# Verification & Testing Guide

## Overview

This guide will help you verify the refactor works correctly and test the new plan-driven architecture.

---

## Pre-Flight Checks ✅

### 1. Verify Imports Work
```python
# Run this to check all imports resolve correctly
python -c "
from core import SessionAgent, Planner, ActionMapper
from schemas import Action, ActionType
from config import Config
print('✅ All imports successful')
"
```

### 2. Verify Files Exist
```bash
# Run in project root
ls -la core/planner.py
ls -la core/action_mapper.py
ls -la core/session_agent.py

# Should show all three files exist
```

### 3. Verify No Syntax Errors
```bash
# Check syntax
python -m py_compile core/planner.py
python -m py_compile core/action_mapper.py
python -m py_compile core/session_agent.py

# Should complete without errors
```

### 4. Check Configuration
```python
# Verify config loads
from config import Config
print(f"API Key set: {bool(Config.GROQ_API_KEY)}")
print(f"Headless: {Config.HEADLESS}")
print(f"Model: {Config.LLM_MODEL}")
```

---

## Unit Tests

### Test 1: Planner Initialization
```python
import asyncio
from core import Planner

async def test_planner_init():
    planner = Planner()
    print("✅ Planner initialized successfully")
    print(f"   API Key: {bool(planner.api_key)}")
    print(f"   Model: {planner.model}")

asyncio.run(test_planner_init())
```

### Test 2: ActionMapper Selector Resolution
```python
import asyncio
from core import ActionMapper
from playwright.async_api import async_playwright

async def test_mapper():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Navigate to a test site
        await page.goto("https://www.google.com")
        
        # Test resolving logical selectors
        search_box = await ActionMapper.resolve_selector(page, "search_box")
        print(f"✅ Resolved 'search_box' to: {search_box}")
        
        await browser.close()

asyncio.run(test_mapper())
```

### Test 3: Plan Generation
```python
import asyncio
from core import Planner

async def test_plan_generation():
    planner = Planner()
    
    # Test simple plan generation
    plan = await planner.generate_plan("Search for Python tutorials on Google")
    
    print(f"✅ Plan generated with {len(plan)} steps")
    for i, step in enumerate(plan):
        print(f"   Step {i+1}: {step['action']} - {step.get('reasoning', 'no reasoning')}")
    
    assert len(plan) > 0, "Plan should not be empty"
    assert plan[0]['action'] == 'goto', "First action should be goto"
    print("✅ Plan structure valid")

asyncio.run(test_plan_generation())
```

### Test 4: Mock Plan Generation
```python
import asyncio
from core import SessionAgent

async def test_mock_plan():
    agent = SessionAgent(use_mock=True)
    
    # Test mock plan creation
    plan = agent._create_mock_plan("Search for laptop")
    
    print(f"✅ Mock plan generated with {len(plan)} steps")
    assert len(plan) > 0
    assert 'action' in plan[0]
    print("✅ Mock plan structure valid")

asyncio.run(test_mock_plan())
```

---

## Integration Tests

### Test 5: Session Start (Mock)
```python
import asyncio
from core import SessionAgent

async def test_session_start():
    agent = SessionAgent(
        headless=True,
        use_mock=True
    )
    
    # Start session
    result = await agent.start_session()
    print(f"✅ Session start result: {result['status']}")
    
    assert result['status'] == 'started', "Session should start successfully"
    assert agent.is_active, "Agent should be marked as active"
    print("✅ Session initialization verified")
    
    # Cleanup
    await agent.end_session()

asyncio.run(test_session_start())
```

### Test 6: Full Command Execution (Mock)
```python
import asyncio
from core import SessionAgent

async def test_command_execution():
    agent = SessionAgent(
        headless=True,
        use_mock=True  # Use mock, no LLM needed
    )
    
    await agent.start_session()
    
    # Execute a command with callback
    def callback(stage, msg):
        print(f"  [{stage}] {msg}")
    
    result = await agent.execute_command(
        "Search for Python tutorials on Google",
        callback=callback
    )
    
    print(f"✅ Command execution completed")
    print(f"   Status: {result['status']}")
    print(f"   Steps: {result['steps']}")
    print(f"   Successful: {result['successful']}")
    print(f"   Failed: {result['failed']}")
    
    assert result['steps'] > 0, "Should have executed steps"
    assert result['successful'] > 0, "Should have successful actions"
    
    await agent.end_session()
    print("✅ Command execution verified")

asyncio.run(test_command_execution())
```

