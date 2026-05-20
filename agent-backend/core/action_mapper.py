"""
Action Mapper: Maps logical selectors to DOM elements.
Provides robust element resolution for browser automation.
"""

from typing import Optional
from playwright.async_api import Page

try:
    from utils import get_logger
except ImportError:
    from ..utils import get_logger


logger = get_logger(__name__)


class ActionMapper:
    """
    Maps logical, human-friendly selectors to actual DOM elements.
    Provides intelligent element resolution for browser automation.
    """
    
    # Mapping of logical selectors to CSS selector candidates and search strategies
    SELECTOR_PATTERNS = {
        "search_box": {
            "selectors": [
                'input[placeholder*="search" i]',
                'input[placeholder*="Search" i]',
                'input[name="q"]',
                'input[name="s"]',
                'input[name="search"]',
                'input[type="search"]',
                'input.search',
                'input[aria-label*="search" i]',
                'input[class*="search" i]',
                '[role="searchbox"]',
            ],
            "fallback_text": ["Search", "search"],
        },
        "first_result": {
            "selectors": [
                'a[href*="search" i]',
                '.search-result:nth-child(1) a',
                '.result-item:first-child',
                'div[data-result-item]:first-child a',
                'h3 > a:first-of-type',
            ],
            "fallback_click_all_links": True,
        },
        "first_product": {
            "selectors": [
                'a[href*="product" i]',
                'div[class*="product" i]:first-child a',
                'article[class*="product" i]:first-child a',
                'li[class*="product" i]:first-child a',
                '[data-product]:first-child',
            ],
        },
        "first_item": {
            "selectors": [
                'div[class*="item" i]:first-child',
                'li[class*="item" i]:first-child',
                'article[class*="item" i]:first-child',
            ],
        },
        "add_to_cart": {
            "selectors": [
                'button:has-text("Add to cart")',
                'button:has-text("Add to Cart")',
                'button:has-text("Add to Basket")',
                'button:has-text("Add to Bag")',
                'a:has-text("Add to cart")',
                'input[value*="Add to" i]',
                'button[class*="add" i][class*="cart" i]',
                '[data-action="add-to-cart"]',
            ],
            "fallback_text": ["Add to cart", "ADD TO CART", "Add to Basket"],
        },
        "second_product": {
            "selectors": [
                'div[class*="product" i]:nth-child(2) a',
                'li[class*="product" i]:nth-child(2) a',
            ],
        },
        "third_product": {
            "selectors": [
                'div[class*="product" i]:nth-child(3) a',
                'li[class*="product" i]:nth-child(3) a',
            ],
        },
        "next_button": {
            "selectors": [
                'button:has-text("Next")',
                'a:has-text("Next")',
                '[aria-label*="Next"]',
                'button[class*="next" i]',
            ],
            "fallback_text": ["Next", "NEXT"],
        },
        "close_button": {
            "selectors": [
                'button[aria-label*="close" i]',
                'button[aria-label*="dismiss" i]',
                'button.close',
                'button[class*="close" i]',
                'svg[class*="close" i]',
            ],
            "fallback_text": ["Close", "CLOSE", "✕", "×"],
        },
    }
    
    @staticmethod
    async def resolve_selector(
        page: Page,
        selector: str,
    ) -> Optional[str]:
        """
        Resolve a logical selector to an actual element on the page.
        
        Args:
            page: Playwright page object
            selector: Logical selector (e.g., "search_box", "first_result")
            
        Returns:
            CSS selector string if element found, None otherwise
        """
        selector_lower = selector.lower().strip()
        
        # Check if it's a known logical selector
        if selector_lower in ActionMapper.SELECTOR_PATTERNS:
            return await ActionMapper._resolve_pattern(page, selector_lower)
        
        # Check for ordinal patterns like "first_product", "2nd_item", "third_link"
        ordinal_match = await ActionMapper._resolve_ordinal(page, selector_lower)
        if ordinal_match:
            return ordinal_match
        
        # Last resort: try as-is (might be a direct CSS selector)
        try:
            element = page.locator(selector_lower).first
            if await element.count() > 0:
                logger.debug(f"Found element using direct selector: {selector_lower}")
                return selector_lower
        except Exception:
            pass
        
        logger.warning(f"Could not resolve selector: {selector}")
        return None
    
    @staticmethod
    async def _resolve_pattern(page: Page, logical_selector: str) -> Optional[str]:
        """
        Resolve a logical selector using predefined patterns with retry logic.
        
        Args:
            page: Playwright page object
            logical_selector: Known logical selector key
            
        Returns:
            CSS selector if found, None otherwise
        """
        patterns = ActionMapper.SELECTOR_PATTERNS.get(logical_selector, {})
        selectors = patterns.get("selectors", [])
        fallback_text = patterns.get("fallback_text", [])
        
        # Retry logic: sometimes elements need time to appear
        max_retries = 3
        for attempt in range(max_retries):
            # Try CSS selectors first
            for css_selector in selectors:
                try:
                    # Use has-text requires special handling
                    if ":has-text(" in css_selector:
                        text = css_selector.split(":has-text(")[1].split(")")[0].strip('"\'')
                        element = page.locator(f"text={text}").first
                    else:
                        element = page.locator(css_selector).first
                    
                    count = await element.count()
                    if count > 0:
                        # Don't require is_visible() - sometimes elements are visible but not marked as such
                        logger.debug(f"Resolved '{logical_selector}' to CSS (attempt {attempt+1}): {css_selector}")
                        return css_selector
                except Exception as e:
                    logger.debug(f"Selector failed ({logical_selector}, attempt {attempt+1}): {css_selector} - {e}")
                    continue
            
            # Try text-based fallback
            for text in fallback_text:
                try:
                    element = page.locator(f"text={text}").first
                    count = await element.count()
                    if count > 0:
                        logger.debug(f"Resolved '{logical_selector}' to text (attempt {attempt+1}): {text}")
                        return f"text={text}"
                except Exception:
                    continue
            
            # If not found on first attempt, wait a bit and retry
            if attempt < max_retries - 1:
                logger.debug(f"Selector '{logical_selector}' not found, retrying in 1s...")
                await page.wait_for_timeout(1000)  # Wait 1 second before retry
        
        logger.warning(f"Failed to resolve logical selector after {max_retries} attempts: {logical_selector}")
        return None
    
    @staticmethod
    async def _resolve_ordinal(page: Page, selector: str) -> Optional[str]:
        """
        Resolve ordinal selectors like "first_product", "2nd_item", "third_link".
        
        Args:
            page: Playwright page object
            selector: Ordinal selector string
            
        Returns:
            CSS selector if pattern matched, None otherwise
        """
        # Ordinal patterns: "first_thing", "2nd_thing", "second_thing"
        import re
        
        ordinal_map = {
            "first": 0, "1": 0, "1st": 0,
            "second": 1, "2": 1, "2nd": 1,
            "third": 2, "3": 2, "3rd": 2,
            "fourth": 3, "4": 3, "4th": 3,
            "fifth": 4, "5": 4, "5th": 4,
        }
        
        # Try to match ordinal_noun pattern
        match = re.match(r"(first|second|third|fourth|fifth|1|2|3|4|5|1st|2nd|3rd|4th|5th)_(.+)", selector)
        if not match:
            return None
        
        ordinal_text, noun = match.groups()
        ordinal_text = ordinal_text.lower()
        noun = noun.lower()
        
        index = ordinal_map.get(ordinal_text, 0)
        
        # Map noun to selector patterns
        noun_patterns = {
            "product": 'div[class*="product" i], li[class*="product" i]',
            "item": 'div[class*="item" i], li[class*="item" i]',
            "result": '.search-result, .result-item, a[href*="search"]',
            "link": 'a',
            "button": 'button',
        }
        
        selector_pattern = noun_patterns.get(noun)
        if not selector_pattern:
            return None
        
        try:
            elements = page.locator(selector_pattern)
            count = await elements.count()
            if count > index:
                logger.debug(f"Resolved ordinal selector '{selector}' to index {index}")
                # Return a locator expression for nth child
                return f"({selector_pattern}):nth-child({index + 1})"
        except Exception as e:
            logger.debug(f"Ordinal resolution failed: {selector} - {e}")
        
        return None
    
    @staticmethod
    async def find_element_by_selector(page: Page, selector: str):
        """
        Find an element on the page using a resolved selector.
        
        Args:
            page: Playwright page object
            selector: Logical or CSS selector
            
        Returns:
            Playwright ElementHandle if found, None otherwise
        """
        resolved = await ActionMapper.resolve_selector(page, selector)
        
        if not resolved:
            logger.warning(f"Could not resolve selector: {selector}")
            return None
        
        try:
            # Handle special locator syntax
            if resolved.startswith("text="):
                element = page.locator(resolved).first
            elif ":" in resolved:  # nth-child, :has-text, etc.
                element = page.locator(resolved).first
            else:
                element = page.locator(resolved).first
            
            if await element.count() > 0:
                return element
        except Exception as e:
            logger.error(f"Failed to find element: {selector} ({resolved}) - {e}")
        
        return None
    
    @staticmethod
    async def get_page_context(page: Page) -> str:
        """
        Extract simplified page context for planner.
        Returns visible interactive elements for planning context.
        
        Args:
            page: Playwright page object
            
        Returns:
            String description of page elements and structure
        """
        try:
            context_parts = [
                f"URL: {page.url}",
                f"Title: {await page.title()}",
            ]
            
            # Get visible buttons and links
            buttons = page.locator("button:visible")
            button_count = await buttons.count()
            if button_count > 0:
                button_texts = []
                for i in range(min(button_count, 5)):
                    try:
                        text = await buttons.nth(i).text_content()
                        if text:
                            button_texts.append(text.strip()[:50])
                    except:
                        pass
                if button_texts:
                    context_parts.append(f"Buttons: {', '.join(button_texts)}")
            
            # Get search boxes
            search_boxes = page.locator('input[placeholder*="search" i], input[type="search"]')
            search_count = await search_boxes.count()
            if search_count > 0:
                context_parts.append(f"Search boxes found: {search_count}")
            
            # Get main headings
            headings = page.locator("h1:visible, h2:visible")
            heading_count = await headings.count()
            if heading_count > 0:
                heading_texts = []
                for i in range(min(heading_count, 3)):
                    try:
                        text = await headings.nth(i).text_content()
                        if text:
                            heading_texts.append(text.strip()[:40])
                    except:
                        pass
                if heading_texts:
                    context_parts.append(f"Headings: {', '.join(heading_texts)}")
            
            return "\n".join(context_parts)
        
        except Exception as e:
            logger.warning(f"Failed to extract page context: {e}")
            return f"URL: {page.url}"
