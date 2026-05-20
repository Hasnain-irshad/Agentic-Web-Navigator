import { useState, useRef, useEffect } from 'react';
import { MdClose } from 'react-icons/md';
import { extractDOMState } from '../util/domExtractor';
import { executeAction } from '../util/actionEngine';

interface Props {
  open: boolean;
  onClose: () => void;
  webview: Electron.WebviewTag | null;
  /** Mounts a webview tab if one doesn't exist. Defaults to about:blank.
   *  Called when the user sends an AI command from a non-webview page. */
  onEnsureTab: (initialUrl?: string) => void;
  /** Shell-level "address-bar search". The agent uses this for site
   *  navigation instead of poking at page DOM inputs. */
  onBrowserBarSearch: (query: string) => void;
  /** Current address-bar URL, for the browser_shell state snapshot. */
  currentUrl: string;
}

/** Wait until `check()` returns a non-null value or timeout. Used to bridge
 *  React re-render delay when we call `onEnsureTab` from an async handler. */
function waitFor<T>(check: () => T | null, timeoutMs = 3000, intervalMs = 80): Promise<T> {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const tick = () => {
      const v = check();
      if (v) return resolve(v);
      if (Date.now() - t0 > timeoutMs) return reject(new Error('waitFor: timeout'));
      setTimeout(tick, intervalMs);
    };
    tick();
  });
}

/** Wait for a freshly-mounted webview to be DOM-ready before extracting state. */
function waitForWebviewReady(wv: Electron.WebviewTag, timeoutMs = 3000): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      wv.removeEventListener('dom-ready', done);
      resolve();
    };
    // Already ready? getURL()/isLoading() are safe proxies.
    try {
      if (!wv.isLoading()) return done();
    } catch { /* proceed to event wait */ }
    wv.addEventListener('dom-ready', done);
    setTimeout(done, timeoutMs);
  });
}

