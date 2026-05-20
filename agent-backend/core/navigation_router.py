"""
Navigation Router: Smart navigation without Google dependency.
Routes user requests directly to target sites or DuckDuckGo for unknown queries.

Key principle: If site is known, go directly. If unknown, use DuckDuckGo (not Google).
"""

from typing import Optional
from enum import Enum

try:
    from core.intent_parser import IntentParser, Intent, SiteType, SITE_DOMAINS
    from utils import get_logger
except ImportError:
    from .intent_parser import IntentParser, Intent, SiteType, SITE_DOMAINS
    from ..utils import get_logger


logger = get_logger(__name__)


class NavigationStrategy(Enum):
    """Navigation strategies."""
    DIRECT = "direct"              # Go directly to known site
    DUCKDUCKGO = "duckduckgo"      # Use DuckDuckGo fallback
    SITE_SEARCH = "site_search"    # Search within site


class NavigationPlan:
    """
    Structured navigation plan for reaching the target site/content.
    
    Handles three scenarios:
    1. Direct: User specifies site → go directly to domain
    2. Search: User searches for something → use DuckDuckGo
    3. Site search: Already on site → use site's search box
    """
    
    def __init__(
        self,
        strategy: NavigationStrategy,
        url: Optional[str] = None,
        search_query: Optional[str] = None,
    ):
        """
        Initialize navigation plan.
        
        Args:
            strategy: How to navigate
            url: Target URL (for direct navigation)
            search_query: What to search for (for search strategies)
        """
        self.strategy = strategy
        self.url = url
        self.search_query = search_query


class NavigationRouter:
    """
    Routes navigation requests intelligently without Google dependency.
    """
    
    @staticmethod
    def plan_navigation(intent: Intent) -> NavigationPlan:
        """
        Generate a navigation plan based on parsed intent.
        
        Args:
            intent: Parsed user intent with site and query
            
        Returns:
            NavigationPlan with strategy and URL
        """
        
        # Case 1: User specified a known site
        if intent.site and intent.site != SiteType.UNKNOWN:
            url = SITE_DOMAINS.get(intent.site)
            logger.info(f"Direct navigation to {intent.site.value}")
            return NavigationPlan(
                strategy=NavigationStrategy.DIRECT,
                url=url,
            )
        
        # Case 2: Unknown site → use DuckDuckGo fallback
        # Never use Google, always prefer DuckDuckGo
        logger.info(f"Using DuckDuckGo for: {intent.query}")
        return NavigationPlan(
            strategy=NavigationStrategy.DUCKDUCKGO,
            url=SITE_DOMAINS[SiteType.DUCKDUCKGO],
            search_query=intent.query,
        )
    
    @staticmethod
    def get_search_url(query: str, site: Optional[SiteType] = None) -> str:
        """
        Build a search URL for a query.
        
        Args:
            query: Search term
            site: Optional site to search within
            
        Returns:
            Full search URL
        """
        if site == SiteType.GOOGLE:
            return f"https://www.google.com/search?q={query}"
        
        elif site == SiteType.AMAZON:
            return f"https://www.amazon.com/s?k={query}"
        
        elif site == SiteType.EBAY:
            return f"https://www.ebay.com/sch/i.html?_nkw={query}"
        
        elif site == SiteType.DARAZ:
            return f"https://www.daraz.pk/search/{query}"
        
        elif site == SiteType.YOUTUBE:
            return f"https://www.youtube.com/results?search_query={query}"
        
        elif site == SiteType.ALIEXPRESS:
            return f"https://www.aliexpress.com/af/search.html?SearchText={query}"
        
        else:
            # Default to DuckDuckGo
            return f"https://duckduckgo.com/?q={query}"
    
    @staticmethod
    def resolve_search_box_selector() -> str:
        """
        Get the universal selector for search boxes.
        Works across most websites.
        
        Returns:
            Logical selector name that ActionMapper can resolve
        """
        return "search_box"
    
    @staticmethod
    def should_use_direct_navigation(intent: Intent) -> bool:
        """
        Determine if we should navigate directly to a site.
        
        Args:
            intent: Parsed user intent
            
        Returns:
            True if direct navigation is preferred
        """
        return (
            intent.site is not None 
            and intent.site != SiteType.UNKNOWN
            and intent.site in SITE_DOMAINS
        )
    
    @staticmethod
    def get_fallback_search_engine() -> str:
        """Get fallback search engine (never Google)."""
        return SITE_DOMAINS[SiteType.DUCKDUCKGO]


