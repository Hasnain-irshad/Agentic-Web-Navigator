import re

ord_pattern = r"(?P<ord>first|1st|second|2nd|third|3rd|fourth|4th|\d+(?:st|nd|rd|th)?)"
goal = "add to cart 2nd item"

try:
    print(f"Testing goal: '{goal}'")
    # NEW logic from session_agent.py
    m_add_only = re.search(rf"(?:add(?: to)?\s+cart).*{ord_pattern}", goal, re.IGNORECASE)
    if not m_add_only:
        m_add_only = re.search(rf"{ord_pattern}.*(?:add(?: to)?\s+cart)", goal, re.IGNORECASE)
        
    if m_add_only:
        print(f"MATCH SUCCESS: {m_add_only.group(0)}")
        if m_add_only.groupdict().get('ord'):
             print(f"Captured ord: {m_add_only.group('ord')}")
    else:
        print("NO MATCH - but no error either (which is good if no match expected)")

except Exception as e:
    print(f"FAILED with error: {e}")
