"""
Robust Intent Parser: Hybrid LLM + Regex approach to extract structured intent.

Solves the problem: Full user command being used as search query.

Example:
    Input: "search for boys watches on daraz and then add to cart 2nd item"
    
    Incorrect (Old): query = "for boys watches and then add to cart 2nd item"  ❌
    Correct (New):  
        - query = "boys watches"  ✅
        - actions = [{"type": "add_to_cart", "index": 2}]  ✅
        - site = "daraz"  ✅
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

try:
    from groq import Groq
    from config import Config
    from utils import get_logger
except ImportError:
    from ..groq import Groq
    from ..config import Config
    from ..utils import get_logger

logger = get_logger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class SiteType(Enum):
    """Known e-commerce sites."""
    DARAZ = "daraz"
    AMAZON = "amazon"
    EBAY = "ebay"
    YOUTUBE = "youtube"
    ALIEXPRESS = "aliexpress"
    UNKNOWN = "unknown"


class ActionType(Enum):
    """Action types to perform after search."""
    OPEN_ITEM = "open_item"           # Open nth item
    ADD_TO_CART = "add_to_cart"       # Add to cart
    CLICK_BUTTON = "click_button"     # Click button
    FILL_FORM = "fill_form"           # Fill form
    NAVIGATE = "navigate"             # Navigate to URL
    NONE = "none"                     # No action


@dataclass
class Action:
    """Represents a specific action to take."""
    action_type: ActionType
    index: Optional[int] = None       # For "open 2nd item"
    value: Optional[str] = None       # For "fill form"
    selector: Optional[str] = None    # Element selector
    
    def to_dict(self) -> dict:
        """Convert to dict."""
        return {
            "type": self.action_type.value,
            "index": self.index,
            "value": self.value,
            "selector": self.selector,
        }


@dataclass
class ParsedIntent:
    """Structured result from intent parsing."""
    site: SiteType
    search_query: str                # CLEAN query for searching
    actions: List[Action] = field(default_factory=list)  # Actions to perform
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dict."""
        return {
            "site": self.site.value,
            "search_query": self.search_query,
            "actions": [a.to_dict() for a in self.actions],
            "metadata": self.metadata,
        }
    
    def __str__(self) -> str:
        """String representation."""
        actions_str = " → ".join([a.action_type.value for a in self.actions])
        return f"[{self.site.value}] '{self.search_query}' {actions_str if actions_str else '(view results)'}"


# ============================================================================
# SITE MAPPING & KEYWORDS
# ============================================================================

SITE_DOMAINS = {
    SiteType.DARAZ: "https://www.daraz.pk",
    SiteType.AMAZON: "https://www.amazon.com",
    SiteType.EBAY: "https://www.ebay.com",
    SiteType.YOUTUBE: "https://www.youtube.com",
    SiteType.ALIEXPRESS: "https://www.aliexpress.com",
}

SITE_KEYWORDS = {
    "daraz": SiteType.DARAZ,
    "amazon": SiteType.AMAZON,
    "ebay": SiteType.EBAY,
    "youtube": SiteType.YOUTUBE,
    "aliexpress": SiteType.ALIEXPRESS,
    "ali express": SiteType.ALIEXPRESS,
}

# Action detection keywords
ACTION_KEYWORDS = {
    "add to cart": ActionType.ADD_TO_CART,
    "add to basket": ActionType.ADD_TO_CART,
    "add to bag": ActionType.ADD_TO_CART,
    "checkout": ActionType.ADD_TO_CART,
}

ORDINAL_WORDS = {
    "first": 1, "1st": 1,
    "second": 2, "2nd": 2,
    "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
}

# Action stop words - these should be removed from query if found
ACTION_STOP_WORDS = [
    "add", "then", "next", "after", "later", "and",
    "item", "items", "product", "products",
    "cart", "basket", "bag", "order",
    "click", "open", "close", "go",
    "button", "link", "element",
]


# ============================================================================
# LLM-BASED PARSING
# ============================================================================

INTENT_PARSER_PROMPT = """Extract structured intent from user command.

User command: "{command}"

Return ONLY valid JSON (no other text):
{{
  "site": "daraz|amazon|ebay|youtube|aliexpress|unknown",
  "search_query": "clean search term without action words",
  "actions": [
    {{"type": "add_to_cart", "index": 2}},
    {{"type": "open_item", "index": 2}}
  ]
}}

CRITICAL RULES:
1. Extract ONLY the product search term for search_query.
   - Input: "search for boys watches on daraz and then add to cart 2nd item"
   - Output search_query: "boys watches"  (NOT "for boys watches and then add...")
   
2. Actions include add_to_cart, open_item, etc.
   - Include ordinal (1st, 2nd, etc) as "index" if specified
   
3. Detect site from keywords (daraz, amazon, etc)
   - If no site mentioned, use "unknown"
   
4. Remove action words from search_query:
   - "add", "then", "next", "item", "cart", "product"
   
Example:
Input: "find laptops on amazon and add 3rd one to cart"
Output:
{{
  "site": "amazon",
  "search_query": "laptops",
  "actions": [
    {{"type": "open_item", "index": 3}},
    {{"type": "add_to_cart"}}
  ]
}}
"""


