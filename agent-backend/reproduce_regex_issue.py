import re

ord_pattern = r"(?P<ord>first|1st|second|2nd|third|3rd|fourth|4th|\d+(?:st|nd|rd|th)?)"
goal = "add to cart 2nd item"

try:
    # This matches the logic in session_agent.py line 175
    # Warning: this uses duplicate named group 'ord'
    m_add_only = re.search(rf"(?:add(?: to)?\s+cart).*{ord_pattern}|{ord_pattern}.*(?:add(?: to)?\s+cart)", goal, re.IGNORECASE)
    print(f"Match found: {m_add_only}")
except Exception as e:
    print(f"FAILED with error: {e}")
