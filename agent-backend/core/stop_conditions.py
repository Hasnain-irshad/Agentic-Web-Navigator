"""
Generic Stop Conditions Module

Implements two website-agnostic mechanisms to prevent infinite loops:
1. CompletionDetector: Detects goal achievement
2. RepetitionDetector: Detects repetitive actions and no-progress

These detectors work across ANY website without hardcoded rules.
"""

from typing import Tuple, Optional, Dict, Any
from urllib.parse import urlparse
import hashlib


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, strip whitespace)."""
    if not text:
        return ""
    return " ".join(text.lower().split())


class CompletionDetector:
    """
    Detects when a goal is achieved using generic signals.
    
    CRITICAL: Does NOT stop based on "done" action alone.
    Validates actual goal achievement through:
    - Search results indicators
    - Navigation domain matching
    - E-commerce signals (products, cart, checkout)
    - Generic goal keyword matching
    """
    
    def __init__(self):
        """Initialize completion detector."""
        self.url_stable_threshold = 2
        self.min_content_length = 100
        self.search_keywords = {
            "result", "results", "found", "product", "products",
            "listing", "listings", "search", "item", "items",
            "offer", "offers", "deal", "deals", "shop"
        }
        self.ecommerce_keywords = {
            "add to cart", "add to basket", "add to bag",
            "price", "rs", "$", "£", "€",
            "discount", "save", "offer",
            "out of stock", "in stock"
        }
        self.checkout_keywords = {
            "checkout", "order", "payment", "shipping", "address",
            "billing", "confirm", "proceed"
        }
        self.error_keywords = {"error", "not found", "404", "exception", "invalid", "fail"}
        self.portal_keywords = {"admissions", "apply", "portal", "login", "account"}
    
    def should_complete(
        self,
        goal: str,
        observation: Any,
        memory: Any,
        last_action: Any,
        last_result: Any
    ) -> Tuple[bool, str]:
        """
        Check if goal is complete.
        
        IMPORTANT: This does NOT check if last_action is "done".
        It validates actual goal achievement.
        
        Args:
            goal: User's goal string
            observation: Current page observation
            memory: MemoryStore instance
            last_action: Last executed action
            last_result: Result of last action
            
        Returns:
            (should_stop: bool, reason: str)
        """
        # Safety checks
        if not observation or not observation.page_text:
            return False, ""
        
        page_text = normalize_text(observation.page_text)
        url = observation.url or ""
        
        # Never stop on error pages
        if any(keyword in page_text for keyword in self.error_keywords):
            return False, "Page has error content"
        
        # Minimum content check
        if len(page_text) < self.min_content_length:
            return False, "Page content too short"
        
        # Extract goal type and keywords
        goal_lower = goal.lower()
        
        # Check search goals
        if any(word in goal_lower for word in ["search", "find", "look for"]):
            is_complete, reason = self._check_search_goal(
                goal, page_text, url, observation
            )
            if is_complete:
                return True, reason
        
        # Check add-to-cart goals
        if any(word in goal_lower for word in ["add", "cart", "basket", "bag"]):
            is_complete, reason = self._check_ecommerce_goal(
                goal, page_text, url, observation
            )
            if is_complete:
                return True, reason
        
        # Check checkout goals
        if any(word in goal_lower for word in ["checkout", "buy", "purchase", "pay"]):
            is_complete, reason = self._check_checkout_goal(goal, page_text, url)
            if is_complete:
                return True, reason
        
        # Check navigation goals
        if any(word in goal_lower for word in ["go to", "visit", "open", "navigate"]):
            is_complete, reason = self._check_navigation_goal(goal, page_text, url)
            if is_complete:
                return True, reason
        
        # Check portal/application goals
        if any(word in goal_lower for word in ["admissions", "apply", "portal"]):
            is_complete, reason = self._check_portal_goal(goal, page_text, url)
            if is_complete:
                return True, reason
        
        # Try generic keyword matching
        return self._check_generic_completion(goal, page_text, url)
    
    def _check_search_goal(
        self,
        goal: str,
        page_text: str,
        url: str,
        observation: Any
    ) -> Tuple[bool, str]:
        """Check if search goal is complete (stronger validation)."""
        # Extract search query from goal
        search_query = self._extract_search_query(goal)
        
        if not search_query:
            return False, "Could not extract search query"
        
        # Check for result keywords
        has_result_keywords = any(
            keyword in page_text for keyword in self.search_keywords
        )
        
        # Check for result-like elements
        has_result_elements = self._has_result_elements(observation)
        
        # Check if search query appears in page or URL
        query_in_page = search_query in page_text
        query_in_url = search_query in url.lower()
        
        # Strong signal: results page + query in page/URL + result elements
        if has_result_keywords and has_result_elements and (query_in_page or query_in_url):
            return True, f"Search results confirmed for '{search_query}'"
        
        # Medium signal: result keywords + elements
        if has_result_keywords and has_result_elements:
            return True, "Search results page detected"
        
        # Weak signal: just result keywords
        if has_result_keywords and len(page_text) > 500:
            return True, "Search results likely on page"
        
        return False, ""
    
    def _check_ecommerce_goal(
        self,
        goal: str,
        page_text: str,
        url: str,
        observation: Any
    ) -> Tuple[bool, str]:
        """Check if add-to-cart or product view goal is complete."""
        # Check for e-commerce signals
        has_ecommerce_keywords = any(
            keyword in page_text for keyword in self.ecommerce_keywords
        )
        
        has_product_elements = self._has_product_elements(observation)
        
        # Check for successful add-to-cart
        if "add to cart" in page_text or "added to" in page_text:
            return True, "Product added to cart"
        
        # Check for product page indicators
        if has_product_elements and has_ecommerce_keywords:
            return True, "Product details page confirmed"
        
        # Check for product listing
        if self._has_multiple_products(observation) and any(
            keyword in goal.lower() for keyword in ["search", "find"]
        ):
            return True, "Product listing page confirmed"
        
        return False, ""
    
    def _check_checkout_goal(
        self,
        goal: str,
        page_text: str,
        url: str
    ) -> Tuple[bool, str]:
        """Check if checkout/payment goal is complete."""
        # Check for checkout page indicators
        has_checkout_keywords = any(
            keyword in page_text for keyword in self.checkout_keywords
        )
        
        if has_checkout_keywords:
            return True, "Checkout page confirmed"
        
        # Check URL for payment/order indicators
        if any(word in url.lower() for word in ["checkout", "payment", "order", "cart"]):
            if has_checkout_keywords or "price" in page_text:
                return True, "Payment page confirmed"
        
        return False, ""
    
    def _check_navigation_goal(
        self,
        goal: str,
        page_text: str,
        url: str
    ) -> Tuple[bool, str]:
        """Check if navigation goal is complete."""
        # Extract target domain from goal
        target_domain = self._extract_target_domain(goal)
        
        if not target_domain:
            return False, ""
        
        # Check if target domain is in current URL
        current_domain = extract_domain(url)
        
        if target_domain in current_domain or current_domain in target_domain:
            return True, f"Successfully navigated to {target_domain}"
        
        return False, ""
    
    def _check_portal_goal(
        self,
        goal: str,
        page_text: str,
        url: str
    ) -> Tuple[bool, str]:
        """Check if portal/admissions goal is complete."""
        goal_lower = goal.lower()
        
        # Check for portal keywords in page
        for keyword in self.portal_keywords:
            if keyword in page_text:
                return True, f"Portal page detected (found '{keyword}')"
        
        # Check URL for portal indicators
        for keyword in self.portal_keywords:
            if keyword in url.lower():
                return True, f"Portal URL confirmed (found '{keyword}')"
        
        return False, ""
    
    def _check_generic_completion(
        self,
        goal: str,
        page_text: str,
        url: str
    ) -> Tuple[bool, str]:
        """Check for generic goal completion via keyword matching."""
        goal_lower = goal.lower()
        goal_words = set(goal_lower.split())
        
        # Filter out common words
        common_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "is", "are",
            "search", "find", "look", "for", "on"
        }
        goal_words = goal_words - common_words
        
        if not goal_words:
            return False, ""
        
        # Check if multiple goal words appear in page
        matching_words = [w for w in goal_words if w in page_text]
        
        if len(matching_words) >= 2:
            return True, f"Multiple goal keywords found: {', '.join(matching_words[:3])}"
        
        return False, ""
    
    def _extract_search_query(self, goal: str) -> str:
        """Extract search query from goal string."""
        goal_lower = goal.lower()
        
        for keyword in ["search for", "find", "search", "look for"]:
            if keyword in goal_lower:
                idx = goal_lower.index(keyword)
                query = goal[idx + len(keyword):].strip()
                # Remove common endings
                for end in [" on ", " in ", " at "]:
                    if end in query:
                        query = query.split(end)[0]
                return query.strip().lower()
        
        return ""
    
    def _extract_target_domain(self, goal: str) -> str:
        """Extract target domain/website from goal string."""
        goal_lower = goal.lower()
        
        for keyword in ["go to", "visit", "open", "navigate to"]:
            if keyword in goal_lower:
                idx = goal_lower.index(keyword)
                domain = goal[idx + len(keyword):].strip()
                # Clean up
                domain = domain.split()[0] if domain else ""
                return domain.lower()
        
        return ""
    
    def _has_result_elements(self, observation: Any) -> bool:
        """Check if page has result-like elements."""
        if not observation or not hasattr(observation, 'elements'):
            return False
        
        # Check for multiple clickable elements
        if hasattr(observation, 'elements') and observation.elements:
            clickable_count = sum(
                1 for elem in observation.elements
                if hasattr(elem, 'tag') and elem.tag in ['a', 'button']
            )
            return clickable_count >= 2
        
        return False
    
    def _has_product_elements(self, observation: Any) -> bool:
        """Check if page has product indicators."""
        if not observation or not observation.page_text:
            return False
        
        page_text = observation.page_text.lower()
        
        # Look for price indicators
        price_indicators = ["$", "rs", "£", "€", "price"]
        if "/5" in page_text or "rating" in page_text:  # Product ratings
            return True
        
        return any(indicator in page_text for indicator in price_indicators)
    
    def _has_multiple_products(self, observation: Any) -> bool:
        """Check if page shows multiple products."""
        if not observation or not observation.page_text:
            return False
        
        page_text = observation.page_text.lower()
        
        # Count product indicators
        indicator_count = sum(1 for indicator in ["product", "item", "price"] if indicator in page_text)
        
        return indicator_count >= 2


class RepetitionDetector:
    """
    Detects stuck loops and no-progress scenarios.
    
    Tracks:
    - Same action signature repeated N times (type, selector, value, key)
    - Page state unchanged across multiple steps (URL + title hash)
    """
    
    def __init__(self, window_size: int = 3):
        """
        Initialize repetition detector.
        
        Args:
            window_size: Number of actions to track for repetition (default: 3)
        """
        self.window_size = window_size
        self.no_progress_threshold = 2
        self.last_page_state = None
        self.page_state_repeats = 0
    
    def is_repetition_detected(
        self,
        memory: Any,
        observation: Any
    ) -> Tuple[bool, str]:
        """
        Check if repetition or no-progress is detected.
        
        Args:
            memory: MemoryStore instance
            observation: Current page observation
            
        Returns:
            (is_repetitive: bool, reason: str)
        """
        # Check for same action repeated
        if hasattr(memory, '_history') and memory._history:
            is_repetitive, reason = self._check_action_repetition(memory)
            if is_repetitive:
                return True, reason
        
        # Check for page state not changing
        is_no_progress, reason = self._check_no_progress(observation)
        if is_no_progress:
            return True, reason
        
        return False, ""
    
    def _check_action_repetition(self, memory: Any) -> Tuple[bool, str]:
        """Check if same action is repeated."""
        if not hasattr(memory, '_history'):
            return False, ""
        
        history = memory._history
        if len(history) < self.window_size:
            return False, ""
        
        # Get last N actions
        recent_actions = history[-self.window_size:]
        
        # Extract action signatures
        signatures = [self._extract_action_signature(entry) for entry in recent_actions]
        
        # Check if all signatures are identical
        if signatures and all(sig == signatures[0] for sig in signatures):
            action_type = signatures[0].get('type', 'unknown')
            return True, f"Action {action_type} repeated {self.window_size} times"
        
        return False, ""
    
    def _check_no_progress(self, observation: Any) -> Tuple[bool, str]:
        """Check if page state hasn't changed."""
        if not observation:
            return False, ""
        
        current_state = self._get_page_state(observation)
        
        if self.last_page_state == current_state:
            self.page_state_repeats += 1
        else:
            self.page_state_repeats = 0
            self.last_page_state = current_state
        
        if self.page_state_repeats >= self.no_progress_threshold:
            return True, "No page state change detected across steps"
        
        return False, ""
    
    def _extract_action_signature(self, entry: Any) -> Dict[str, Any]:
        """Extract unique action signature from memory entry."""
        sig = {
            'type': None,
            'selector': None,
            'value': None,
            'key': None
        }
        
        if not entry or not hasattr(entry, 'action'):
            return sig
        
        action = entry.action
        
        if hasattr(action, 'action_type'):
            sig['type'] = action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)
        if hasattr(action, 'selector'):
            sig['selector'] = action.selector
        if hasattr(action, 'value'):
            sig['value'] = action.value
        if hasattr(action, 'key'):
            sig['key'] = action.key
        
        return sig
    
    def _get_page_state(self, observation: Any) -> str:
        """Get hashable page state (URL + title hash)."""
        if not observation:
            return ""
        
        url = observation.url or ""
        title = ""
        if hasattr(observation, 'page_title'):
            title = observation.page_title or ""
        elif hasattr(observation, 'title'):
            title = observation.title or ""
        
        # Create hash of URL + title
        state_str = f"{url}|{title}"
        return hashlib.md5(state_str.encode()).hexdigest()


def should_stop(
    goal: str,
    observation: Any,
    memory: Any,
    last_action: Any,
    last_result: Any,
    completion_detector: CompletionDetector,
    repetition_detector: RepetitionDetector
) -> Tuple[bool, str]:
    """
    Main integration function: determine if agent should stop.
    
    Checks both completion and repetition conditions.
    
    Args:
        goal: User's goal string
        observation: Current page observation
        memory: MemoryStore instance
        last_action: Last executed action
        last_result: Result of last action
        completion_detector: CompletionDetector instance
        repetition_detector: RepetitionDetector instance
        
    Returns:
        (should_stop: bool, reason: str)
    """
    # Check for completion first
    is_complete, completion_reason = completion_detector.should_complete(
        goal, observation, memory, last_action, last_result
    )
    
    if is_complete:
        return True, completion_reason
    
    # Check for repetition/no-progress
    is_repetitive, repetition_reason = repetition_detector.is_repetition_detected(
        memory, observation
    )
    
    if is_repetitive:
        return True, repetition_reason
    
    # No stop condition met
    return False, ""
