/**
 * Browser-level action executor for the AI agent.
 *
 * Contract: accepts a payload of shape `{ action, selector?, value?, key?, direction? }`
 * dispatched by the Python agent, and performs it against the passed webview.
 *
 * Supported actions:
 *   - goto         : load URL
 *   - click        : click CSS selector
 *   - type         : set input value (React-safe) + dispatch input/change
 *   - press_key    : dispatch keydown/keypress/keyup on activeElement
 *   - scroll       : direction = 'up' | 'down' | 'top' | 'bottom'
 *   - back         : navigate back in webview history
 *   - forward      : navigate forward in webview history
 *   - reload       : reload current page
 *   - idle / done  : no-op (caller handles UI)
 *   - error        : no-op (caller handles UI)
 *   - create_tab   : handled by caller (AIChatSidebar via onEnsureTab), no-op here
 *
 * Shell-level actions (browser chrome, NOT webview DOM):
 *   - browser_search / browser_navigate
 *     These are intercepted by AIChatSidebar and routed to onBrowserBarSearch,
 *     which drives the renderer-side address bar like a human. They should
 *     never reach this function; if they do, we safe-fall-back to loadURL.
 */

type ActionPayload = {
    action: string;
    selector?: string;
    value?: string;
    url?: string;
    key?: string;
    direction?: 'up' | 'down' | 'top' | 'bottom' | string;
};

export async function executeAction(webview: Electron.WebviewTag, payload: ActionPayload): Promise<void> {
    const { action, selector, value, key, direction } = payload;

    // ── No-op actions (handled by UI layer) ──
    // `create_tab` is intercepted upstream by the sidebar (onEnsureTab). If it
    // reaches here, we already have a tab mounted, so just load the target URL.
    if (action === 'idle' || action === 'done' || action === 'error') {
        return;
    }

    // Shell-level actions should have been intercepted upstream. Safe fallback:
    // just load the URL into the current webview.
    if (action === 'browser_search' || action === 'browser_navigate') {
        const target = (payload.value || payload.url || '').toString();
        if (!target) return;
        const url = /^https?:\/\//i.test(target) ? target : `https://${target}`;
        webview.loadURL(url);
        return;
    }

    if (action === 'create_tab') {
        const target = (payload.url || value || 'about:blank');
        if (target && target !== 'about:blank' && target !== 'browser_home') {
            webview.loadURL(target.startsWith('http') ? target : `https://${target}`);
        }
        return;
    }

    // ── Navigation ──
    if (action === 'goto' && value) {
        webview.loadURL(value.startsWith('http') ? value : `https://${value}`);
        return;
    }

    if (action === 'back') {
        // `canGoBack` may not exist on older webview typings; call defensively.
        try {
            const wv = webview as any;
            if (typeof wv.canGoBack === 'function' ? wv.canGoBack() : true) {
                wv.goBack();
            }
        } catch {
            // Fallback via history API inside the page
            await webview.executeJavaScript(`history.back()`);
        }
        return;
    }

    if (action === 'forward') {
        try {
            const wv = webview as any;
            if (typeof wv.canGoForward === 'function' ? wv.canGoForward() : true) {
                wv.goForward();
            }
        } catch {
            await webview.executeJavaScript(`history.forward()`);
        }
        return;
    }

    if (action === 'reload') {
        try {
            (webview as any).reload();
        } catch {
            await webview.executeJavaScript(`location.reload()`);
        }
        return;
    }

    // ── Scrolling ──
    if (action === 'scroll') {
        const dir = (direction || 'down').toLowerCase();
        if (dir === 'top') {
            await webview.executeJavaScript(`window.scrollTo({ top: 0, behavior: 'smooth' });`);
            return;
        }
        if (dir === 'bottom') {
            await webview.executeJavaScript(`window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });`);
            return;
        }
        const sign = dir === 'up' ? -1 : 1;
        await webview.executeJavaScript(`
            window.scrollBy({ top: window.innerHeight * 0.6 * ${sign}, behavior: 'smooth' });
        `);
        return;
    }

    // ── press_key doesn't require a selector ──
    if (action === 'press_key') {
        const keyName = key || 'Enter';
        await webview.executeJavaScript(`
            (() => {
                const activeEl = document.activeElement || document.body;
                const keyName = ${JSON.stringify(keyName)};
                let keyCode = 13;
                if (keyName === 'Escape') keyCode = 27;
                if (keyName === 'Tab') keyCode = 9;

                const events = ['keydown', 'keypress', 'keyup'];
                events.forEach(type => {
                    const ev = new KeyboardEvent(type, {
                        key: keyName,
                        code: keyName,
                        keyCode: keyCode,
                        which: keyCode,
                        bubbles: true,
                        cancelable: true
                    });
                    activeEl.dispatchEvent(ev);
                });
            })();
        `);
        return;
    }

    // ── Everything below needs a selector ──
    if (!selector) {
        throw new Error(`Action '${action}' requires a CSS selector`);
    }

    if (action === 'click') {
        await webview.executeJavaScript(`
            (() => {
                const el = document.querySelector(${JSON.stringify(selector)});
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.click();
                } else {
                    throw new Error("Element not found for click: " + ${JSON.stringify(selector)});
                }
            })();
        `);
        return;
    }

    if (action === 'type') {
        await webview.executeJavaScript(`
            (() => {
                const el = document.querySelector(${JSON.stringify(selector)});
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.focus();

                    // React inputs require calling the native setter to register
                    // programmatic value changes.
                    const proto = el.tagName === 'TEXTAREA'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter) {
                        setter.call(el, ${JSON.stringify(value ?? '')});
                    } else {
                        el.value = ${JSON.stringify(value ?? '')};
                    }

                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    throw new Error("Element not found for type: " + ${JSON.stringify(selector)});
                }
            })();
        `);
        return;
    }

    console.warn(`[actionEngine] Unknown action type: ${action}`);
}
