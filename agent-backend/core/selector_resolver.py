"""
Selector Resolver: Robust dynamic selector resolution.
Extends ActionMapper with smarter strategies for finding elements.

Strategies:
1. CSS selectors (standard)
2. Text matching (buttons/links with specific text)
3. ARIA labels
4. Placeholder text
5. Role attributes
6. Visual heuristics (first, nth-child, etc.)
"""

from typing import Optional, List
from playwright.async_api import Page, Locator

try:
    from utils import get_logger
except ImportError:
    from ..utils import get_logger


logger = get_logger(__name__)


class SelectorStrategy:
    """Container for selector resolution strategies."""
    
    # Text patterns for common elements
    TEXT_PATTERNS = {
        "search_button": ["Search", "Find", "Go", "Submit"],
        "add_to_cart": ["Add to cart", "Add to Cart", "Add to Basket", "Add to Bag", "Add Item"],
        "next_button": ["Next", "Next Page", "Load More", "See More"],
        "previous_button": ["Previous", "Prev", "Back", "Previous Page"],
        "submit_button": ["Submit", "Send", "Apply", "Confirm", "Save"],
        "close_button": ["Close", "Dismiss", "Cancel", "X", "×"],
        "checkout_button": ["Checkout", "Check out", "Buy now", "Pay", "Purchase"],
    }


