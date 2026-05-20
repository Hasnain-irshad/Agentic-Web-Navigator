"""
Page Detector: Determines the semantic type of the current page based on context and URL.
"""

from core.observation_extractor import PageElement
from typing import List

try:
    from utils import get_logger
except ImportError:
    from ..utils import get_logger

logger = get_logger(__name__)

def detect_page_type(url: str, elements: List[PageElement], page_text: str) -> str:
    """
    Detects the semantic page type.
    Returns: 'homepage', 'search_results', 'product_page', 'generic'
    """
    url_lower = url.lower()
    text_lower = page_text.lower()
    
    # URL Heuristics
    if any(k in url_lower for k in ["/search", "?q=", "query=", "search?"]):
        if not "/p/" in url_lower and not "/product" in url_lower:
            return "search_results"
            
    if any(k in url_lower for k in ["/p/", "/product/", "/item/"]):
        return "product_page"
        
    # Element Heuristics
    price_markers = ["$", "€", "£", "₹", "rs", "pkr", "₨", "/-"]
    
    # Check for heavy presence of pricing and "add to cart" CTAs
    add_to_cart_count = sum(1 for e in elements if "cart" in (e.text or "").lower() or "add to bag" in (e.text or "").lower() or "buy" in (e.text or "").lower())
    price_count = sum(1 for e in elements if any(p in (e.text or "").lower() or p in (getattr(e, "nearby_text", "") or "").lower() for p in price_markers))
    
    if add_to_cart_count > 0 and price_count > 0:
        return "product_page"
        
    # Count identical class names (Grid structures)
    class_counts = {}
    for e in elements:
        c = (e.attributes or {}).get("class", "")
        if c:
            class_counts[c] = class_counts.get(c, 0) + 1
            
    has_grid = any(count > 4 for count in class_counts.values())
    
    if has_grid and price_count >= 3:
        return "search_results"
        
    # If URL is very short, likely homepage
    url_parts = url.rstrip("/").split("/")
    if len(url_parts) <= 3: # e.g. https://www.daraz.pk
        return "homepage"
        
    return "generic"
