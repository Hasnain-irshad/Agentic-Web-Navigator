#!/usr/bin/env python
"""
Test suite and demo for Agentic Web Navigator.

Run examples to verify system works correctly.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import Config
from core import BrowserController, ObservationExtractor, AgentReasoner
from core.agent_reasoner import MockReasoner
from schemas import Action, ActionType
from utils import get_logger


logger = get_logger(__name__)


# ==============================================================================
# TEST 1: Browser Controller
# ==============================================================================

async def test_browser_controller():
    """Test BrowserController basic functionality."""
    print("\n" + "=" * 70)
    print("TEST 1: BrowserController")
    print("=" * 70)
    
    try:
        async with BrowserController(headless=True) as browser:
            print("✓ Browser started")
            
            # Get current page
            page = await browser.get_current_page()
            print("✓ Got current page")
            
            # Test GOTO
            action = Action(
                action_type=ActionType.GOTO,
                value="https://example.com",
                reasoning="Test navigation"
            )
            result = await browser.execute_action(action)
            print(f"✓ GOTO action: {result.message}")
            
            # Test SCROLL
            action = Action(
                action_type=ActionType.SCROLL,
                direction="down",
                reasoning="Test scroll"
            )
            result = await browser.execute_action(action)
            print(f"✓ SCROLL action: {result.message}")
            
            # Test BACK
            action = Action(
                action_type=ActionType.BACK,
                reasoning="Test back"
            )
            result = await browser.execute_action(action)
            print(f"✓ BACK action: {result.message}")
            
            print("\n✓ BrowserController test PASSED")
            return True
            
    except Exception as e:
        print(f"\n✗ BrowserController test FAILED: {e}")
        return False


# ==============================================================================
# TEST 2: Observation Extractor
# ==============================================================================

async def test_observation_extractor():
    """Test ObservationExtractor functionality."""
    print("\n" + "=" * 70)
    print("TEST 2: ObservationExtractor")
    print("=" * 70)
    
    try:
        extractor = ObservationExtractor(max_elements=20)
        
        async with BrowserController(headless=True) as browser:
            # Navigate to example.com
            page = await browser.get_current_page()
            await page.goto("https://example.com")
            
            # Extract observation
            observation = await extractor.extract(page)
            
            print(f"✓ Extracted observation from: {observation.url}")
            print(f"  - Title: {observation.title}")
            print(f"  - Elements found: {len(observation.elements)}")
            
            # Print elements
            if observation.elements:
                print(f"  - Element types: {set(e.element_type for e in observation.elements)}")
                for i, elem in enumerate(observation.elements[:3], 1):
                    print(f"    [{i}] {elem.element_type}: {elem.text[:50]}")
            
            # Check observation formatting
            prompt_text = observation.to_prompt_text()
            print(f"✓ Generated LLM prompt ({len(prompt_text)} chars)")
            
            print("\n✓ ObservationExtractor test PASSED")
            return True
            
    except Exception as e:
        print(f"\n✗ ObservationExtractor test FAILED: {e}")
        return False


# ==============================================================================
# TEST 3: Memory Store
# ==============================================================================

def test_memory_store():
    """Test MemoryStore functionality."""
    print("\n" + "=" * 70)
    print("TEST 3: MemoryStore")
    print("=" * 70)
    
    try:
        from core.memory_store import MemoryStore
        from core.observation_extractor import Observation
        
        memory = MemoryStore(
            goal="Test memory store",
            max_steps=10
        )
        
        print("✓ MemoryStore created")
        print(f"  - Goal: {memory.goal}")
        print(f"  - Max steps: {memory.max_steps}")
        print(f"  - Current step: {memory.step_count}")
        
        # Add an entry
        action = Action(
            action_type=ActionType.GOTO,
            value="https://example.com",
            reasoning="Test"
        )
        
        from schemas import ActionResult
        result = ActionResult(
            success=True,
            message="Test navigation"
        )
        
        observation = Observation(
            url="https://example.com",
            title="Example Domain"
        )
        
        memory.add_entry(action, result, observation)
        print("✓ Added memory entry")
        print(f"  - Step count: {memory.step_count}")
        
        # Get context
        context = memory.get_context(observation)
        print("✓ Generated context for LLM")
        print(f"  - History entries: {len(context.history)}")
        
        # Get summary
        summary = memory.get_summary()
        print("✓ Generated summary")
        print(f"  - Status: {summary['status']}")
        print(f"  - Total steps: {summary['total_steps']}")
        
        print("\n✓ MemoryStore test PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ MemoryStore test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# TEST 4: Action Schema
# ==============================================================================

def test_action_schema():
    """Test Action schema and validation."""
    print("\n" + "=" * 70)
    print("TEST 4: Action Schema")
    print("=" * 70)
    
    try:
        # Test GOTO
        action = Action(
            action_type=ActionType.GOTO,
            value="example.com",
            reasoning="Test"
        )
        print(f"✓ GOTO action: {action.value}")
        
        # Test CLICK
        action = Action(
            action_type=ActionType.CLICK,
            selector="Search",
            reasoning="Test"
        )
        print(f"✓ CLICK action: {action.selector}")
        
        # Test TYPE
        action = Action(
            action_type=ActionType.TYPE,
            selector="search box",
            value="test query",
            reasoning="Test"
        )
        print(f"✓ TYPE action: {action.value}")
        
        # Test SCROLL
        action = Action(
            action_type=ActionType.SCROLL,
            direction="down",
            reasoning="Test"
        )
        print(f"✓ SCROLL action: {action.direction}")
        
        # Test serialization
        action_dict = action.to_dict()
        print(f"✓ Serialized to dict: {action_dict['action_type']}")
        
        # Test deserialization
        action2 = Action.from_dict(action_dict)
        print(f"✓ Deserialized from dict: {action2.action_type.value}")
        
        # Test validation
        try:
            bad_action = Action(
                action_type=ActionType.CLICK,
                # Missing required selector
            )
            print("✗ Validation should have failed!")
            return False
        except ValueError as e:
            print(f"✓ Validation caught error: {str(e)[:50]}...")
        
        print("\n✓ Action Schema test PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ Action Schema test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# TEST 5: Mock Reasoner
# ==============================================================================

async def test_mock_reasoner():
    """Test MockReasoner functionality."""
    print("\n" + "=" * 70)
    print("TEST 5: MockReasoner")
    print("=" * 70)
    
    try:
        from core.memory_store import MemoryStore
        from core.observation_extractor import Observation
        
        reasoner = MockReasoner()
        print("✓ MockReasoner created")
        
        # Create a context
        memory = MemoryStore("Test task", 10)
        observation = Observation(
            url="https://example.com",
            title="Test"
        )
        context = memory.get_context(observation)
        
        # Get action 1
        action = await reasoner.decide_action(context)
        print(f"✓ Action 1: {action.action_type.value}")
        
        # Get action 2
        action = await reasoner.decide_action(context)
        print(f"✓ Action 2: {action.action_type.value}")
        
        # Get action 3
        action = await reasoner.decide_action(context)
        print(f"✓ Action 3: {action.action_type.value}")
        
        print("\n✓ MockReasoner test PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ MockReasoner test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# TEST 6: Configuration
# ==============================================================================

def test_configuration():
    """Test Configuration loading."""
    print("\n" + "=" * 70)
    print("TEST 6: Configuration")
    print("=" * 70)
    
    try:
        print(f"✓ GROQ_API_KEY: {'*' * 10 if Config.GROQ_API_KEY else 'NOT SET'}")
        print(f"✓ LLM_MODEL: {Config.LLM_MODEL}")
        print(f"✓ LLM_TEMPERATURE: {Config.LLM_TEMPERATURE}")
        print(f"✓ LLM_MAX_TOKENS: {Config.LLM_MAX_TOKENS}")
        print(f"✓ HEADLESS: {Config.HEADLESS}")
        print(f"✓ BROWSER_TIMEOUT: {Config.BROWSER_TIMEOUT}")
        print(f"✓ MAX_STEPS: {Config.MAX_STEPS}")
        print(f"✓ OBSERVATION_MAX_ELEMENTS: {Config.OBSERVATION_MAX_ELEMENTS}")
        
        print("\n✓ Configuration test PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ Configuration test FAILED: {e}")
        return False


# ==============================================================================
# MAIN TEST RUNNER
# ==============================================================================

async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("AGENTIC WEB NAVIGATOR - TEST SUITE")
    print("=" * 70)
    
    results = []
    
    # Sync tests
    results.append(("Configuration", test_configuration()))
    results.append(("Action Schema", test_action_schema()))
    results.append(("MemoryStore", test_memory_store()))
    
    # Async tests
    results.append(("BrowserController", await test_browser_controller()))
    results.append(("ObservationExtractor", await test_observation_extractor()))
    results.append(("MockReasoner", await test_mock_reasoner()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:10} | {test_name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print("=" * 70)
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    return all(p for _, p in results)


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