class NavigationOptimizer:
    """
    Optimizes navigation to minimize round trips and bot detection.
    """
    
    @staticmethod
    def build_direct_search_plan(query: str, site: Optional[SiteType] = None) -> list[dict]:
        """
        Build a direct multi-step search plan.
        
        Example for "search for watches on daraz":
        Returns:
        [
            {"action": "goto", "value": "https://www.daraz.pk"},
            {"action": "type", "selector": "search_box", "value": "watches"},
            {"action": "press_key", "key": "Enter"},
            {"action": "done", "reasoning": "Search completed"}
        ]
        
        Args:
            query: Search term
            site: Target site (or None for DuckDuckGo)
            
        Returns:
            List of action steps
        """
        
        if site and site in SITE_DOMAINS:
            # Direct: Go to site → search
            url = SITE_DOMAINS[site]
            steps = [
                {
                    "action": "goto",
                    "value": url,
                    "reasoning": f"Navigate to {site.value}",
                },
                {
                    "action": "type",
                    "selector": "search_box",
                    "value": query,
                    "reasoning": f"Search for: {query}",
                },
                {
                    "action": "press_key",
                    "key": "Enter",
                    "reasoning": "Submit search",
                },
                {
                    "action": "done",
                    "reasoning": f"Search for {query} on {site.value} completed",
                },
            ]
        else:
            # Fallback: Use DuckDuckGo
            steps = [
                {
                    "action": "goto",
                    "value": SITE_DOMAINS[SiteType.DUCKDUCKGO],
                    "reasoning": "Navigate to DuckDuckGo",
                },
                {
                    "action": "type",
                    "selector": "search_box",
                    "value": query,
                    "reasoning": f"Search for: {query}",
                },
                {
                    "action": "press_key",
                    "key": "Enter",
                    "reasoning": "Submit search",
                },
                {
                    "action": "done",
                    "reasoning": f"Search completed on DuckDuckGo",
                },
            ]
        
        return steps
    
    @staticmethod
    def build_product_search_plan(
        product_query: str,
        site: Optional[SiteType] = None,
        add_to_cart: bool = False,
    ) -> list[dict]:
        """
        Build a plan for product search and optional add-to-cart.
        
        Example for "search for watches on daraz and add first item":
        [
            {"action": "goto", "value": "https://www.daraz.pk", ...},
            {"action": "type", "selector": "search_box", "value": "watches", ...},
            {"action": "press_key", "key": "Enter", ...},
            {"action": "click", "selector": "first_product", ...},  // optional
            {"action": "click", "selector": "add_to_cart", ...}     // optional
        ]
        
        Args:
            product_query: Product search term
            site: Target site (defaults to DuckDuckGo if None)
            add_to_cart: Whether to add first product to cart
            
        Returns:
            List of action steps
        """
        steps = NavigationOptimizer.build_direct_search_plan(product_query, site)
        
        # Remove the "done" at the end
        steps = steps[:-1]
        
        if add_to_cart:
            steps.extend([
                {
                    "action": "click",
                    "selector": "first_product",
                    "reasoning": "Click first product",
                },
                {
                    "action": "click",
                    "selector": "add_to_cart",
                    "reasoning": "Add product to cart",
                },
            ])
        
        steps.append({
            "action": "done",
            "reasoning": f"Product search and {'add to cart' if add_to_cart else 'view'} completed",
        })
        
        return steps
