"""
Element Resolver: Production-Grade General-Purpose DOM Element Resolution.
Multi-factor, intent-aware scoring system. Works universally across any website.
"""

import re
from enum import Enum
from typing import Optional, List, Tuple, Dict
from difflib import SequenceMatcher

try:
    from utils import get_logger
    from core.observation_extractor import PageElement
except ImportError:
    from ..utils import get_logger
    from .observation_extractor import PageElement

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Intent Types
# ═══════════════════════════════════════════════════════════════════════════

class IntentType(Enum):
    SEARCH_INPUT = "search_input"
    PRODUCT_CLICK = "product_click"
    ADD_TO_CART = "add_to_cart"
    NAVIGATION = "navigation"
    FILTER_SORT = "filter_sort"
    GENERIC = "generic"

def detect_intent(text: str) -> IntentType:
    t = text.lower()
    if any(kw in t for kw in ["search_input", "search box", "type search", "search query"]):
        return IntentType.SEARCH_INPUT
    if any(kw in t for kw in ["add_to_cart", "add to cart", "buy now", "purchase"]):
        return IntentType.ADD_TO_CART
    if any(kw in t for kw in ["filter", "sort", "order by", "price low to high"]):
        return IntentType.FILTER_SORT
    if any(kw in t for kw in ["nav", "go to", "open link"]):
        return IntentType.NAVIGATION
    if any(kw in t for kw in ["product", "item", "result", "listing", "article", "first_", "second_"]):
        return IntentType.PRODUCT_CLICK
    return IntentType.GENERIC


# ═══════════════════════════════════════════════════════════════════════════
# Generic Utilities
# ═══════════════════════════════════════════════════════════════════════════

def fuzzy_match_ratio(query: str, target: str) -> float:
    if not query or not target:
        return 0.0
    return SequenceMatcher(None, query.lower(), target.lower()).ratio()


# ═══════════════════════════════════════════════════════════════════════════
# Multi-Factor Core Engine
# ═══════════════════════════════════════════════════════════════════════════

