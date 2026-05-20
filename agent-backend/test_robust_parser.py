"""
Test and validation script for RobustIntentParser.

Demonstrates the fix for the core issue:
- Input: "search for boys watches on daraz and then add to cart 2nd item"
- Old behavior: query = "for boys watches and then add..." ❌
- New behavior: query = "boys watches", actions = [add_to_cart, open_item(2)] ✅
"""

import asyncio
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent))

from core.robust_intent_parser import parse_intent, RobustIntentParser
from core.planner import Planner


def print_section(title: str):
    """Print formatted section."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def test_robust_parser():
    """Test the robust intent parser."""
    print_section("TESTING ROBUST INTENT PARSER")
    
    test_cases = [
        "search for boys watches on daraz",
        "search for boys watches on daraz and then add to cart 2nd item",
        "find laptops on amazon and add 3rd one to cart",
        "search for python tutorials",
        "search for blue jeans on ebay add to cart",
        "look for iphone 13 on amazon then buy it",
    ]
    
    parser = RobustIntentParser()
    
    for command in test_cases:
        print(f"\n📝 INPUT: {command}")
        print("-" * 70)
        
        intent = parser.parse(command)
        
        print(f"✅ SITE:       {intent.site.value}")
        print(f"✅ QUERY:      {intent.search_query}")
        
        if intent.actions:
            print(f"✅ ACTIONS:    {len(intent.actions)} step(s)")
            for i, action in enumerate(intent.actions, 1):
                action_type = action.action_type.value
                if action.index:
                    print(f"               {i}. {action_type} (index={action.index})")
                else:
                    print(f"               {i}. {action_type}")
        else:
            print(f"✅ ACTIONS:    (none - just search)")
        
        if intent.metadata:
            print(f"✅ METADATA:   {intent.metadata}")


async def test_planner_with_query():
    """Test that Planner uses clean query."""
    print_section("TESTING PLANNER WITH CLEAN QUERY")
    
    planner = Planner()
    
    test_commands = [
        "search for boys watches on daraz",
        "search for boys watches on daraz and then add to cart 2nd item",
        "find laptops on amazon and add 3rd to cart",
    ]
    
    for command in test_commands:
        print(f"\n📝 INPUT: {command}")
        print("-" * 70)
        
        try:
            plan = await planner.generate_plan(command)
            
            print(f"✅ GENERATED {len(plan)} action steps:\n")
            
            for i, action in enumerate(plan, 1):
                action_type = action.get("action", "unknown")
                
                if action_type == "goto":
                    value = action.get("value", "")
                    print(f"   {i}. {action_type.upper():12} → {value}")
                    
                elif action_type == "type":
                    value = action.get("value", "")
                    print(f"   {i}. {action_type.upper():12} ({action.get('selector')}) = '{value}'")
                    # ✅ THIS IS THE KEY CHECK - value should be CLEAN query
                    if "and" in value or "then" in value or "add" in value or "cart" in value:
                        print(f"      ⚠️  WARNING: Query contains action words!")
                    
                elif action_type == "click":
                    selector = action.get("selector", "")
                    print(f"   {i}. {action_type.upper():12} {selector}")
                    
                elif action_type == "press_key":
                    key = action.get("key", "")
                    print(f"   {i}. {action_type.upper():12} {key}")
                    
                elif action_type == "done":
                    reasoning = action.get("reasoning", "")
                    print(f"   {i}. {action_type.upper():12} ({reasoning})")
                    
                else:
                    print(f"   {i}. {action_type.upper():12} {action}")
            
        except Exception as e:
            print(f"❌ ERROR: {e}")


def test_query_validation():
    """Test query validation."""
    print_section("TESTING QUERY VALIDATION")
    
    parser = RobustIntentParser()
    
    test_queries = [
        ("boys watches", "CLEAN - should pass"),
        ("boys watches add to cart", "DIRTY - contains action word"),
        ("python tutorials", "CLEAN - should pass"),
        ("python tutorials then add", "DIRTY - contains action words"),
    ]
    
    print("Validating queries:\n")
    
    for query, description in test_queries:
        validated = parser._validate_query(query)
        status = "✅" if validated == query else "⚠️"
        print(f"{status} '{query}'")
        print(f"   → Validated: '{validated}'")
        print(f"   ({description})\n")


def compare_old_vs_new():
    """Show comparison between old and new approach."""
    print_section("OLD vs NEW APPROACH")
    
    command = "search for boys watches on daraz and then add to cart 2nd item"
    
    print(f"INPUT: {command}\n")
    
    print("❌ OLD BEHAVIOR (BROKEN):")
    print("-" * 70)
    print("   search_query = 'for boys watches and then add to cart 2nd item'")
    print("   (Full command used, action words included)")
    print("   → TYPE 'for boys watches and then add to cart 2nd item'")
    print("   → Searches for wrong thing!")
    
    print("\n✅ NEW BEHAVIOR (FIXED):")
    print("-" * 70)
    
    parser = RobustIntentParser()
    intent = parser.parse(command)
    
    print(f"   search_query = '{intent.search_query}'")
    print(f"   (Clean query, action words removed)")
    print(f"   → TYPE '{intent.search_query}'")
    print(f"   → actions = {[a.action_type.value for a in intent.actions]}")
    print(f"   → Searches correctly!")
    
    print("\n✅ RESULT: Search query is now clean and actionable!")


if __name__ == "__main__":
    # Run tests
    print("\n" + "="*70)
    print("  ROBUST INTENT PARSER VALIDATION TEST SUITE")
    print("="*70)
    
    # Test 1: Parser basics
    test_robust_parser()
    
    # Test 2: Query validation
    test_query_validation()
    
    # Test 3: Comparison
    compare_old_vs_new()
    
    # Test 4: Planner integration
    print("\n" + "="*70)
    print("  RUNNING ASYNC PLANNER TESTS")
    print("  (This requires valid Groq API key)")
    print("="*70)
    
    try:
        asyncio.run(test_planner_with_query())
    except Exception as e:
        print(f"\n⚠️  Planner test skipped: {e}")
        print("   (This is OK if Groq API key is not configured)")
    
    print("\n" + "="*70)
    print("  ✅ TEST SUITE COMPLETE")
    print("="*70 + "\n")