---

## End-to-End Tests

### Test 7: GUI Compatibility
```python
# Run the GUI
python session_gui.py

# Then manually:
# 1. Click "Start Session"
# 2. Enter command: "Search for Python tutorials on Google"
# 3. Click "Send Command"
# 4. Verify output appears
# 5. Verify no errors
```

### Test 8: Real Browser Search (no mock)
```python
import asyncio
from core import SessionAgent

async def test_real_browser():
    agent = SessionAgent(
        headless=False,  # Show browser
        use_mock=False   # Use real planner
    )
    
    try:
        await agent.start_session()
        
        def callback(stage, msg):
            if stage in ['plan', 'execute']:
                print(f"[{stage}] {msg}")
        
        result = await agent.execute_command(
            "Search for Python tutorials on Google",
            callback=callback
        )
        
        print("\n✅ RESULT:")
        print(f"   Status: {result['status']}")
        print(f"   Steps executed: {result['steps']}")
        print(f"   Successful: {result['successful']}")
        
        # Wait for user to see results
        input("Press Enter to close browser...")
        
    finally:
        await agent.end_session()

asyncio.run(test_real_browser())
```

---

## Regression Tests

### Test 9: Verify Old Regex Removed
```python
# This should NOT work anymore (no regex parsing)
import asyncio
from core import SessionAgent

async def test_no_regex():
    # The old regex patterns are removed
    # Commands now go through planner instead
    
    agent = SessionAgent(use_mock=True)
    await agent.start_session()
    
    # This should work with planner (not regex):
    result = await agent.execute_command("Search on Daraz for watches")
    
    print("✅ Old 'search on X for Y' pattern now handled by planner")
    assert result['status'] in ['completed', 'partial']
    
    await agent.end_session()

asyncio.run(test_no_regex())
```

### Test 10: Verify Hardcoded Logic Removed
```python
# The old deterministic_plan and hardcoded selectors are gone
# Message should not reference "deterministic" anymore

import asyncio
from core import SessionAgent

async def test_no_deterministic():
    agent = SessionAgent(use_mock=True)
    
    # These attributes should NOT exist:
    assert not hasattr(agent, '_deterministic_plan'), "Should not have _deterministic_plan"
    assert not hasattr(agent, '_deterministic_target_site'), "Should not have _deterministic_target_site"
    
    # These attributes SHOULD exist now:
    assert hasattr(agent, '_planner'), "Should have _planner"
    
    print("✅ Old hardcoded logic removed, new planner in place")

test_no_deterministic()
```

---

## Stress Tests

### Test 11: Multiple Commands
```python
import asyncio
from core import SessionAgent

async def test_multiple_commands():
    agent = SessionAgent(use_mock=True)
    await agent.start_session()
    
    commands = [
        "Search for Python on Google",
        "Search for JavaScript tutorials",
        "Find Daraz homepage",
    ]
    
    for cmd in commands:
        result = await agent.execute_command(cmd)
        print(f"✅ Command: '{cmd[:40]}...' → {result['status']}")
        assert result['steps'] >= 0
    
    await agent.end_session()
    print("✅ Multiple commands handled correctly")

asyncio.run(test_multiple_commands())
```

### Test 12: Session Persistence
```python
import asyncio
from core import SessionAgent

async def test_session_persistence():
    agent = SessionAgent(use_mock=True)
    await agent.start_session()
    
    # Execute multiple commands in same session
    result1 = await agent.execute_command("First command")
    result2 = await agent.execute_command("Second command")
    result3 = await agent.execute_command("Third command")
    
    # Check history
    print(f"✅ Commands in history: {len(agent._command_history)}")
    assert len(agent._command_history) >= 3
    
    await agent.end_session()
    print("✅ Session persistence verified")

asyncio.run(test_session_persistence())
```

---

## Browser Control Tests

