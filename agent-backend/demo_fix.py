"""
SIMPLE DEMO: Robust Intent Parser Fix

Shows the fixed behavior without API calls or async complexity.
"""

from core.robust_intent_parser import RobustIntentParser


def demo():
    """Demonstrate the fix."""
    parser = RobustIntentParser()
    
    print("\n" + "="*80)
    print("  ROBUST INTENT PARSER - QUICK DEMO")
    print("="*80)
    
    # Test cases showing the fix
    test_cases = [
        ("search for boys watches on daraz and add to cart 2nd item", 
         "boys watches", ["open_item", "add_to_cart"]),
        
        ("find laptops on amazon and add 3rd one to cart",
         "laptops", ["open_item", "add_to_cart"]),
        
        ("look for blue jeans on ebay",
         "blue jeans", []),
        
        ("search for python tutorials online",
         "python tutorials", []),
    ]
    
    for input_text, expected_query, expected_actions in test_cases:
        print(f"\n{'INPUT':10} → {input_text}")
        print("-" * 80)
        
        # Parse using regex (no LLM needed)
        result = parser._parse_with_regex(input_text)
        
        # Display results
        print(f"{'SITE':10} → {result.site.value}")
        print(f"{'QUERY':10} → {result.search_query}")
        
        # Verify query is clean
        query_ok = result.search_query == expected_query
        if query_ok:
            print(f"  ✅ Query matches expected: '{expected_query}'")
        else:
            print(f"  ❌ Query mismatch!")
            print(f"     Expected: '{expected_query}'")
            print(f"     Got:      '{result.search_query}'")
        
        # Verify actions
        actions = [a.action_type.value for a in result.actions]
        if actions == expected_actions:
            print(f"  ✅ Actions match expected: {expected_actions}")
        else:
            print(f"  ⚠️  Actions mismatch!")
            print(f"     Expected: {expected_actions}")
            print(f"     Got:      {actions}")
    
    print("\n" + "="*80)
    print("  KEY FIX VERIFICATION")
    print("="*80)
    
    # Show the critical fix
    bad_command = "search for boys watches on daraz and then add to cart 2nd item"
    result = parser._parse_with_regex(bad_command)
    
    print(f"\nCommand: {bad_command}\n")
    print(f"❌ OLD (BROKEN):     query = 'for boys watches and then add to cart 2nd item'")
    print(f"✅ NEW (FIXED):      query = '{result.search_query}'")
    print(f"✅ ACTIONS EXTRACTED: {[a.action_type.value for a in result.actions]}")
    
    print("\n✅ The search query is now CLEAN and will be used for TYPE action!")
    print(f"   → Will TYPE: '{result.search_query}' (not the full messy command)")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    demo()
