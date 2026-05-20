"""
World Model: Converts raw DOM observations into structured semantic page representations.

This is the central intelligence layer. The LLM never sees raw DOM — it only sees
the compact, structured WorldModel output.

Pipeline: DOM Elements → Enrichment → Grouping → Page Detection → WorldModel
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

try:
    from core.observation_extractor import PageElement, Observation
    from utils import get_logger
except ImportError:
    from .observation_extractor import PageElement, Observation
    from ..utils import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Page States
# ═══════════════════════════════════════════════════════════════════════════

class PageState(Enum):
    HOME_PAGE = "HOME_PAGE"
    SEARCH_RESULTS = "SEARCH_RESULTS"
    PRODUCT_PAGE = "PRODUCT_PAGE"
    LOGIN_PAGE = "LOGIN_PAGE"
    CART_PAGE = "CART_PAGE"
    ERROR_PAGE = "ERROR_PAGE"
    GENERIC = "GENERIC"


# ═══════════════════════════════════════════════════════════════════════════
# Semantic Role Assignment
# ═══════════════════════════════════════════════════════════════════════════

class SemanticRole(Enum):
    SEARCH_INPUT = "search_input"
    SEARCH_BUTTON = "search_button"
    PRODUCT_CARD = "product_card"
    ACTION_BUTTON = "action_button"       # add to cart, buy now, checkout
    FILTER_CONTROL = "filter_control"
    NAVIGATION_LINK = "navigation_link"
    LOGIN_INPUT = "login_input"
    FORM_INPUT = "form_input"
    HEADING = "heading"
    GENERIC_LINK = "generic_link"
    GENERIC_BUTTON = "generic_button"
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# Enriched Element (internal intermediary)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EnrichedElement:
    """A PageElement enriched with semantic metadata."""
    source: PageElement                    # Original element with css_selector
    semantic_role: SemanticRole = SemanticRole.UNKNOWN
    inferred_label: str = ""               # e.g. "Add to Cart Button", "Search Input"
    importance: float = 0.0                # 0.0 to 1.0
    confidence: float = 0.0                # 0.0 to 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Structured Item Representations (what the LLM sees)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SearchInfo:
    found: bool = False
    element_index: int = -1                # Links back to PageElement.index
    css_selector: str = ""
    placeholder: str = ""

@dataclass
class ProductItem:
    rank: int = 0                          # 1-based ordinal
    title: str = ""
    price: str = ""
    element_index: int = -1
    css_selector: str = ""

@dataclass
class ActionItem:
    label: str = ""                        # "Add to Cart", "Buy Now"
    element_index: int = -1
    css_selector: str = ""

@dataclass
class FilterItem:
    label: str = ""
    element_index: int = -1
    css_selector: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# WorldModel — the final structured output
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class WorldModel:
    """Complete structured semantic representation of a page.
    
    This is the ONLY thing the LLM sees. No raw DOM, no element lists.
    """
    url: str = ""
    title: str = ""
    page_state: PageState = PageState.GENERIC

    # Structured semantic groups
    search: Optional[SearchInfo] = None
    products: List[ProductItem] = field(default_factory=list)
    actions: List[ActionItem] = field(default_factory=list)
    filters: List[FilterItem] = field(default_factory=list)
    
    # Page context
    page_text_summary: str = ""
    error: str = ""

    # Internal lookup (NOT sent to LLM)
    _element_map: Dict[int, PageElement] = field(default_factory=dict, repr=False)

    def resolve_element(self, element_index: int) -> Optional[PageElement]:
        """Resolve a world model element index back to a real PageElement with css_selector."""
        return self._element_map.get(element_index)

    # ── Boolean capability flags (used by planner / prompt) ──────────────

    @property
    def has_search_box(self) -> bool:
        return bool(self.search and self.search.found)

    @property
    def has_products(self) -> bool:
        return len(self.products) > 0

    @property
    def has_add_to_cart(self) -> bool:
        """True if any action button looks like an Add-to-Cart / Buy affordance."""
        if not self.actions:
            return False
        cart_kw = ("cart", "buy", "add to bag", "add to basket", "purchase")
        return any(any(k in (a.label or "").lower() for k in cart_kw) for a in self.actions)

    @property
    def has_login_form(self) -> bool:
        """True when the page exposes a login form. We check both the detected
        page_state and the presence of email+password style inputs."""
        if self.page_state == PageState.LOGIN_PAGE:
            return True
        # Fallback: scan element map for 2+ login-shaped inputs
        email_like = 0
        pwd_like = 0
        for elem in self._element_map.values():
            if (elem.tag or "").lower() not in ("input", "textarea"):
                continue
            t = (elem.attributes.get("type") or "").lower()
            if t == "password":
                pwd_like += 1
            elif t in ("email", "text"):
                name = (elem.attributes.get("name") or "").lower()
                if any(k in name for k in ("email", "user", "login", "username")):
                    email_like += 1
        return pwd_like >= 1 and email_like >= 1

    def capability_flags(self) -> dict:
        return {
            "page_type": self.page_state.value,
            "has_search_box": self.has_search_box,
            "has_products": self.has_products,
            "has_add_to_cart": self.has_add_to_cart,
            "has_login_form": self.has_login_form,
        }

    def get_product_by_ordinal(self, ordinal: int) -> Optional[ProductItem]:
        """Get product by 1-based ordinal (1st, 2nd, 3rd...)."""
        if 1 <= ordinal <= len(self.products):
            return self.products[ordinal - 1]
        return None

    def to_prompt(self) -> str:
        """Generate the compact text representation that the LLM sees."""
        lines = []
        lines.append(f"PAGE STATE: {self.page_state.value}")
        lines.append(f"URL: {self.url}")
        lines.append(f"TITLE: {self.title}")
        lines.append(
            f"CAPABILITIES: has_search_box={self.has_search_box} "
            f"has_products={self.has_products} "
            f"has_add_to_cart={self.has_add_to_cart} "
            f"has_login_form={self.has_login_form}"
        )
        lines.append("")

        # Search
        if self.search and self.search.found:
            lines.append(f"SEARCH INPUT: Available (placeholder: \"{self.search.placeholder}\")")
        else:
            lines.append("SEARCH INPUT: Not found on this page")
        lines.append("")

        # Products
        if self.products:
            lines.append(f"ITEMS ON PAGE ({len(self.products)} found):")
            for p in self.products[:20]:  # Cap at 20 to keep prompt small
                price_str = f" - {p.price}" if p.price else ""
                lines.append(f"  {p.rank}. {p.title[:80]}{price_str}")
            lines.append("")

        # Actions
        if self.actions:
            lines.append("AVAILABLE ACTIONS:")
            for a in self.actions:
                lines.append(f"  - {a.label}")
            lines.append("")

        # Filters
        if self.filters:
            lines.append("FILTERS/SORTING:")
            for f in self.filters:
                lines.append(f"  - {f.label}")
            lines.append("")

        # Context
        if self.page_text_summary:
            lines.append("PAGE CONTEXT:")
            lines.append(f"  {self.page_text_summary[:500]}")
            lines.append("")

        if self.error:
            lines.append(f"ERROR: {self.error}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# WorldModelBuilder — the brain
# ═══════════════════════════════════════════════════════════════════════════

PRICE_RE = re.compile(
    r'(?:Rs\.?|PKR|₨|\$|€|£|₹)\s*[\d,]+(?:\.\d+)?|'
    r'[\d,]+(?:\.\d+)?\s*(?:Rs\.?|PKR|₨|\$|€|£|₹)',
    re.IGNORECASE
)

class WorldModelBuilder:
    """Builds a WorldModel from a raw Observation."""

    @staticmethod
    def build(obs: Observation) -> WorldModel:
        """
        Main entry point. Converts raw Observation → structured WorldModel.
        
        Pipeline:
        1. Enrich each element with semantic role
        2. Detect page state
        3. Extract structured groups (search, products, actions, filters)
        4. Build compact WorldModel
        """
        if not obs or obs.error:
            return WorldModel(
                url=obs.url if obs else "",
                title=obs.title if obs else "",
                page_state=PageState.ERROR_PAGE,
                error=obs.error if obs else "No observation",
            )

        # Step 1: Enrich elements
        enriched = [WorldModelBuilder._enrich(e) for e in obs.elements]
        
        # Step 2: Detect page state
        page_state = WorldModelBuilder._detect_page_state(obs.url, enriched, obs.page_text)

        # Step 3: Build element lookup map
        element_map = {e.index: e for e in obs.elements}

        # Step 4: Extract structured groups
        search_info = WorldModelBuilder._extract_search(enriched)
        products = WorldModelBuilder._extract_products(enriched, page_state)
        actions = WorldModelBuilder._extract_actions(enriched)
        filters = WorldModelBuilder._extract_filters(enriched)
        
        # Step 5: Build summary
        summary = WorldModelBuilder._build_summary(obs.page_text, page_state)

        model = WorldModel(
            url=obs.url,
            title=obs.title,
            page_state=page_state,
            search=search_info,
            products=products,
            actions=actions,
            filters=filters,
            page_text_summary=summary,
            _element_map=element_map,
        )

        logger.info(
            f"[WorldModel] {page_state.value} | "
            f"search={'✓' if search_info and search_info.found else '✗'} | "
            f"products={len(products)} | actions={len(actions)} | filters={len(filters)}"
        )

        return model

    # ── Element Enrichment ─────────────────────────────────────────────

    @staticmethod
    def _enrich(elem: PageElement) -> EnrichedElement:
        """Assign semantic role, label, importance, and confidence to an element."""
        tag = (elem.tag or "").lower()
        text = (elem.text or "").lower()
        attrs = elem.attributes or {}
        placeholder = attrs.get("placeholder", "").lower()
        aria = attrs.get("aria-label", "").lower()
        name = attrs.get("name", "").lower()
        input_type = attrs.get("type", "").lower()
        role = attrs.get("role", "").lower()
        nearby = (getattr(elem, "nearby_text", "") or "").lower()

        semantic_role = SemanticRole.UNKNOWN
        label = ""
        importance = 0.3
        confidence = 0.5

        # ── Search Input ──
        if tag in ("input", "textarea"):
            is_search = any([
                input_type == "search",
                "search" in placeholder,
                "search" in aria,
                name in ("q", "query", "search", "search_text"),
                "search" in name,
            ])
            if is_search:
                semantic_role = SemanticRole.SEARCH_INPUT
                label = f"Search Input ({placeholder or aria or 'text field'})"
                importance = 1.0
                confidence = 0.95
            elif input_type in ("email", "password"):
                semantic_role = SemanticRole.LOGIN_INPUT
                label = f"Login {input_type.title()} Input"
                importance = 0.7
                confidence = 0.9
            else:
                semantic_role = SemanticRole.FORM_INPUT
                label = f"Input ({placeholder or name or 'text'})"
                importance = 0.4
                confidence = 0.6

        # ── Buttons ──
        elif tag == "button" or role == "button" or (tag == "input" and input_type in ("button", "submit")):
            cart_keywords = {"add to cart", "add to bag", "buy now", "checkout", "buy", "purchase"}
            search_keywords = {"search", "find", "go"}
            
            if any(k in text or k in aria for k in cart_keywords):
                semantic_role = SemanticRole.ACTION_BUTTON
                label = f"Action: {text.title()[:30]}"
                importance = 1.0
                confidence = 0.95
            elif any(k in text or k in aria for k in search_keywords):
                semantic_role = SemanticRole.SEARCH_BUTTON
                label = f"Search Button"
                importance = 0.8
                confidence = 0.85
            else:
                filter_keywords = {"sort", "filter", "apply", "reset"}
                if any(k in text or k in aria for k in filter_keywords):
                    semantic_role = SemanticRole.FILTER_CONTROL
                    label = f"Filter: {text.title()[:30]}"
                    importance = 0.6
                    confidence = 0.75
                else:
                    semantic_role = SemanticRole.GENERIC_BUTTON
                    label = f"Button: {text.title()[:30]}" if text else "Button"
                    importance = 0.3
                    confidence = 0.5

        # ── Links ──
        elif tag == "a":
            href = attrs.get("href", "").lower()
            
            # Check for product signals
            has_price = bool(PRICE_RE.search(text) or PRICE_RE.search(nearby))
            has_product_href = any(k in href for k in ["/p/", "/product", "/item", "/dp/"])
            is_substantial = len(text) > 10

            if has_price or has_product_href:
                semantic_role = SemanticRole.PRODUCT_CARD
                label = text[:60]
                importance = 0.9
                confidence = 0.85 if has_price else 0.7
            elif any(k in text for k in ["sort", "filter", "price", "low to high", "high to low"]):
                semantic_role = SemanticRole.FILTER_CONTROL
                label = f"Filter: {text[:30]}"
                importance = 0.6
                confidence = 0.75
            elif is_substantial and not WorldModelBuilder._is_nav_noise(text, href):
                # Could be a product or content card even without explicit price
                semantic_role = SemanticRole.GENERIC_LINK
                label = text[:60]
                importance = 0.5
                confidence = 0.5
            else:
                semantic_role = SemanticRole.NAVIGATION_LINK
                label = text[:40] if text else href[:40]
                importance = 0.1
                confidence = 0.6

        # ── Headings ──
        elif tag in ("h1", "h2", "h3"):
            semantic_role = SemanticRole.HEADING
            label = text[:60]
            importance = 0.2
            confidence = 0.9

        return EnrichedElement(
            source=elem,
            semantic_role=semantic_role,
            inferred_label=label,
            importance=importance,
            confidence=confidence,
        )

    @staticmethod
    def _is_nav_noise(text: str, href: str) -> bool:
        """Detect navigation noise elements that should be de-prioritized."""
        noise = {
            "login", "signup", "sign up", "sign in", "register",
            "about", "contact", "help", "support", "terms", "privacy",
            "policy", "careers", "blog", "faq", "affiliate",
        }
        return any(n in text for n in noise) or any(n in href for n in noise)

    # ── Page State Detection ───────────────────────────────────────────

    @staticmethod
    def _detect_page_state(url: str, enriched: List[EnrichedElement], page_text: str) -> PageState:
        """Determine what kind of page we're on."""
        url_lower = url.lower()
        text_lower = (page_text or "").lower()

        # URL patterns
        if any(k in url_lower for k in ["/cart", "/basket", "/checkout"]):
            return PageState.CART_PAGE
        if any(k in url_lower for k in ["/login", "/signin", "/auth"]):
            return PageState.LOGIN_PAGE
        if any(k in url_lower for k in ["/search", "?q=", "query=", "keyword="]):
            return PageState.SEARCH_RESULTS
        if any(k in url_lower for k in ["/p/", "/product/", "/item/", "/dp/"]):
            return PageState.PRODUCT_PAGE

        # Count semantic roles
        role_counts = {}
        for e in enriched:
            role_counts[e.semantic_role] = role_counts.get(e.semantic_role, 0) + 1

        product_count = role_counts.get(SemanticRole.PRODUCT_CARD, 0)
        action_count = role_counts.get(SemanticRole.ACTION_BUTTON, 0)
        login_count = role_counts.get(SemanticRole.LOGIN_INPUT, 0)
        search_count = role_counts.get(SemanticRole.SEARCH_INPUT, 0)

        # Login page
        if login_count >= 2:
            return PageState.LOGIN_PAGE

        # Product page (single product + CTA)
        if action_count >= 1 and product_count <= 2:
            if any(k in text_lower for k in ["add to cart", "buy now", "add to bag", "quantity"]):
                return PageState.PRODUCT_PAGE

        # Search results (many products)
        if product_count >= 3:
            return PageState.SEARCH_RESULTS

        # Homepage (search bar + minimal products)
        url_parts = url.rstrip("/").split("/")
        if len(url_parts) <= 3 and search_count >= 1:
            return PageState.HOME_PAGE

        return PageState.GENERIC

    # ── Structured Group Extraction ────────────────────────────────────

    @staticmethod
    def _extract_search(enriched: List[EnrichedElement]) -> Optional[SearchInfo]:
        """Extract search input info."""
        for e in enriched:
            if e.semantic_role == SemanticRole.SEARCH_INPUT:
                return SearchInfo(
                    found=True,
                    element_index=e.source.index,
                    css_selector=e.source.css_selector,
                    placeholder=e.source.attributes.get("placeholder", ""),
                )
        return SearchInfo(found=False)

    @staticmethod
    def _extract_products(enriched: List[EnrichedElement], page_state: PageState) -> List[ProductItem]:
        """Extract product/item cards as an ordered list."""
        candidates = []
        
        for e in enriched:
            if e.semantic_role == SemanticRole.PRODUCT_CARD:
                candidates.append(e)
            # On search results pages, substantial generic links might be items too
            elif (page_state == PageState.SEARCH_RESULTS 
                  and e.semantic_role == SemanticRole.GENERIC_LINK
                  and e.importance >= 0.5):
                candidates.append(e)

        # Sort by bounding box Y position (top to bottom) for natural ordering
        def sort_key(e: EnrichedElement):
            box = getattr(e.source, "bounding_box", None) or {}
            return (box.get("y", 9999), box.get("x", 0))
        
        candidates.sort(key=sort_key)

        products = []
        for rank, e in enumerate(candidates, start=1):
            text = e.source.text or ""
            
            # Try to extract price from text or nearby text
            price = ""
            nearby = getattr(e.source, "nearby_text", "") or ""
            price_match = PRICE_RE.search(text) or PRICE_RE.search(nearby)
            if price_match:
                price = price_match.group(0).strip()

            # Clean title: remove price from title text
            title = text
            if price and price in title:
                title = title.replace(price, "").strip()
            title = " ".join(title.split())[:80]  # Normalize whitespace, cap length

            products.append(ProductItem(
                rank=rank,
                title=title if title else f"Item {rank}",
                price=price,
                element_index=e.source.index,
                css_selector=e.source.css_selector,
            ))

        return products

    @staticmethod
    def _extract_actions(enriched: List[EnrichedElement]) -> List[ActionItem]:
        """Extract actionable buttons (add to cart, buy now, etc.)."""
        actions = []
        for e in enriched:
            if e.semantic_role == SemanticRole.ACTION_BUTTON:
                actions.append(ActionItem(
                    label=e.inferred_label or e.source.text[:40] or "Action",
                    element_index=e.source.index,
                    css_selector=e.source.css_selector,
                ))
        return actions

    @staticmethod
    def _extract_filters(enriched: List[EnrichedElement]) -> List[FilterItem]:
        """Extract filter/sort controls."""
        filters = []
        for e in enriched:
            if e.semantic_role == SemanticRole.FILTER_CONTROL:
                filters.append(FilterItem(
                    label=e.inferred_label or e.source.text[:40] or "Filter",
                    element_index=e.source.index,
                    css_selector=e.source.css_selector,
                ))
        return filters

    @staticmethod
    def _build_summary(page_text: str, page_state: PageState) -> str:
        """Build a brief contextual summary of the page."""
        if not page_text:
            return ""
        # Take first 400 chars, clean up
        text = " ".join(page_text.split())[:400]
        return text


