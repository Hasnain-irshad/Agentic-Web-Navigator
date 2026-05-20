export const DOM_EXTRACTOR_JS = `
(() => {
    try {
        const MAX_ELEMENTS = 200;
        const results = [];

        function uniqueSelector(el) {
            if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
                return '#' + CSS.escape(el.id);
            }
            const testId = el.getAttribute('data-testid');
            if (testId && document.querySelectorAll('[data-testid="' + CSS.escape(testId) + '"]').length === 1) {
                return '[data-testid="' + CSS.escape(testId) + '"]';
            }
            for (const attr of ['data-sku', 'data-product-id', 'data-item-id']) {
                const val = el.getAttribute(attr);
                if (val) {
                    const sel = '[' + attr + '="' + CSS.escape(val) + '"]';
                    if (document.querySelectorAll(sel).length === 1) return sel;
                }
            }
            const parts = [];
            let current = el;
            while (current && current !== document.documentElement) {
                let selector = current.tagName.toLowerCase();
                if (current.id && document.querySelectorAll('#' + CSS.escape(current.id)).length === 1) {
                    parts.unshift('#' + CSS.escape(current.id));
                    break;
                }
                let siblings = Array.from(current.parentNode.children).filter(node => node.tagName === current.tagName);
                if (siblings.length > 1) {
                    let index = siblings.indexOf(current) + 1;
                    selector += \`:nth-of-type(\${index})\`;
                }
                parts.unshift(selector);
                current = current.parentNode;
            }
            return parts.join(' > ');
        }

        function isVisible(el) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility !== 'visible' || style.opacity === '0') return false;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return false;
            return true;
        }

        function getText(el) {
            const t = el.innerText || el.textContent || '';
            return t.replace(/\\s+/g, ' ').trim();
        }

        function getAttrs(el) {
            const attrs = {};
            const keys = ['id', 'class', 'href', 'placeholder', 'name', 'type', 'value', 'aria-label', 'role', 'data-sku', 'data-product-id', 'data-testid', 'title', 'alt'];
            for (const k of keys) {
                const v = el.getAttribute(k);
                if (v) attrs[k] = v;
            }
            return attrs;
        }

        function classifyElement(el, tag) {
            if (tag === 'input' || tag === 'textarea' || tag === 'select') return 'input';
            if (tag === 'button' || el.getAttribute('role') === 'button') return 'button';
            if (tag === 'a') return 'link';
            return 'other';
        }

        const interactiveSelectors = [
            'a[href]', 'button', 'input:not([type="hidden"])', 'textarea', 'select',
            '[role="button"]', '[role="link"]', '[role="menuitem"]', '[role="option"]', '[tabindex]:not([tabindex="-1"])',
            '[onclick]'
        ];

        const elements = document.querySelectorAll(interactiveSelectors.join(', '));
        const seen = new Set();
        let currentIndex = 1;

        for (const el of elements) {
            if (results.length >= MAX_ELEMENTS) break;
            if (seen.has(el)) continue;
            if (!isVisible(el)) continue;

            seen.add(el);

            try {
                const tag = el.tagName.toLowerCase();
                const text = getText(el);
                const type = classifyElement(el, tag);

                if (type !== 'input' && !text && !el.getAttribute('aria-label') && !el.getAttribute('title')) {
                    continue;
                }

                let nearbyText = '';
                if (el.parentElement) {
                    const parentText = (el.parentElement.innerText || el.parentElement.textContent || '').trim().replace(/\\s+/g, ' ');
                    if (parentText !== text && parentText.length < 300) {
                        nearbyText = parentText;
                    }
                }

                const rect = el.getBoundingClientRect();
                results.push({
                    index: currentIndex++,
                    tag: tag,
                    text: text,
                    css_selector: uniqueSelector(el),
                    element_type: type,
                    attributes: getAttrs(el),
                    is_clickable: true,
                    nearby_text: nearbyText,
                    bounding_box: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                    },
                });
            } catch (e) {
                // Skip inner errors
            }
        }

        try {
            const headings = document.querySelectorAll('h1, h2, h3');
            for (const h of headings) {
                if (results.length >= MAX_ELEMENTS) break;
                if (seen.has(h)) continue;
                if (!isVisible(h)) continue;
                seen.add(h);
                const text = getText(h);
                if (!text) continue;
                results.push({
                    index: currentIndex++,
                    tag: h.tagName.toLowerCase(),
                    text: text,
                    css_selector: uniqueSelector(h),
                    element_type: 'heading',
                    attributes: getAttrs(h),
                    is_clickable: false,
                    bounding_box: null,
                });
            }
        } catch(e) {}

        return results;

    } catch (err) {
        console.error("DOM script crashed entirely:", err);
        return [];
    }
})();
`;

export async function extractDOMState(webview: Electron.WebviewTag): Promise<any> {
    try {
        const elements = await webview.executeJavaScript(DOM_EXTRACTOR_JS);
        
        // Also extract some basic page info
        const page_text = await webview.executeJavaScript(`
            (() => {
                const text = document.body ? document.body.innerText : '';
                return text.split('\\n').map(t => t.trim()).filter(Boolean).join(' ').substring(0, 3500);
            })();
        `);
        
        const url = webview.getURL();
        const title = webview.getTitle();

        return {
            url,
            title,
            elements: elements || [],
            page_text: page_text || '',
            error: ''
        };
    } catch (err: any) {
        return {
            url: webview.getURL(),
            title: webview.getTitle(),
            elements: [],
            page_text: '',
            error: err.toString()
        };
    }
}
