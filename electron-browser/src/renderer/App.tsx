import { useState, useEffect, useCallback } from 'react';
import './App.css';
import IconButton from './components/IconButton';
import AIChatSidebar from './components/AIChatSidebar';
import BrowserMenu from './components/BrowserMenu';
import {
  MdArrowBackIos,
  MdArrowForwardIos,
  MdRefresh,
  MdMoreVert,
  MdStar,
  MdChat,
} from 'react-icons/md';
import LandingPage from './pages/LandingPage';

// import pages
import Bookmarks from './pages/Bookmarks';
import History from './pages/History';
import Settings from './pages/Settings';

type Page = 'landing' | 'webview' | 'bookmarks' | 'history' | 'settings' | 'error';

export default function App() {
  const [webview, setWebview] = useState<Electron.WebviewTag | null>(null);
  const [url, setUrl] = useState('');
  const [webviewSrc, setWebviewSrc] = useState(''); // Separate src prop to preserve history
  const [input, setInput] = useState(url);
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [page, setPage] = useState<Page>('landing');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errorInfo, setErrorInfo] = useState<{
    url: string;
    errorCode?: number;
    errorDescription?: string;
  } | null>(null);

  // Human-friendly site shortcuts for the address bar (omnibox).
  // Keep in sync with backend DOMAIN_ALIASES in task_planner.py.
  const SITE_ALIASES: Record<string, string> = {
    youtube: 'https://www.youtube.com',
    facebook: 'https://www.facebook.com',
    instagram: 'https://www.instagram.com',
    twitter: 'https://twitter.com',
    x: 'https://x.com',
    daraz: 'https://www.daraz.pk',
    amazon: 'https://www.amazon.com',
    ebay: 'https://www.ebay.com',
    flipkart: 'https://www.flipkart.com',
    walmart: 'https://www.walmart.com',
    aliexpress: 'https://www.aliexpress.com',
    google: 'https://www.google.com',
    duckduckgo: 'https://duckduckgo.com',
    github: 'https://github.com',
    reddit: 'https://www.reddit.com',
    linkedin: 'https://www.linkedin.com',
    wikipedia: 'https://en.wikipedia.org',
  };

  /**
   * Resolve whatever the user typed into the address bar into a real URL.
   *   - Bare alias ("youtube")   -> full https URL
   *   - Domain-ish ("daraz.pk")  -> https://daraz.pk
   *   - Full URL                 -> as-is
   * Returns null if the input can't be interpreted as a URL at all.
   */
  const resolveAddressBarInput = (raw: string): string | null => {
    const t = raw.trim();
    if (!t) return null;

    // Already a URL
    if (/^https?:\/\//i.test(t)) {
      try { new URL(t); return t; } catch { return null; }
    }

    // Alias
    const alias = SITE_ALIASES[t.toLowerCase()];
    if (alias) return alias;

    // Domain-ish (contains a dot + plausible TLD)
    if (/^[a-z0-9\-]+(\.[a-z0-9\-]+)+(\/.*)?$/i.test(t)) {
      return `https://${t}`;
    }

    // Single bare token — treat as .com as a best-effort
    if (/^[a-z0-9\-]{2,}$/i.test(t)) {
      return `https://www.${t.toLowerCase()}.com`;
    }

    return null;
  };

  // Safe navigate when typing in URL bar.
  const safeNavigate = (inputUrl: string) => {
    const resolved = resolveAddressBarInput(inputUrl);
    if (!resolved) {
      console.error('Could not resolve address bar input:', inputUrl);
      return;
    }
    setWebviewSrc(resolved);
    setUrl(resolved);
    setInput(resolved);
    setPage('webview');
  };

  /**
   * Shell-level "browser search": the AI agent calls this to mimic a human
   * typing into the address bar and pressing Enter. Visually updates the
   * input so the user SEES the agent using the browser UI.
   */
  const browserBarSearch = useCallback((query: string) => {
    if (!query || !query.trim()) return;
    const resolved = resolveAddressBarInput(query) || query;
    setInput(query);           // show the raw query in the bar (human-like)
    setUrl(resolved);
    setWebviewSrc(resolved);
    setPage('webview');
  }, []);

  /**
   * Guarantee a webview tab exists. Called by the AI sidebar when the user
   * sends a command while on a non-webview page (landing, bookmarks, etc.).
   *
   * The tab opens on `about:blank` by default — NO automatic redirect to a
   * search engine. The agent decides where to go after observing state.
   */
  const ensureTab = useCallback((initialUrl: string = 'about:blank') => {
    setPage((currentPage) => {
      if (currentPage === 'webview' && webview) return currentPage;
      // Mounting webview for the first time — give it a neutral src
      setWebviewSrc(initialUrl);
      setUrl(initialUrl === 'about:blank' ? '' : initialUrl);
      setInput(initialUrl === 'about:blank' ? '' : initialUrl);
      return 'webview';
    });
  }, [webview]);

  useEffect(() => {
    const unsubscribe = window.electron.ipcRenderer.on(
      'renderer-navigate',
      (...args: unknown[]) => {
        console.log('RECEIVED IPC:', args);
        const url = args[0];

        if (typeof url !== 'string') return;
        if (!webview) return;

        webview.stop();
        webview.loadURL(url);

        setWebviewSrc(url);
        setUrl(url);
        setInput(url);
        setPage('webview');
      },
    );

    return () => {
      unsubscribe();
    };
  }, [webview]);

  // Listen to webview navigation and automatically add to history
  useEffect(() => {
    if (!webview) return;

    const handleNavigation = (event: Electron.DidNavigateEvent) => {
      const currentUrl = event.url;
      setUrl(currentUrl);
      setInput(currentUrl);
      // NOTE: Do NOT update webviewSrc here, as it forces re-navigation and clears forward history

      // send history item to main process
      window.electron.ipcRenderer.sendMessage('history-add', {
        url: currentUrl,
        title: webview.getTitle() || currentUrl,
        timestamp: Date.now(),
      });
    };

    const handleInPageNavigation = (event: Electron.DidNavigateInPageEvent) => {
      const currentUrl = event.url;
      setUrl(currentUrl);
      setInput(currentUrl);

      // optional: add in-page navigation to history
      window.electron.ipcRenderer.sendMessage('history-add', {
        url: currentUrl,
        title: webview.getTitle() || currentUrl,
        timestamp: Date.now(),
      });
    };

    const handleTitleUpdate = (event: any) => {
      // Update last history item with latest title
    };

    webview.addEventListener('did-navigate', handleNavigation);
    webview.addEventListener('did-navigate-in-page', handleInPageNavigation);
    webview.addEventListener('page-title-updated', handleTitleUpdate);

    return () => {
      webview.removeEventListener('did-navigate', handleNavigation);
      webview.removeEventListener(
        'did-navigate-in-page',
        handleInPageNavigation,
      );
      webview.removeEventListener('page-title-updated', handleTitleUpdate);
    };
  }, [webview]);

  // for loading bar
  useEffect(() => {
    if (!webview) return;

    let progressInterval: NodeJS.Timeout | null = null;

    const startLoading = () => {
      setLoading(true);
      setProgress(10);

      // Fake progress until real finish (like Chrome does)
      progressInterval = setInterval(() => {
        setProgress((p) => (p < 90 ? p + Math.random() * 5 : p));
      }, 200);
    };

    const stopLoading = () => {
      if (progressInterval) clearInterval(progressInterval);
      setProgress(100);

      // Let bar reach 100% then hide
      setTimeout(() => {
        setLoading(false);
        setProgress(0);
      }, 300);
    };

    webview.addEventListener('did-start-loading', startLoading);
    webview.addEventListener('did-stop-loading', stopLoading);
    webview.addEventListener('did-fail-load', stopLoading);

    return () => {
      webview.removeEventListener('did-start-loading', startLoading);
      webview.removeEventListener('did-stop-loading', stopLoading);
      webview.removeEventListener('did-fail-load', stopLoading);
      if (progressInterval) clearInterval(progressInterval);
    };
  }, [webview]);


  const handleMenuClick = (target: Page) => {
    setPage(target);
    setMenuOpen(false);
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top bar: always visible */}
      <div className="top-bar" style={{ position: 'relative' }}>
        <IconButton
          icon={MdArrowBackIos}
          onClick={() => {
            if (webview?.canGoBack()) {
              webview.goBack();
            } else {
              setPage('landing');
            }
          }}
          tooltip="Back"
        />
        <IconButton
          icon={MdArrowForwardIos}
          onClick={() => {
            if (webview?.canGoForward()) {
              webview.goForward();
            }
          }}
          tooltip="Forward"
        />
        <IconButton
          icon={MdRefresh}
          onClick={() => webview?.reloadIgnoringCache()}
          tooltip="Reload"
        />

        <input
          style={inputStyle}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && safeNavigate(input)}
          placeholder="Enter address"
        />

        <IconButton
          icon={MdStar}
          onClick={() => {
            if (!url) return;
            window.electron.ipcRenderer.sendMessage('bookmark-add', {
              url,
              title: webview?.getTitle() || url,
              timestamp: Date.now(),
            });
            alert('Bookmark added!');
          }}
          tooltip="Add Bookmark"
        />

        <IconButton
          icon={MdChat}
          onClick={() => setChatOpen((v) => !v)}
          tooltip="AI Chat"
        />
        <IconButton
          icon={MdMoreVert}
          onClick={() => setMenuOpen((v) => !v)}
          tooltip="Menu"
        />

        <BrowserMenu
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          onOptionClick={handleMenuClick}
        />
      </div>

      {loading && (
        <div style={loadingBarContainer}>
          <div style={{ ...loadingBar, width: `${progress}%` }} />
        </div>
      )}

      {/* Main content below top bar */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {/* Landing Page */}
        {page === 'landing' && (
          <LandingPage
            onNavigate={(newUrl) => {
              // Update BOTH url and src for new navigation
              setWebviewSrc(newUrl);
              setUrl(newUrl);
              setInput(newUrl);
              setPage('webview');
            }}
          />
        )}

        {/* Webview */}
        {page === 'webview' && (
          <webview
            ref={(ref) => setWebview(ref as Electron.WebviewTag | null)}
            src={webviewSrc}
            style={{ width: '100%', height: '100%' }}
            allowpopups
            useragent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
          />
        )}

        {/* Bookmarks */}
        {page === 'bookmarks' && (
          <Bookmarks
            onBack={(newUrl?: string) => {
              if (newUrl) {
                setWebviewSrc(newUrl);
                setUrl(newUrl);
                setInput(newUrl);
              }
              setPage('webview');
            }}
          />
        )}

        {/* History */}
        {page === 'history' && (
          <History
            onBack={(newUrl?: string) => {
              if (newUrl) {
                setWebviewSrc(newUrl);
                setUrl(newUrl);
                setInput(newUrl);
              }
              setPage('webview');
            }}
          />
        )}

        {/* Settings */}
        {page === 'settings' && <Settings />}
      </div>
      <AIChatSidebar
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        webview={webview}
        onEnsureTab={ensureTab}
        onBrowserBarSearch={browserBarSearch}
        currentUrl={url}
      />
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: '8px 14px',
  borderRadius: '20px',
  border: '1px solid #555',
  outline: 'none',
};


const loadingBarContainer: React.CSSProperties = {
  height: '3px',
  width: '100%',
  background: 'transparent',
  overflow: 'hidden',
};

const loadingBar: React.CSSProperties = {
  height: '100%',
  background: 'linear-gradient(90deg, #4facfe, #dd9a0a)',
  transition: 'width 0.2s ease',
};