# ═══════════════════════════════════════════════════════════════════════════
# Durable-fact extraction helpers
# Used by SessionState.update_from_world_model to maintain session-level
# truth (cart, login state, active product) across page transitions.
# ═══════════════════════════════════════════════════════════════════════════

LOGOUT_MARKERS = (
    "log out", "logout", "sign out", "signout", "my account",
    "my orders", "your account",
)

LOGIN_LANDING_MARKERS = (
    "sign in", "log in", "login", "forgot password", "create account",
)


def detect_logged_in(wm: WorldModel) -> bool:
    """Heuristic login detection. Returns True only when the page exposes a
    clear logout affordance (conservative — we don't want false positives)."""
    if wm is None:
        return False

    # If we're ON a login page, we are not logged in — unambiguous signal.
    if wm.page_state == PageState.LOGIN_PAGE:
        return False

    # Scan actions, filters, and page text for logout markers
    haystack_parts = []
    for a in (wm.actions or []):
        haystack_parts.append((a.label or "").lower())
    for f in (wm.filters or []):
        haystack_parts.append((f.label or "").lower())

    # Labels alone are a strong signal
    combined = " | ".join(haystack_parts)
    for m in LOGOUT_MARKERS:
        if m in combined:
            return True

    # Page text is noisy — require logout verb, not just "my account"
    text = (wm.page_text_summary or "").lower()
    if "log out" in text or "sign out" in text or "logout" in text:
        return True

    return False


