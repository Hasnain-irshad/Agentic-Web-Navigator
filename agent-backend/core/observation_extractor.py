"""
ObservationExtractor: Extracts REAL, interactive DOM elements from a webpage.
Uses a JavaScript injection to walk the live DOM and generate unique CSS selectors.
Every element is numbered so the LLM can reference it by index.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from playwright.async_api import Page

try:
    from config import Config
    from utils import get_logger
except ImportError:
    from ..config import Config
    from ..utils import get_logger


logger = get_logger(__name__)


# ── JavaScript that runs inside the browser to extract elements ───────────
# This is the heart of DOM grounding: it walks real DOM nodes and returns
# structured data with unique CSS selectors.
EXTRACT_ELEMENTS_JS = """
() => {
    try {
        const MAX_ELEMENTS = %d;
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
                    selector += `:nth-of-type(${index})`;
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
        console.error("[ObservationExtractor] DOM script crashed entirely:", err);
        return [];
    }
}
"""


@dataclass
class PageElement:
    """Represents a real, extracted DOM element with a verified CSS selector."""
    index: int               # 1-based index for LLM reference
    tag: str                 # a, button, input, div, h1, etc.
    text: str                # visible text content
    css_selector: str        # unique CSS selector verified against real DOM
    element_type: str        # button, link, input, heading, product, other
    attributes: dict[str, str] = field(default_factory=dict)
    is_clickable: bool = False
    nearby_text: str = ""
    bounding_box: Optional[dict] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "index": self.index,
            "tag": self.tag,
            "text": self.text,
            "css_selector": self.css_selector,
            "type": self.element_type,
            "attributes": self.attributes,
            "is_clickable": self.is_clickable,
            "bounding_box": self.bounding_box,
        }

    # Keep backward-compat property
    @property
    def selector(self) -> str:
        return self.css_selector


@dataclass
class Observation:
    """
    Complete observation of current page state.
    All elements are real DOM elements with verified CSS selectors.

    Attributes:
        url: Current page URL
        title: Page title
        elements: List of real interactive elements
        page_text: Visible text content summary
        error: Any error during extraction
    """
    url: str
    title: str
    elements: list[PageElement] = field(default_factory=list)
    page_text: str = ""
    error: str = ""

    def get_element_by_index(self, index: int) -> Optional[PageElement]:
        """
        Get element by its 1-based index.

        Args:
            index: 1-based element index (as shown to LLM)

        Returns:
            PageElement or None if out of bounds
        """
        if 1 <= index <= len(self.elements):
            return self.elements[index - 1]
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "elements": [e.to_dict() for e in self.elements],
            "page_text": self.page_text,
            "error": self.error,
        }

    def to_prompt_text(self) -> str:
        """Legacy debug representation. Use WorldModel.to_prompt() for LLM prompts."""
        lines = [
            f"URL: {self.url}",
            f"Title: {self.title}",
            f"Elements: {len(self.elements)}",
        ]
        for elem in self.elements[:20]:
            lines.append(f"  [{elem.index}] <{elem.tag}> {elem.text[:50]}")
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


class ObservationExtractor:
    """
    Extracts REAL DOM elements from a Playwright page via JavaScript injection.

    Instead of using Playwright locators (which require pre-known selectors),
    this injects JS that walks the live DOM tree to find all visible interactive
    elements and generates unique CSS selectors for each one.
    """

    def __init__(self, max_elements: int | None = None) -> None:
        """
        Initialize the extractor.

        Args:
            max_elements: Maximum number of elements to extract.
                         Defaults to Config.OBSERVATION_MAX_ELEMENTS.
        """
        self._max_elements = max_elements or Config.OBSERVATION_MAX_ELEMENTS

    async def extract(self, page: Page) -> Observation:
        """
        Extract observation from current page state using JS DOM walking.

        Args:
            page: Playwright Page object

        Returns:
            Observation containing page state and REAL interactive elements
        """
        import asyncio
        try:
            # ── 1. DOM Readiness Buffer ──────────────────────────────────
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception as wait_e:
                logger.debug(f"[Extractor] Timeout waiting for strict load state: {wait_e} - continuing anyway")
                
            await asyncio.sleep(1.0)  # Core stability buffer

            url = page.url
            title = await page.title()

            # ── 4. Bot Protection & CAPTCHA Detection ────────────────────
            page_content = await page.content()
            content_lower = page_content.lower()
            captcha_keywords = ["captcha", "robot check", "unusual traffic", "prove you are human", "checking if the site connection is secure"]
            if any(term in content_lower for term in captcha_keywords):
                logger.warning(f"[Extractor] Anti-Bot/CAPTCHA detected at {url}. Bypassing invalid DOM extraction.")
                return Observation(url=url, title=title, error="Captcha/Bot Protection Blocked DOM Extraction", page_type="error")

            # ── 3. DOM Existence Sandbox Verification ────────────────────
            dom_size = await page.evaluate("document.querySelectorAll('*').length")
            logger.info(f"[Extractor DEBUG] URL prior to extraction: {url}")
            logger.info(f"[Extractor DEBUG] Total raw DOM nodes size: {dom_size}")
            
            if dom_size == 0:
                logger.warning("[Extractor] CRITICAL: DOM size reported as 0. Page failed to render or execution context is trapped inside iframe.")

            # ── 5. Base Check: Do selectors even work here? ──────────────
            base_interactive = await page.evaluate("document.querySelectorAll('input, button, a, textarea').length")
            if base_interactive == 0:
                logger.warning("[Extractor] CRITICAL: Base `a, button, input` nodes length is 0. Standard interactive UI is entirely missing.")

            # ── Inject JS to extract elements from real DOM ───────────
            js_code = EXTRACT_ELEMENTS_JS % self._max_elements
            raw_elements = await page.evaluate(js_code)
            
            logger.info(f"[Extractor] JS returned {len(raw_elements or [])} elements")

            # ── Retry fallback if 0 elements ──────────────────────────
            if not raw_elements:
                logger.warning("[Extractor] 0 elements on first try, retrying after 2s...")
                await asyncio.sleep(2.0)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                raw_elements = await page.evaluate(js_code)
                logger.info(f"[Extractor] Retry returned {len(raw_elements or [])} elements")

            # ── Convert raw JS results to PageElement objects ─────────
            elements: list[PageElement] = []
            for i, raw in enumerate(raw_elements or [], start=1):
                try:
                    elements.append(PageElement(
                        index=i,
                        tag=raw.get("tag", ""),
                        text=raw.get("text", ""),
                        css_selector=raw.get("css_selector", ""),
                        element_type=raw.get("element_type", "other"),
                        attributes=raw.get("attributes", {}),
                        is_clickable=raw.get("is_clickable", False),
                        nearby_text=raw.get("nearby_text", ""),
                        bounding_box=raw.get("bounding_box"),
                    ))
                except Exception:
                    continue

            # ── Extract page text ─────────────────────────────────────
            page_text = await self._extract_page_text(page)
            
            logger.info(f"[Extractor] Final: {len(elements)} elements from {url[:60]}")
            
            return Observation(
                url=url,
                title=title,
                elements=elements,
                page_text=page_text,
            )

        except Exception as e:
            logger.error(f"Observation extraction failed: {e}")
            return Observation(
                url=getattr(page, "url", "unknown"),
                title="",
                error=str(e),
            )

    async def extract_for_intent(
        self,
        page: Page,
        intent: str,
    ) -> Observation:
        """
        Extract and rank elements by relevance to a specific intent.
        """
        from core.element_resolver import ElementResolver, IntentType, detect_intent

        obs = await self.extract(page)

        if obs.elements and intent:
            intent_type = detect_intent(intent)
            ranked = ElementResolver.resolve(obs.elements, intent_type, intent)
            
            reindexed = []
            for new_idx, (elem, _score) in enumerate(ranked, start=1):
                elem.index = new_idx
                reindexed.append(elem)
            obs.elements = reindexed

        return obs

    async def _extract_page_text(self, page: Page) -> str:
        """Extract main visible text content."""
        try:
            body_text = await page.locator("body").inner_text()
            lines = [line.strip() for line in body_text.split("\n") if line.strip()]
            text = " ".join(lines)
            return text[:3500]
        except Exception as e:
            logger.debug(f"Page text extraction error: {e}")
            return ""
