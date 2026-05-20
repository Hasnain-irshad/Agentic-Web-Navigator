"""
Validation helpers for the Agentic Web Navigator.
"""

from urllib.parse import urlparse
from typing import Optional


def is_valid_url(url: str) -> bool:
    """
    Validate if a string is a valid URL.
    
    Args:
        url: String to validate
        
    Returns:
        True if valid URL, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except (ValueError, TypeError):
        return False


def normalize_url(url: str) -> str:
    """
    Normalize a URL string.
    
    Adds https:// if no scheme is provided.
    
    Args:
        url: URL string to normalize
        
    Returns:
        Normalized URL
    """
    if not url:
        return ""
    
    # Add https:// if no scheme
    if not url.startswith(("http://", "https://", "ftp://")):
        url = f"https://{url}"
    
    return url


def validate_selector(selector: str) -> bool:
    """
    Validate if a selector string is reasonable.
    
    Args:
        selector: Selector string
        
    Returns:
        True if selector seems valid
    """
    if not selector or not isinstance(selector, str):
        return False
    
    # Should be at least 2 characters
    return len(selector.strip()) >= 2


def validate_action_value(value: Optional[str]) -> bool:
    """
    Validate action value parameters.
    
    Args:
        value: Value to validate
        
    Returns:
        True if valid
    """
    if value is None:
        return True
    
    if not isinstance(value, str):
        return False
    
    # Should be reasonable length for browser actions
    return 0 <= len(value) <= 5000