class ElementResolver:
    """Production-grade element resolver using multi-signal weighted scoring."""
    
    @staticmethod
    def resolve(grouped_elements: Dict[str, List[PageElement]], intent_type: IntentType, query: str = "", page_type: str = "generic", relax_filters: bool = False) -> List[Tuple[PageElement, float]]:
        """
        Main routing function. Pre-filters elements and scores candidates dynamically via strict group-mapping.
        Returns sorted Top 5 tuple list.
        """
        # Mapping: intent to specific group
        target_group = []
        if intent_type == IntentType.SEARCH_INPUT:
            target_group = grouped_elements.get("search", [])
        elif intent_type == IntentType.PRODUCT_CLICK:
            target_group = grouped_elements.get("products", [])
        elif intent_type == IntentType.ADD_TO_CART:
            target_group = grouped_elements.get("actions", [])
        elif intent_type == IntentType.FILTER_SORT:
            target_group = grouped_elements.get("filters", [])
        elif intent_type == IntentType.NAVIGATION:
            target_group = grouped_elements.get("navigation", [])
            
        # Fallback to general pool if the required structural group fails constraints
        if not target_group or relax_filters:
            target_group = []
            for g in grouped_elements.values():
                target_group.extend(g)
            
        filtered_elements = target_group

        # ── Strong Pre-Filtering (unless relaxed) ──
        if not relax_filters and intent_type not in (IntentType.NAVIGATION, IntentType.SEARCH_INPUT, IntentType.GENERIC):
            filtered_elements = [
                e for e in filtered_elements if not ElementResolver._is_junk_navigation(e)
            ]
            
        scored_elements = []
        for elem in filtered_elements:
            score_data = ElementResolver._compute_factors(elem, intent_type, query)
            
            # Apply formula: Step 5 Final Score
            final_score = (
                (0.30 * score_data["text_score"]) +
                (0.25 * score_data["attribute_score"]) +
                (0.20 * score_data["type_priority"]) +
                (0.15 * score_data["actionability"]) +
                (0.10 * score_data["context_score"]) +
                score_data["positional_offset"]  # Add absolute flat modifiers from heuristics
            )
            
            # Drop severely penalized elements
            if final_score > 0:
                scored_elements.append((elem, final_score, score_data))

        # Sort descending
        scored_elements.sort(key=lambda x: x[1], reverse=True)
        
        # Log Top 5 candidates with reasoning
        logger.info(f"  [RESOLVER DEBUG] Intent: {intent_type.name} | Query: '{query}'")
        for i, (elem, score, data) in enumerate(scored_elements[:5]):
            logger.info(f"    #{i+1}: '[{elem.tag}] {elem.text[:30]}' (Score: {score:.2f})")
            logger.info(f"        -> text:{data['text_score']:.1f} attr:{data['attribute_score']:.1f} "
                        f"type:{data['type_priority']:.1f} act:{data['actionability']:.1f} pos:{data['positional_offset']:.1f}")
        
        # Return standard tuple
        return [(e, s) for e, s, _ in scored_elements]


    @staticmethod
    def _is_junk_navigation(element: PageElement) -> bool:
        """Filters out generic noise (header/footer, about us, policies) before ranking."""
        text = (element.text or "").lower()
        
        # Textual heuristics
        junk_terms = {"privacy policy", "terms of service", "about us", "contact us", "help center", "login", "signup"}
        if any(term in text for term in junk_terms):
            return True
            
        # Positional heuristics
        box = getattr(element, "bounding_box", {}) or {}
        y = box.get("y", -1)
        if y != -1:
            if y > 4000: # Typical deep footer range bounds heuristic
                return True
                
        return False

    @staticmethod
    def _compute_factors(element: PageElement, intent_type: IntentType, query: str) -> Dict[str, float]:
        """Compute the independent 5-factor scores for a specific element."""
        return {
            "text_score": ElementResolver._score_text(element, query),
            "attribute_score": ElementResolver._score_attributes(element, intent_type, query),
            "type_priority": ElementResolver._score_type(element, intent_type),
            "actionability": ElementResolver._score_actionability(element),
            "context_score": ElementResolver._score_context(element, query),
            "positional_offset": ElementResolver._score_position(element, intent_type)
        }

    # ── FACTOR 1: TEXT MATCH (Weak Signal natively, relies on difflib) ──
    @staticmethod
    def _score_text(element: PageElement, query: str) -> float:
        text = (element.text or "").lower()
        if not text or not query:
            return 0.0
            
        words = query.lower().split()
        match_count = sum(1 for w in words if len(w) > 2 and w in text)
        base = (match_count / max(1, len(words))) * 50.0  # up to 50 pts
        
        fuzzy = fuzzy_match_ratio(query, text) * 50.0
        return base + fuzzy

    # ── FACTOR 2: ATTRIBUTE MATCH (Strong Signal) ──
    @staticmethod
    def _score_attributes(element: PageElement, intent_type: IntentType, query: str) -> float:
        score = 0.0
        attrs = element.attributes or {}
        combined_attrs = " ".join(str(v) for v in attrs.values()).lower()
        
        # Intent specific attribute hints
        if intent_type == IntentType.SEARCH_INPUT:
            if attrs.get("type", "").lower() in ("search", "text"): score += 40.0
            if "search" in attrs.get("placeholder", "").lower(): score += 30.0
            if "search" in attrs.get("aria-label", "").lower(): score += 30.0
            if "search" in attrs.get("name", "").lower() or "q" == attrs.get("name", "").lower(): score += 20.0
            
        elif intent_type == IntentType.ADD_TO_CART:
            if any(k in combined_attrs for k in ["cart", "add", "buy"]): score += 50.0
                
        elif intent_type == IntentType.FILTER_SORT:
            if any(k in combined_attrs for k in ["sort", "filter", "order"]): score += 50.0
            
        # General query overlap
        for word in query.lower().split():
            if len(word) > 3 and word in combined_attrs:
                score += 15.0
                
        return min(score, 100.0)

    # ── FACTOR 3: ELEMENT TYPE PRIORITY (Crucial Rules) ──
    @staticmethod
    def _score_type(element: PageElement, intent_type: IntentType) -> float:
        tag = (element.tag or "").lower()
        role = (element.attributes.get("role") or "").lower()
        
        if intent_type == IntentType.SEARCH_INPUT:
            if tag == "input": return 100.0
            if tag == "textarea": return 60.0
            if role == "searchbox": return 80.0
            return -50.0 # Heavily penalize non-inputs
            
        if intent_type == IntentType.ADD_TO_CART or intent_type == IntentType.FILTER_SORT:
            if tag == "button" or role == "button" or (tag == "input" and element.attributes.get("type") in ("button", "submit")):
                return 100.0
            if tag == "a": return 40.0
            if tag == "div": return 10.0 # Clickable div
            return -20.0
            
        if intent_type == IntentType.PRODUCT_CLICK or intent_type == IntentType.NAVIGATION:
            if tag == "a": return 100.0
            if tag == "button": return 50.0
            if tag in ("div", "li"): return 20.0
            return 0.0
            
        return 50.0 # Generic neutral

    # ── FACTOR 4: ACTIONABILITY SCORE ──
    @staticmethod
    def _score_actionability(element: PageElement) -> float:
        score = 0.0
        if getattr(element, "is_clickable", False):
            score += 100.0
        
        if element.attributes.get("disabled") is not None:
            score -= 100.0
            
        return score

    # ── FACTOR 5: POSITIONAL SIGNAL & OFFSETS ──
    @staticmethod
    def _score_position(element: PageElement, intent_type: IntentType) -> float:
        box = getattr(element, "bounding_box", {}) or {}
        y = box.get("y", -1)
        if y == -1: return 0.0
        
        # Absolute Positional Offset Modifiers
        if intent_type == IntentType.SEARCH_INPUT:
            # Searches are generally at the top (Y < 200)
            if y < 200: return +15.0
            if y > 1000: return -20.0
            
        if intent_type == IntentType.PRODUCT_CLICK:
            # Grids live in center viewports generally
            if y < 100: return -10.0 # Not header nav
            if 300 < y < 2500: return +10.0
            
        return 0.0

    # ── FACTOR 6: CONTEXT MATCH ──
    @staticmethod
    def _score_context(element: PageElement, query: str) -> float:
        nearby = (getattr(element, "nearby_text", "")).lower()
        if not nearby: return 0.0
        
        score = 0.0
        # If nearby context contains pricing, boost for products
        if any(sym in nearby for sym in ["$", "€", "£", "₹", "rs.", "pkr", "₨"]):
            score += 30.0
            
        if query:
            words = query.lower().split()
            match_count = sum(1 for w in words if len(w) > 2 and w in nearby)
            score += (match_count / max(1, len(words))) * 40.0
            
        return min(score, 100.0)

# ═══════════════════════════════════════════════════════════════════════════
# Ordinal Parsing
# ═══════════════════════════════════════════════════════════════════════════

ORDINAL_MAP = {
    "first": 0, "1st": 0, "1": 0, "second": 1, "2nd": 1, "2": 1,
    "third": 2, "3rd": 2, "3": 2, "fourth": 3, "4th": 3, "4": 3,
    "fifth": 4, "5th": 4, "5": 5, "sixth": 5, "6th": 5, "6": 5,
}

ORDINAL_RE = re.compile(r"\b(first|second|third|fourth|fifth|sixth|1st|2nd|3rd|4th|5th|6th|(\d+)(?:st|nd|rd|th)?)\b", re.IGNORECASE)

def parse_ordinal(text: str) -> Optional[int]:
    m = ORDINAL_RE.search(text.lower())
    if not m: return None
    word = m.group(1).lower()
    if word in ORDINAL_MAP: return ORDINAL_MAP[word]
    if m.group(2): return int(m.group(2)) - 1
    return None

def validate_element_basic(element: PageElement, intent_type: IntentType) -> bool:
    """Basic sanity stop."""
    if intent_type == IntentType.SEARCH_INPUT:
        return (element.tag or "").lower() in ("input", "textarea")
    return True
