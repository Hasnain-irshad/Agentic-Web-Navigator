"""
Intent Parser: Converts natural language commands into structured intents.
Enables site-specific and goal-driven automation without Google dependency.
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

try:
    from utils import get_logger
except ImportError:
    from ..utils import get_logger


logger = get_logger(__name__)


class IntentType(Enum):
    """Types of user intents."""
    SEARCH = "search"              # Search for something
    NAVIGATE = "navigate"          # Go to a website
    CLICK = "click"                # Click an element
    FILL_FORM = "fill_form"        # Fill form fields
    ADD_TO_CART = "add_to_cart"    # Add item to cart
    CHECKOUT = "checkout"          # Proceed to checkout
    EXTRACT_INFO = "extract_info"  # Extract information
    GENERAL = "general"            # Generic goal


class SiteType(Enum):
    """Known e-commerce and utility sites."""
    DARAZ = "daraz"
    AMAZON = "amazon"
    EBAY = "ebay"
    YOUTUBE = "youtube"
    GOOGLE = "google"
    DUCKDUCKGO = "duckduckgo"
    ALIEXPRESS = "aliexpress"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    """
    Structured representation of a user command.
    
    Attributes:
        intent_type: Type of user goal (search, navigate, etc.)
        site: Target site if specified
        domain_url: Direct URL if known, else None
        query: Search query or main goal
        sub_goals: Breakdown of the task into steps
        metadata: Additional info (product category, filters, etc.)
    """
    intent_type: IntentType
    query: str
    site: Optional[SiteType] = None
    domain_url: Optional[str] = None
    sub_goals: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    def __str__(self) -> str:
        """String representation."""
        site_str = f" on {self.site.value}" if self.site else ""
        return f"{self.intent_type.value}{site_str}: {self.query}"


# Site domain mappings
SITE_DOMAINS = {
    SiteType.DARAZ: "https://www.daraz.pk",
    SiteType.AMAZON: "https://www.amazon.com",
    SiteType.EBAY: "https://www.ebay.com",
    SiteType.YOUTUBE: "https://www.youtube.com",
    SiteType.GOOGLE: "https://www.google.com",
    SiteType.DUCKDUCKGO: "https://duckduckgo.com",
    SiteType.ALIEXPRESS: "https://www.aliexpress.com",
}

# Keywords mapping sites
SITE_KEYWORDS = {
    "daraz": SiteType.DARAZ,
    "amazon": SiteType.AMAZON,
    "ebay": SiteType.EBAY,
    "youtube": SiteType.YOUTUBE,
    "google": SiteType.GOOGLE,
    "duckduckgo": SiteType.DUCKDUCKGO,
    "duck duck go": SiteType.DUCKDUCKGO,
    "aliexpress": SiteType.ALIEXPRESS,
    "ali express": SiteType.ALIEXPRESS,
}

# Intent type keywords
SEARCH_KEYWORDS = ["search", "find", "look for", "hunt for", "seek"]
NAVIGATE_KEYWORDS = ["go to", "open", "visit", "navigate to", "browse"]
ADD_TO_CART_KEYWORDS = ["add to cart", "add to basket", "add to bag"]
CHECKOUT_KEYWORDS = ["checkout", "buy", "purchase", "pay"]
CLICK_KEYWORDS = ["click", "tap", "select"]


class IntentParser:
    """Parses natural language commands into structured intents."""
    
    @staticmethod
    def parse(command: str) -> Intent:
        """
        Parse a user command into a structured intent.
        
        Args:
            command: Natural language command
            
        Returns:
            Intent object with parsed information
        """
        command_lower = command.lower().strip()
        
        # Step 1: Detect site
        site = IntentParser._extract_site(command_lower)
        domain_url = SITE_DOMAINS.get(site) if site != SiteType.UNKNOWN else None
        
        # Step 2: Detect intent type
        intent_type = IntentParser._detect_intent_type(command_lower)
        
        # Step 3: Extract query/goal
        query = IntentParser._extract_query(command_lower, intent_type, site)
        
        # Step 4: Generate sub-goals based on intent
        sub_goals = IntentParser._generate_sub_goals(intent_type, site, query)
        
        # Step 5: Extract metadata
        metadata = IntentParser._extract_metadata(command_lower)
        
        intent = Intent(
            intent_type=intent_type,
            query=query,
            site=site if site != SiteType.UNKNOWN else None,
            domain_url=domain_url,
            sub_goals=sub_goals,
            metadata=metadata,
        )
        
        logger.debug(f"Parsed intent: {intent}")
        return intent
    
    @staticmethod
    def _extract_site(command: str) -> SiteType:
        """Extract target site from command."""
        for keyword, site in SITE_KEYWORDS.items():
            if keyword in command:
                return site
        return SiteType.UNKNOWN
    
    @staticmethod
    def _detect_intent_type(command: str) -> IntentType:
        """Detect the type of user intent."""
        if any(kw in command for kw in SEARCH_KEYWORDS):
            return IntentType.SEARCH
        elif any(kw in command for kw in NAVIGATE_KEYWORDS):
            return IntentType.NAVIGATE
        elif any(kw in command for kw in ADD_TO_CART_KEYWORDS):
            return IntentType.ADD_TO_CART
        elif any(kw in command for kw in CHECKOUT_KEYWORDS):
            return IntentType.CHECKOUT
        elif any(kw in command for kw in CLICK_KEYWORDS):
            return IntentType.CLICK
        else:
            return IntentType.GENERAL
    
    @staticmethod
    def _extract_query(command: str, intent_type: IntentType, site: SiteType) -> str:
        """Extract the main query/goal from command."""
        # Remove common keywords
        query = command
        
        for kw in SEARCH_KEYWORDS + NAVIGATE_KEYWORDS + ADD_TO_CART_KEYWORDS + CHECKOUT_KEYWORDS:
            pattern = rf'\b{re.escape(kw)}\b'
            query = re.sub(pattern, "", query, flags=re.IGNORECASE)
        
        # Remove site names
        for keyword in SITE_KEYWORDS.keys():
            pattern = rf'\bon\s+{re.escape(keyword)}|{re.escape(keyword)}'
            query = re.sub(pattern, "", query, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        query = " ".join(query.split()).strip()
        
        return query or "general task"
    
    @staticmethod
    def _generate_sub_goals(intent_type: IntentType, site: SiteType, query: str) -> List[str]:
        """Generate breakdown of task into sub-goals."""
        sub_goals = []
        
        if site and site != SiteType.UNKNOWN:
            # Direct site navigation
            sub_goals.append(f"Navigate to {site.value}")
        elif intent_type in [IntentType.SEARCH, IntentType.GENERAL]:
            # Use DuckDuckGo as fallback for unknown sites
            sub_goals.append("Navigate to DuckDuckGo")
        
        if intent_type == IntentType.SEARCH:
            sub_goals.append(f"Search for: {query}")
            sub_goals.append("View search results")
        
        elif intent_type == IntentType.NAVIGATE:
            sub_goals.append(f"Navigate to: {query}")
        
        elif intent_type == IntentType.ADD_TO_CART:
            sub_goals.append(f"Find product: {query}")
            sub_goals.append("Click Add to Cart")
        
        elif intent_type == IntentType.CHECKOUT:
            sub_goals.append("Proceed to checkout")
            sub_goals.append("Review order")
        
        elif intent_type == IntentType.CLICK:
            sub_goals.append(f"Click element: {query}")
        
        else:  # GENERAL
            sub_goals.append(f"Accomplish: {query}")
        
        return sub_goals
    
    @staticmethod
    def _extract_metadata(command: str) -> dict:
        """Extract additional metadata from command."""
        metadata = {}
        
        # Extract numbers (quantities, prices, etc.)
        numbers = re.findall(r'\d+', command)
        if numbers:
            metadata["numbers"] = [int(n) for n in numbers]
        
        # Extract "first", "second", etc.
        ordinal_match = re.search(r'\b(first|second|third|fourth|fifth)\b', command)
        if ordinal_match:
            metadata["ordinal"] = ordinal_match.group(1)
        
        # Extract category keywords
        if "watch" in command or "watches" in command:
            metadata["category"] = "watches"
        elif "phone" in command or "phones" in command:
            metadata["category"] = "phones"
        elif "laptop" in command or "laptops" in command:
            metadata["category"] = "laptops"
        
        return metadata
    
    @staticmethod
    def get_direct_url(site: SiteType) -> Optional[str]:
        """Get direct URL for a known site."""
        return SITE_DOMAINS.get(site)