export default function AIChatSidebar({
  open, onClose, webview, onEnsureTab, onBrowserBarSearch, currentUrl,
}: Props) {
  const [width, setWidth] = useState(350);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const [isResizing, setIsResizing] = useState(false);

  const [messages, setMessages] = useState<{role: 'user' | 'agent' | 'system', content: string}[]>([]);
  const [msgInput, setMsgInput] = useState('');
  const [sessionId] = useState(() => Math.random().toString(36).substring(2, 15));

  const wsRef = useRef<WebSocket | null>(null);
  // Mirror the webview prop into a ref so async handlers always see the latest
  // value after `onEnsureTab` triggers a re-render.
  const webviewRef = useRef<Electron.WebviewTag | null>(webview);
  useEffect(() => { webviewRef.current = webview; }, [webview]);
  // Same treatment for currentUrl — used when snapshotting browser_shell.
  const currentUrlRef = useRef<string>(currentUrl);
  useEffect(() => { currentUrlRef.current = currentUrl; }, [currentUrl]);
  const [isRunning, setIsRunning] = useState(false);

  /** Build a state payload with the browser_shell snapshot attached.
   *  The backend uses this to prefer the address bar over page DOM inputs. */
  const buildStatePayload = async (wv: Electron.WebviewTag) => {
    const state: any = await extractDOMState(wv);
    state.browser_shell = {
      search_bar_available: true,
      active_input: 'search_bar',
      current_url: currentUrlRef.current || (wv ? wv.getURL?.() : '') || '',
    };
    return state;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsResizing(true);
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth >= 250 && newWidth <= 600) setWidth(newWidth);
    };

    const handleMouseUp = () => setIsResizing(false);

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  const connectWS = () => {
    if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
      wsRef.current = new WebSocket('ws://127.0.0.1:8000/ws');
      wsRef.current.onopen = () => {
        console.log('Connected to Agent WS');
      };
      
      wsRef.current.onmessage = async (event) => {
        const payload = JSON.parse(event.data);
        console.log("Agent sent:", payload);

        // ── Error from agent ──
        if (payload.action === 'error') {
            setMessages(prev => [...prev, { role: 'system', content: `Error: ${payload.message || payload.reasoning || 'unknown'}` }]);
            setIsRunning(false);
            return;
        }

        // ── Terminal states: done, idle, loop-stop, budget-exhausted ──
        if (payload.action === 'done' || payload.action === 'idle' || payload.done) {
            const reason: string = payload.reasoning || 'Done.';
            let statusTag = 'Goal completed';
            if (payload.task_status === 'failed') {
                statusTag = /loop/i.test(reason) ? 'Stopped due to loop' : 'Task failed';
            } else if (payload.task_status === 'awaiting_user') {
                statusTag = reason.startsWith('Completed') ? 'Goal completed' : 'Awaiting next command';
            }
            setMessages(prev => [...prev, { role: 'agent', content: `${statusTag}: ${reason}` }]);
            setIsRunning(false);
            return;
        }

        // ── Normal action from agent ──
        const targetBits = [payload.selector, payload.key, payload.value, payload.direction]
            .filter(Boolean)
            .join(' | ');
        const actionDesc = `${payload.action}${targetBits ? ` -> ${targetBits}` : ''}`;
        const trailer = payload.session_snapshot?.subgoal
            ? ` | subgoal: ${payload.session_snapshot.subgoal}`
            : '';
        setMessages(prev => [...prev, {
            role: 'agent',
            content: `[${actionDesc}] ${payload.reasoning || ''}${trailer}`,
        }]);

        // ── Shell-level actions (browser chrome, not webview DOM) ──
        // `browser_search` / `browser_navigate` drive the URL/address bar the
        // same way a human types into it. We intentionally do NOT open a new
        // tab. We visually update the bar and let the webview navigate.
        if (payload.action === 'browser_search' || payload.action === 'browser_navigate') {
            const query = (payload.value || payload.url || '').toString();
            if (!query) {
                setMessages(prev => [...prev, { role: 'system', content: 'browser_search missing query' }]);
                setIsRunning(false);
                return;
            }
            // Ensure a tab exists (shell drives existing webview if mounted)
            if (!webviewRef.current) {
                onEnsureTab('about:blank');
                try { await waitFor(() => webviewRef.current, 3500); } catch { /* fall through */ }
            }
            onBrowserBarSearch(query);

            // Wait for the webview to settle on the new URL, then echo state
            try {
                const wv = await waitFor(() => webviewRef.current, 3500);
                await waitForWebviewReady(wv, 5000);
                await new Promise(r => setTimeout(r, 600));
                const state = await buildStatePayload(wv);
                wsRef.current?.send(JSON.stringify({ state, session_id: sessionId }));
            } catch (err) {
                setMessages(prev => [...prev, {
                    role: 'system',
                    content: `Browser bar navigation failed: ${(err as Error)?.message || err}`,
                }]);
                setIsRunning(false);
            }
            return;
        }

        // Handle `create_tab` at the frontend level — no webview needed
        if (payload.action === 'create_tab') {
            const initial = (payload.url || payload.value || 'about:blank').toString();
            onEnsureTab(initial === 'browser_home' ? 'about:blank' : initial);
            try {
                const wv = await waitFor(() => webviewRef.current, 3500);
                await waitForWebviewReady(wv);
                const state = await buildStatePayload(wv);
                wsRef.current?.send(JSON.stringify({ state, session_id: sessionId }));
            } catch (err) {
                setMessages(prev => [...prev, {
                    role: 'system',
                    content: `Failed to open tab: ${(err as Error)?.message || err}`,
                }]);
                setIsRunning(false);
            }
            return;
        }

        const wv = webviewRef.current;
        if (!wv) {
            // Self-heal: mount a blank tab and retry state extraction
            onEnsureTab('about:blank');
            try {
                const mounted = await waitFor(() => webviewRef.current, 3500);
                await waitForWebviewReady(mounted);
                const state = await buildStatePayload(mounted);
                wsRef.current?.send(JSON.stringify({ state, session_id: sessionId }));
            } catch (err) {
                console.error('Recovery tab-open failed', err);
                setIsRunning(false);
            }
            return;
        }

        try {
            await executeAction(wv, payload);

            // Give the page a moment to settle. Navigation-ish actions need longer.
            const settleMs = ['goto', 'click', 'back', 'forward', 'reload', 'press_key'].includes(payload.action)
                ? 2000
                : 800;
            await new Promise(r => setTimeout(r, settleMs));

            const state = await buildStatePayload(wv);
            wsRef.current?.send(JSON.stringify({ state, session_id: sessionId }));
        } catch (err: any) {
            console.error('Action execution failed', err);
            setMessages(prev => [...prev, {
                role: 'system',
                content: `Action failed: ${err?.message || err?.toString()}`,
            }]);

            // Always echo current state back so the agent can recover
            try {
                const state = await buildStatePayload(wv);
                wsRef.current?.send(JSON.stringify({ state, session_id: sessionId }));
            } catch (innerErr) {
                console.error('Recovery state extraction failed', innerErr);
                setIsRunning(false);
            }
        }
      };
      
      wsRef.current.onclose = () => {
        console.log('Agent WS Closed');
        setIsRunning(false);
      };
      
      wsRef.current.onerror = (err) => {
        console.error('Agent WS error', err);
        setMessages(prev => [...prev, { role: 'system', content: 'Connection to agent backend failed. Ensure FastAPI is running.' }]);
        setIsRunning(false);
      };
    }
  };

  const startSession = async (cmd: string) => {
    setIsRunning(true);
    // Append the new user command — do NOT clear history; multi-turn
    // follow-ups like "add 2nd item to cart" rely on seeing context.
    setMessages(prev => [...prev, { role: 'user', content: cmd }]);
    setMsgInput('');

    // ── Tab-initialization rule ──
    // If there's no webview mounted (user is on landing/bookmarks/etc.),
    // we create a blank tab. No error, no forced search-engine redirect.
    let wv = webviewRef.current;
    if (!wv) {
        setMessages(prev => [...prev, { role: 'system', content: 'Opening a new blank tab...' }]);
        onEnsureTab('about:blank');
        try {
            wv = await waitFor(() => webviewRef.current, 3500);
            await waitForWebviewReady(wv);
        } catch {
            setMessages(prev => [...prev, { role: 'system', content: 'Failed to open a tab. Please try again.' }]);
            setIsRunning(false);
            return;
        }
    }

    connectWS();
    await new Promise(r => setTimeout(r, 500));

    try {
        setMessages(prev => [...prev, { role: 'system', content: 'Extracting page state...' }]);
        const state = await buildStatePayload(wv);

        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({
                command: cmd,
                state: state,
                session_id: sessionId,
            }));
            setMessages(prev => [...prev, { role: 'system', content: 'Command sent to Agent...' }]);
        } else {
            setMessages(prev => [...prev, { role: 'system', content: 'Error: Agent websocket is not ready.' }]);
            setIsRunning(false);
        }
    } catch (err: any) {
        setMessages(prev => [...prev, { role: 'system', content: `Extraction failed: ${err}` }]);
        setIsRunning(false);
    }
  };

  const handleSend = () => {
    if (!msgInput.trim()) return;
    if (isRunning) {
        // Just add note, agent is running
        setMessages(prev => [...prev, { role: 'system', content: "Agent is currently running. We will stop the current task and start over logic not implemented yet." }]);
        setMsgInput('');
        return;
    }
    startSession(msgInput.trim());
  };

  return (
    <div
      ref={sidebarRef}
      style={{
        position: 'fixed',
        top: 0,
        right: open ? 0 : -width,
        width,
        height: '100%',
        background: '#1f1f1f',
        color: 'white',
        boxShadow: '-2px 0 8px rgba(0,0,0,0.5)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'right 0.3s',
        zIndex: 9999, // Ensure it's on top of webview
      }}
    >
      {/* Header */}
      <div style={headerStyle}>
        <span>AI Agent {isRunning && <span style={{color: '#4facfe', marginLeft: 8}}>(Running...)</span>}</span>
        <MdClose size={24} style={{ cursor: 'pointer' }} onClick={onClose} />
      </div>

      {/* Resizer */}
      <div
        style={resizerStyle}
        onMouseDown={handleMouseDown}
        title="Drag to resize"
      />

      {/* Chat area */}
      <div style={chatAreaStyle}>
        {messages.length === 0 ? (
          <p style={{ textAlign: 'center', color: '#888' }}>
            Start a session by entering a command...
          </p>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} style={msg.role === 'user' ? userMsgStyle : (msg.role === 'system' ? sysMsgStyle : agentMsgStyle)}>
              <b>{msg.role.toUpperCase()}:</b> {msg.content}
            </div>
          ))
        )}
      </div>

      {/* Input box */}
      <div style={inputContainerStyle}>
        <input
          style={inputStyle}
          placeholder="e.g. Add first item to cart"
          value={msgInput}
          onChange={(e) => setMsgInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          disabled={isRunning}
        />
        <button style={sendButtonStyle} onClick={handleSend} disabled={isRunning}>
          Run
        </button>
      </div>
    </div>
  );
}