class RobustIntentParser:
    """
    Parse user intent with hybrid approach:
    1. Try LLM parsing (primary, most accurate)
    2. Fallback to regex parsing if LLM fails
    """
    
    def __init__(self):
        """Initialize parser."""
        self.client = Groq(api_key=Config.GROQ_API_KEY) if Config.GROQ_API_KEY else None
        self.model = Config.LLM_MODEL or "mixtral-8x7b-32768"
    
    def parse(self, command: str) -> ParsedIntent:
        """
        Parse user command into structured intent.
        
        Args:
            command: User natural language command
            
        Returns:
            ParsedIntent with site, search_query, and actions
        """
        command = command.strip()
        logger.info(f"Parsing: {command}")
        
        # Try LLM parsing first
        if self.client:
            try:
                result = self._parse_with_llm(command)
                if result:
                    logger.info(f"Parsed with LLM: {result}")
                    return result
            except Exception as e:
                logger.warning(f"LLM parsing failed: {e}, trying regex fallback")
        
        # Fallback to regex parsing
        result = self._parse_with_regex(command)
        logger.info(f"Parsed with regex: {result}")
        return result
    
    def _parse_with_llm(self, command: str) -> Optional[ParsedIntent]:
        """
        Parse using LLM (primary method).
        
        Args:
            command: User command
            
        Returns:
            ParsedIntent or None if parsing fails
        """
        try:
            prompt = INTENT_PARSER_PROMPT.format(command=command)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # Deterministic
                max_tokens=500,
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                logger.warning(f"No JSON in LLM response: {response_text}")
                return None
            
            data = json.loads(json_match.group(0))
            
            return self._build_intent_from_dict(data)
        
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error from LLM: {e}")
            return None
        except Exception as e:
            logger.warning(f"LLM parsing error: {e}")
            return None
    
    def _parse_with_regex(self, command: str) -> ParsedIntent:
        """
        Parse using regex patterns (fallback method).
        
        Args:
            command: User command
            
        Returns:
            ParsedIntent
        """
        command_lower = command.lower()
        
        # Step 1: Extract site
        site = self._extract_site_regex(command_lower)
        
        # Step 2: Extract search query (clean of action words)
        search_query = self._extract_query_regex(command_lower)
        
        # Step 3: Extract actions
        actions = self._extract_actions_regex(command_lower)
        
        # Step 4: Extract metadata
        metadata = self._extract_metadata_regex(command_lower)
        
        return ParsedIntent(
            site=site,
            search_query=search_query,
            actions=actions,
            metadata=metadata,
        )
    
    def _extract_site_regex(self, command: str) -> SiteType:
        """Extract site using regex."""
        for keyword, site in SITE_KEYWORDS.items():
            if re.search(rf'\b{re.escape(keyword)}\b', command):
                return site
        return SiteType.UNKNOWN
    
    def _extract_query_regex(self, command: str) -> str:
        """
        Extract clean search query (without action words).
        
        Strategy: Find the part of the command that is the actual search term,
        which is typically between search keywords and site/action keywords.
        """
        query = command.lower()
        
        # Step 1: Remove everything before and including search keywords
        search_keywords = ["search for", "find", "look for", "hunt for", "seek", "search"]
        for kw in search_keywords:
            if kw in query:
                # Keep everything AFTER the search keyword
                idx = query.find(kw)
                query = query[idx + len(kw):].strip()
                break  # Only process first match
        
        # Step 2: Extract everything BEFORE "on <site>" or action keywords
        # Look for "on <site>" pattern
        cleanup_patterns = []
        
        # "on <site>" patterns
        for site_kw in SITE_KEYWORDS.keys():
            pattern = rf'\bon\s+{re.escape(site_kw)}\b'
            if re.search(pattern, query):
                # Extract part BEFORE "on <site>"
                match = re.search(pattern, query)
                query = query[:match.start()].strip()
                break
        
        # Step 3: Remove action keywords and connectors from the end
        query = re.sub(r'\s+(and|then|next|later).*$', '', query, flags=re.IGNORECASE).strip()
        
        # Step 4: Remove common action words that might have sneaked in
        # But be more conservative - only remove if they're at the end or start
        query = re.sub(r'^(add|click|open|close|go|put|get)\s+', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+(to\s+cart|to\s+basket|\s+item\s*$)$', '', query, flags=re.IGNORECASE)
        
        # Step 5: Clean up extra whitespace
        query = re.sub(r'\s+', ' ', query).strip()
        
        # If empty, return generic
        return query or "products"
    
    def _extract_actions_regex(self, command: str) -> List[Action]:
        """Extract action steps from command."""
        actions = []
        
        # Check for add to cart (more flexible pattern)
        if any(re.search(rf'\b{re.escape(kw)}\b', command, re.IGNORECASE) 
               for kw in ["add to cart", "add to basket", "add to bag", "checkout", "buy"]):
            # Check for ordinal (which item to add)
            ordinal_match = re.search(
                r'\b(' + '|'.join(re.escape(k) for k in ORDINAL_WORDS.keys()) + r')\b',
                command,
                re.IGNORECASE
            )
            
            item_index = None
            if ordinal_match:
                ordinal = ordinal_match.group(1).lower()
                item_index = ORDINAL_WORDS.get(ordinal)
            
            # Usually add to cart follows opening an item
            if item_index:
                actions.append(Action(ActionType.OPEN_ITEM, index=item_index))
            
            actions.append(Action(ActionType.ADD_TO_CART))
        
        # Check for open item (just ordinal without add to cart)
        elif re.search(r'\b(open|click|view|get)\s+(?:' + '|'.join(re.escape(k) for k in ORDINAL_WORDS.keys()) + r')\b', command, re.IGNORECASE):
            ordinal_match = re.search(
                r'\b(' + '|'.join(re.escape(k) for k in ORDINAL_WORDS.keys()) + r')\b',
                command,
                re.IGNORECASE
            )
            if ordinal_match:
                ordinal = ordinal_match.group(1).lower()
                item_index = ORDINAL_WORDS.get(ordinal)
                if item_index:
                    actions.append(Action(ActionType.OPEN_ITEM, index=item_index))
        
        return actions
    
    def _extract_metadata_regex(self, command: str) -> dict:
        """Extract metadata."""
        metadata = {}
        
        # Extract numbers (quantities, prices)
        numbers = re.findall(r'\d+', command)
        if numbers:
            metadata["numbers"] = [int(n) for n in set(numbers)]
        
        # Extract ordinal
        ordinal_match = re.search(
            r'\b(' + '|'.join(ORDINAL_WORDS.keys()) + r')\b',
            command,
            re.IGNORECASE
        )
        if ordinal_match:
            metadata["ordinal"] = ordinal_match.group(1).lower()
            metadata["ordinal_index"] = ORDINAL_WORDS[metadata["ordinal"]]
        
        return metadata
    
    def _build_intent_from_dict(self, data: dict) -> ParsedIntent:
        """
        Build ParsedIntent from dict (from LLM or elsewhere).
        
        Args:
            data: Dict with site, search_query, actions, etc.
            
        Returns:
            ParsedIntent
        """
        # Parse site
        site_str = data.get("site", "unknown").lower()
        site = SiteType(site_str) if site_str in [s.value for s in SiteType] else SiteType.UNKNOWN
        
        # Parse query
        search_query = data.get("search_query", "products").strip()
        if not search_query:
            search_query = "products"
        
        # Validate and clean query (no action words should remain)
        search_query = self._validate_query(search_query)
        
        # Parse actions
        actions = []
        for action_data in data.get("actions", []):
            action_type_str = action_data.get("type", "").lower()
            try:
                action_type = ActionType(action_type_str)
                action = Action(
                    action_type=action_type,
                    index=action_data.get("index"),
                    value=action_data.get("value"),
                    selector=action_data.get("selector"),
                )
                actions.append(action)
            except ValueError:
                logger.warning(f"Unknown action type: {action_type_str}")
        
        return ParsedIntent(
            site=site,
            search_query=search_query,
            actions=actions,
            metadata=data.get("metadata", {}),
        )
    
    @staticmethod
    def _validate_query(query: str) -> str:
        """
        Validate that query doesn't contain action words.
        
        If it does, try to clean them out.
        
        Args:
            query: Search query
            
        Returns:
            Clean query
        """
        query_lower = query.lower()
        
        # Check for problematic words
        action_words = ACTION_STOP_WORDS + ["add", "checkout", "cart", "basket"]
        bad_words = [w for w in action_words if w in query_lower.split()]
        
        if bad_words:
            logger.warning(f"Query contains action words: {bad_words}. Original: {query}")
            
            # Try to remove them
            clean_query = query
            for word in bad_words:
                clean_query = re.sub(rf'\b{re.escape(word)}\b', '', clean_query, flags=re.IGNORECASE)
            
            clean_query = re.sub(r'\s+', ' ', clean_query).strip()
            
            if clean_query:
                logger.info(f"Cleaned query: {clean_query}")
                return clean_query
            
        return query


# ============================================================================
# PUBLIC API
# ============================================================================

def parse_intent(command: str) -> ParsedIntent:
    """
    Public API to parse user intent.
    
    Args:
        command: User natural language command
        
    Returns:
        ParsedIntent with structured data
        
    Example:
        >>> intent = parse_intent("search for boys watches on daraz and add to cart 2nd item")
        >>> print(intent.search_query)  # "boys watches"
        >>> print(intent.actions)        # [open_item(2), add_to_cart]
    """
    parser = RobustIntentParser()
    return parser.parse(command)