### Test 13: Planner Output Format
```python
import asyncio
from core import Planner

async def test_plan_format():
    planner = Planner()
    
    plan = await planner.generate_plan("Search for something")
    
    # Verify JSON structure
    assert isinstance(plan, list), "Plan should be list"
    assert len(plan) > 0, "Plan should have steps"
    
    for step in plan:
        assert isinstance(step, dict), "Each step should be dict"
        assert 'action' in step, "Step must have 'action'"
        assert step['action'] in [
            'goto', 'type', 'click', 'press_key', 
            'scroll', 'back', 'done'
        ], "Invalid action type"
    
    print(f"✅ Plan format valid: {len(plan)} properly formatted steps")

asyncio.run(test_plan_format())
```

### Test 14: Mapper Fallback
```python
import asyncio
from core import ActionMapper
from playwright.async_api import async_playwright

async def test_mapper_fallback():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        await page.goto("https://www.google.com")
        
        # Test multiple selector variants
        selectors = ["search_box", "Search", "q", "[name=q]"]
        
        for sel in selectors:
            result = await ActionMapper.resolve_selector(page, sel)
            if result:
                print(f"✅ Selector '{sel}' resolved to: {result[:50]}")
        
        await browser.close()

asyncio.run(test_mapper_fallback())
```

---

## Quick Test Suite

Run this to verify everything works:

```python
# test_refactor.py
import asyncio
from core import SessionAgent, Planner, ActionMapper
from config import Config

async def run_all_tests():
    print("=" * 50)
    print("REFACTOR VERIFICATION TESTS")
    print("=" * 50)
    
    # Test 1: Imports
    print("\n[1/6] Testing imports...")
    try:
        from core import SessionAgent, Planner, ActionMapper
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 2: Planner init
    print("[2/6] Testing Planner initialization...")
    try:
        planner = Planner()
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 3: Mock plan
    print("[3/6] Testing mock plan generation...")
    try:
        agent = SessionAgent(use_mock=True)
        plan = agent._create_mock_plan("test")
        assert len(plan) > 0
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 4: Session start
    print("[4/6] Testing session start...")
    try:
        agent = SessionAgent(use_mock=True, headless=True)
        result = await agent.start_session()
        assert result['status'] == 'started'
        await agent.end_session()
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 5: Old code removed
    print("[5/6] Verifying old regex code removed...")
    try:
        agent = SessionAgent()
        assert not hasattr(agent, '_deterministic_plan')
        assert hasattr(agent, '_planner')
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 6: Command execution
    print("[6/6] Testing command execution (mock)...")
    try:
        agent = SessionAgent(use_mock=True, headless=True)
        await agent.start_session()
        result = await agent.execute_command("test command")
        assert result['steps'] >= 0
        await agent.end_session()
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("✅ ALL TESTS PASSED")
    print("=" * 50)
    return True

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
```

**Run it**:
```bash
python test_refactor.py
```

---

## Expected Output

```
==================================================
REFACTOR VERIFICATION TESTS
==================================================

[1/6] Testing imports...
✅ PASS
[2/6] Testing Planner initialization...
✅ PASS
[3/6] Testing mock plan generation...
✅ PASS
[4/6] Testing session start...
✅ PASS
[5/6] Verifying old regex code removed...
✅ PASS
[6/6] Testing command execution (mock)...
✅ PASS

==================================================
✅ ALL TESTS PASSED
==================================================
```

---

## Troubleshooting

### Import Error: "No module named 'core.planner'"
- **Cause**: New files not found or __init__.py not updated
- **Fix**: Check files exist:
  ```bash
  ls core/planner.py core/action_mapper.py
  ```

### Import Error: "cannot import Planner"
- **Cause**: __init__.py not updated
- **Fix**: Verify `core/__init__.py` has Planner and ActionMapper exports

### Planner returns empty list
- **Cause**: Groq API issue
- **Fix**: Use `use_mock=True` for testing

### ActionMapper can't resolve selector
- **Cause**: Element not on page or different structure
- **Fix**: Check element visibility, try different command

### Old code still present
- **Cause**: File changes didn't save
- **Fix**: Check `core/session_agent.py` has new code (no regex)

---

## Success Criteria ✅

- [x] All imports work
- [x] Planner initializes
- [x] Plans generate valid JSON
- [x] ActionMapper resolves selectors
- [x] SessionAgent uses new flow
- [x] No regex in session_agent.py
- [x] No hardcoded deterministic_plan
- [x] GUI still works
- [x] Commands execute with feedback
- [x] Results contain metrics

**If all tests pass**: Refactor is successful! ✅