def first_price(wm: WorldModel) -> str:
    """Extract the most prominent price from the current page for the
    currently_viewing entity. On a product page the first product card's
    price is usually the main price; fall back to regex over page text."""
    if wm is None:
        return ""
    if wm.products:
        for p in wm.products:
            if p.price:
                return p.price
    # fallback: regex against page text summary
    m = PRICE_RE.search(wm.page_text_summary or "")
    if m:
        return m.group(0).strip()
    return ""


CART_QTY_RE = re.compile(r"\b(?:qty|quantity)[:\s]*(\d+)\b", re.IGNORECASE)


def extract_cart_items(wm: WorldModel):
    """Extract cart contents from a CART_PAGE WorldModel.

    Returns a list[CartItem] or None if we can't confidently parse.
    Rationale: trust the DOM over any local state — if we reach the cart
    page we rebuild the cart from what's actually there.
    """
    # Lazy import to avoid cycle
    try:
        from core.session_state import CartItem
    except ImportError:
        from .session_state import CartItem

    if wm is None or wm.page_state != PageState.CART_PAGE:
        return None

    items = []
    # Reuse the same product extraction — cart line items are structurally
    # similar to product cards (title + price, often with a qty control).
    for p in wm.products or []:
        if not p.title or len(p.title) < 3:
            continue
        qty = 1
        # Try to parse quantity from the page text near this item — best-effort
        m = CART_QTY_RE.search(p.title)
        if m:
            try:
                qty = max(1, int(m.group(1)))
            except Exception:
                qty = 1
        items.append(CartItem(
            title=p.title,
            price=p.price,
            quantity=qty,
        ))

    # Safety: never clobber an existing cart with 0 parsed items unless the
    # page really is empty (keyword "your cart is empty")
    text = (wm.page_text_summary or "").lower()
    if not items and ("cart is empty" in text or "no items" in text or "basket is empty" in text):
        return []

    # If we got nothing but the page isn't flagged empty, refuse to update.
    if not items:
        return None

    return items