/* ---------- Styles ---------- */
const headerStyle: React.CSSProperties = {
  padding: '12px 16px',
  borderBottom: '1px solid #333',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  fontWeight: 'bold',
  fontSize: '16px',
};

const resizerStyle: React.CSSProperties = {
  position: 'absolute',
  left: -5,
  top: 0,
  width: 10,
  height: '100%',
  cursor: 'ew-resize',
  zIndex: 1001,
};

const chatAreaStyle: React.CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '10px',
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
};

const agentMsgStyle: React.CSSProperties = {
  background: '#333',
  borderRadius: '8px',
  padding: '8px 12px',
  alignSelf: 'flex-start',
  maxWidth: '90%',
  wordBreak: 'break-word',
  fontSize: 13,
};

const userMsgStyle: React.CSSProperties = {
  background: '#4facfe',
  color: '#fff',
  borderRadius: '8px',
  padding: '8px 12px',
  alignSelf: 'flex-end',
  maxWidth: '90%',
  wordBreak: 'break-word',
  fontSize: 13,
};

const sysMsgStyle: React.CSSProperties = {
  background: 'transparent',
  color: '#888',
  fontStyle: 'italic',
  alignSelf: 'center',
  fontSize: 12,
  padding: '4px',
};

const inputContainerStyle: React.CSSProperties = {
  display: 'flex',
  padding: '8px',
  borderTop: '1px solid #333',
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: '8px 12px',
  borderRadius: '20px',
  border: 'none',
  outline: 'none',
  fontSize: '14px',
};

const sendButtonStyle: React.CSSProperties = {
  marginLeft: '8px',
  padding: '8px 16px',
  borderRadius: '20px',
  border: 'none',
  backgroundColor: '#dd9a0a',
  color: 'white',
  fontWeight: 'bold',
  cursor: 'pointer',
};
