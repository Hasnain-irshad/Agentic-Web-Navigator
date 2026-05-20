"""
Element Grouper: Groups raw DOM elements into semantic categories.
"""

from typing import List, Dict
from core.observation_extractor import PageElement
import re

try:
    from utils import get_logger
except ImportError:
    from ..utils import get_logger

logger = get_logger(__name__)

def is_search_element(e: PageElement) -> bool:
    tag = (e.tag or "").lower()
    attrs = e.attributes or {}
    text = (e.text or "").lower()
    
    if tag not in ("input", "textarea"): return False
    
    has_search_attr = any([
        "search" in attrs.get("type", "").lower(),
        "search" in attrs.get("placeholder", "").lower(),
        "search" in attrs.get("aria-label", "").lower(),
        "q" == attrs.get("name", "").lower() or "search" in attrs.get("name", "").lower()
    ])
    
    return has_search_attr or "search" in text

def is_nav_element(e: PageElement) -> bool:
    tag = (e.tag or "").lower()
    text = (e.text or "").lower()
    box = getattr(e, "bounding_box", {}) or {}
    y = box.get("y", -1)
    
    if y != -1 and (y < 200 or y > 2500):
        # Header/Footer bounds
        if tag == "a" or tag == "li":
            return True
            
    nav_keywords = {"login", "signup", "about", "contact", "help", "terms", "policy", "category"}
    return any(k in text for k in nav_keywords)

def is_action_element(e: PageElement) -> bool:
    tag = (e.tag or "").lower()
    attrs = e.attributes or {}
    text = (e.text or "").lower()
    
    is_btn = tag == "button" or attrs.get("role") == "button" or attrs.get("type") in ("button", "submit")
    action_words = {"add to cart", "buy now", "checkout", "submit", "apply", "continue"}
    
    return is_btn and any(w in text or w in attrs.get("aria-label", "").lower() for w in action_words)

def is_filter_element(e: PageElement) -> bool:
    text = (e.text or "").lower()
    attrs = e.attributes or {}
    
    filter_words = {"sort", "filter", "price low", "price high", "order by", "category"}
    return any(w in text or w in attrs.get("aria-label", "").lower() for w in filter_words)

def is_product_element(e: PageElement) -> bool:
    tag = (e.tag or "").lower()
    text = (e.text or "").lower()
    nearby = (getattr(e, "nearby_text", "") or "").lower()
    
    price_markers = ["$", "€", "£", "₹", "rs", "pkr", "₨", "/-"]
    has_price = any(p in text or p in nearby for p in price_markers)
    
    # Articles / lists usually have substantial text length
    has_substance = len(text) > 15
    
    is_clickable = tag in ("a", "div", "li", "button")
    
    return (has_price or has_substance) and is_clickable


def group_elements(elements: List[PageElement], page_type: str) -> Dict[str, List[PageElement]]:
    """
    Groups elements semantically. Elements can theoretically appear in multiple groups
    if they span boundaries, but we try to resolve exclusively.
    """
    groups = {
        "search": [],
        "products": [],
        "actions": [],
        "filters": [],
        "navigation": [],
        "generic": []
    }
    
    for e in elements:
        placed = False
        
        # 1. Search (Input fields)
        if is_search_element(e):
            groups["search"].append(e)
            placed = True
            
        # 2. Actions (CTAs)
        elif is_action_element(e):
            groups["actions"].append(e)
            placed = True
            
        # 3. Filters
        elif is_filter_element(e):
            groups["filters"].append(e)
            placed = True
            
        # 4. Products/Grid (Only if not nav or explicitly action)
        elif is_product_element(e) and not is_nav_element(e):
            groups["products"].append(e)
            placed = True
            
        # 5. Navigation
        elif is_nav_element(e):
            groups["navigation"].append(e)
            placed = True
            
        # Fallback Generic
        if not placed:
            groups["generic"].append(e)
            
    return groups