class SelectorResolver:
    """
    Improved selector resolution with multiple fallback strategies.
    """
    
    @staticmethod
    async def resolve_selector(
        page: Page,
        selector: str,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        Resolve a logical selector to a CSS selector using multiple strategies.
        
        Tries strategies in order:
        1. Exact CSS selector
        2. Text-based button matching
        3. ARIA label matching
        4. Placeholder attribute
        5. Data attributes
        6. Role-based resolution
        7. Visual heuristics
        
        Args:
            page: Playwright page
            selector: Logical selector (e.g., "search_box", "first_product")
            max_retries: Number of resolution attempts
            
        Returns:
            Resolved CSS selector or None
        """
        selector_lower = selector.lower().strip()
        
        # Try multiple resolution strategies
        for strategy_name, strategy_func in [
            ("direct_css", SelectorResolver._try_direct_css),
            ("text_based", SelectorResolver._try_text_based),
            ("aria_label", SelectorResolver._try_aria_label),
            ("placeholder", SelectorResolver._try_placeholder),
            ("role_based", SelectorResolver._try_role_based),
            ("data_attr", SelectorResolver._try_data_attr),
            ("visual_heuristic", SelectorResolver._try_visual_heuristic),
        ]:
            try:
                result = await strategy_func(page, selector_lower)
                if result:
                    logger.debug(f"Resolved '{selector}' using strategy: {strategy_name} → {result}")
                    return result
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} failed: {e}")
                continue
        
        logger.warning(f"Could not resolve selector: {selector}")
        return None
    
    @staticmethod
    async def _try_direct_css(page: Page, selector: str) -> Optional[str]:
        """Try using selector as direct CSS selector."""
        try:
            count = await page.locator(selector).count()
            if count > 0:
                return selector
        except Exception:
            pass
        return None
    
    @staticmethod
    async def _try_text_based(page: Page, selector: str) -> Optional[str]:
        """Try matching by button/link text content."""
        # Map logical names to text patterns
        text_map = {
            "search_box": ["Search", "search"],
            "search_button": SelectorStrategy.TEXT_PATTERNS["search_button"],
            "add_to_cart": SelectorStrategy.TEXT_PATTERNS["add_to_cart"],
            "first_result": None,  # Handled separately
            "first_product": None,
            "next_button": SelectorStrategy.TEXT_PATTERNS["next_button"],
            "close_button": SelectorStrategy.TEXT_PATTERNS["close_button"],
        }
        
        if selector not in text_map:
            return None
        
        texts = text_map.get(selector)
        if not texts:
            return None
        
        # Try each text pattern
        for text in texts:
            try:
                # Try button first
                button_selector = f'button:has-text("{text}")'
                if await page.locator(button_selector).count() > 0:
                    return button_selector
                
                # Try link
                link_selector = f'a:has-text("{text}")'
                if await page.locator(link_selector).count() > 0:
                    return link_selector
                
                # Try input with value
                input_selector = f'input[value="{text}" i]'
                if await page.locator(input_selector).count() > 0:
                    return input_selector
            except Exception:
                continue
        
        return None
    
    @staticmethod
    async def _try_aria_label(page: Page, selector: str) -> Optional[str]:
        """Try matching by ARIA label."""
        aria_map = {
            "close_button": "close",
            "next_button": "next",
            "previous_button": "previous",
            "search_box": "search",
        }
        
        aria_label = aria_map.get(selector)
        if not aria_label:
            return None
        
        try:
            selector_css = f'[aria-label*="{aria_label}" i]'
            if await page.locator(selector_css).count() > 0:
                return selector_css
        except Exception:
            pass
        
        return None
    
    @staticmethod
    async def _try_placeholder(page: Page, selector: str) -> Optional[str]:
        """Try matching by placeholder attribute."""
        placeholder_map = {
            "search_box": "search",
            "email_input": "email",
            "password_input": "password",
        }
        
        placeholder = placeholder_map.get(selector)
        if not placeholder:
            return None
        
        try:
            selector_css = f'input[placeholder*="{placeholder}" i]'
            if await page.locator(selector_css).count() > 0:
                return selector_css
        except Exception:
            pass
        
        return None
    
    @staticmethod
    async def _try_role_based(page: Page, selector: str) -> Optional[str]:
        """Try matching by ARIA role."""
        role_map = {
            "search_box": "searchbox",
            "close_button": "button",
        }
        
        role = role_map.get(selector)
        if not role:
            return None
        
        try:
            selector_css = f'[role="{role}"]'
            if await page.locator(selector_css).count() > 0:
                return selector_css
        except Exception:
            pass
        
        return None
    
    @staticmethod
    async def _try_data_attr(page: Page, selector: str) -> Optional[str]:
        """Try matching by data attributes."""
        data_map = {
            "add_to_cart": "add-to-cart",
            "search_button": "search",
            "first_product": "product",
        }
        
        data_attr = data_map.get(selector)
        if not data_attr:
            return None
        
        try:
            # Try data-action, data-id, data-test, etc.
            for prefix in ["data-action", "data-id", "data-testid", "data-test"]:
                selector_css = f'[{prefix}*="{data_attr}" i]'
                if await page.locator(selector_css).count() > 0:
                    return selector_css
        except Exception:
            pass
        
        return None
    
    @staticmethod
    async def _try_visual_heuristic(page: Page, selector: str) -> Optional[str]:
        """Try visual heuristics: first, nth-child, etc."""
        
        # "first_*" patterns
        if selector.startswith("first_"):
            element_type = selector.replace("first_", "")
            
            heuristics = {
                "product": [
                    'div[class*="product" i]:nth-child(1)',
                    'li[class*="product" i]:nth-child(1)',
                    'article[class*="product" i]:nth-child(1)',
                    'a[href*="product" i]:nth-child(1)',
                ],
                "result": [
                    'a[href*="search" i]:nth-child(1)',
                    '.search-result:nth-child(1) a',
                    'h3 > a:nth-child(1)',
                ],
                "item": [
                    'div[class*="item" i]:nth-child(1)',
                    'li[class*="item" i]:nth-child(1)',
                ],
                "link": ['a:nth-child(1)'],
            }
            
            selectors = heuristics.get(element_type, [])
            for selector_css in selectors:
                try:
                    if await page.locator(selector_css).count() > 0:
                        return selector_css
                except Exception:
                    continue
        
        # "nth_*" patterns (second, third, etc.)
        ordinal_map = {
            "second_": 2,
            "third_": 3,
            "fourth_": 4,
            "fifth_": 5,
        }
        
        for ordinal_prefix, position in ordinal_map.items():
            if selector.startswith(ordinal_prefix):
                element_type = selector.replace(ordinal_prefix, "")
                
                heuristics = {
                    "product": f'div[class*="product" i]:nth-child({position})',
                    "result": f'a[href*="search" i]:nth-child({position})',
                    "item": f'div[class*="item" i]:nth-child({position})',
                }
                
                selector_css = heuristics.get(element_type)
                if selector_css:
                    try:
                        if await page.locator(selector_css).count() > 0:
                            return selector_css
                    except Exception:
                        pass
        
        return None
    
    @staticmethod
    async def find_element_by_text(
        page: Page,
        text: str,
        element_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Find an element containing specific text.
        
        Args:
            page: Playwright page
            text: Text to search for
            element_type: Optional element type (button, link, etc.)
            
        Returns:
            Resolved CSS selector or None
        """
        selectors_to_try = []
        
        if element_type:
            selectors_to_try = [
                f'{element_type}:has-text("{text}")',
                f'{element_type}:has-text("{text.lower()}")',
            ]
        else:
            selectors_to_try = [
                f'button:has-text("{text}")',
                f'a:has-text("{text}")',
                f'input:has-text("{text}")',
                f'[role="button"]:has-text("{text}")',
            ]
        
        for selector_css in selectors_to_try:
            try:
                if await page.locator(selector_css).count() > 0:
                    return selector_css
            except Exception:
                continue
        
        return None
    
    @staticmethod
    async def find_all_clickables(page: Page) -> List[str]:
        """
        Find all clickable elements on the page (for debugging).
        
        Returns:
            List of element descriptions
        """
        try:
            # Get buttons, links, and interactive elements
            buttons = await page.locator("button").all()
            links = await page.locator("a[href]").all()
            
            clickables = []
            for btn in buttons[:5]:  # First 5
                text = await btn.text_content()
                if text:
                    clickables.append(f"button: {text.strip()[:30]}")
            
            for link in links[:5]:  # First 5
                text = await link.text_content()
                href = await link.get_attribute("href")
                if text:
                    clickables.append(f"link: {text.strip()[:30]} ({href})")
            
            return clickables
        except Exception as e:
            logger.debug(f"Error finding clickables: {e}")
            return []
