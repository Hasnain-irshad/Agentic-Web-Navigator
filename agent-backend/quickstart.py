#!/usr/bin/env python
"""
Quick start and environment validation script.
Run this to verify your setup is correct.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def check_imports():
    """Check if all required packages are installed."""
    print("Checking imports...")
    required = {
        "playwright": "Playwright (browser automation)",
        "groq": "Groq (LLM API)",
        "dotenv": "python-dotenv (environment)",
    }
    
    missing = []
    for module, name in required.items():
        try:
            __import__(module)
            print(f"  ✓ {name}")
        except ImportError:
            print(f"  ✗ {name} - NOT INSTALLED")
            missing.append(module)
    
    return len(missing) == 0


def check_config():
    """Check if configuration is valid."""
    print("\nChecking configuration...")
    try:
        from config import Config
        
        # Check API key
        if Config.GROQ_API_KEY:
            print(f"  ✓ GROQ_API_KEY configured")
        else:
            print(f"  ⚠ GROQ_API_KEY not set (required for real mode)")
        
        print(f"  ✓ Model: {Config.LLM_MODEL}")
        print(f"  ✓ Max steps: {Config.MAX_STEPS}")
        print(f"  ✓ Headless: {Config.HEADLESS}")
        
        return True
    except Exception as e:
        print(f"  ✗ Configuration error: {e}")
        return False


def check_project_structure():
    """Check if all project files exist."""
    print("\nChecking project structure...")
    required_files = [
        "main.py",
        "config.py",
        "requirements.txt",
        "core/browser_controller.py",
        "core/observation_extractor.py",
        "core/agent_reasoner.py",
        "core/memory_store.py",
        "schemas/actions.py",
        "utils/logger.py",
        "utils/validators.py",
    ]
    
    all_exist = True
    for file in required_files:
        file_path = project_root / file
        if file_path.exists():
            print(f"  ✓ {file}")
        else:
            print(f"  ✗ {file} - NOT FOUND")
            all_exist = False
    
    return all_exist


async def test_mock_agent():
    """Test agent with mock reasoner (no API calls)."""
    print("\nTesting agent with mock reasoner...")
    try:
        from main import WebNavigatorAgent
        
        agent = WebNavigatorAgent(
            goal="Test navigation to Google",
            max_steps=3,
            headless=True,
            use_mock=True,
        )
        
        result = await agent.run()
        
        if result.get("status") == "error":
            print(f"  ✗ Agent test failed: {result.get('error')}")
            return False
        
        print(f"  ✓ Mock agent executed successfully")
        print(f"    Steps: {result.get('total_steps')}")
        print(f"    Status: {result.get('status')}")
        return True
        
    except Exception as e:
        print(f"  ✗ Agent test failed: {e}")
        return False


async def main():
    """Run all checks."""
    print("=" * 60)
    print("AGENTIC WEB NAVIGATOR - QUICK START & VALIDATION")
    print("=" * 60)
    
    checks = [
        ("Package imports", check_imports()),
        ("Configuration", check_config()),
        ("Project structure", check_project_structure()),
    ]
    
    # Run async test
    print("\nTesting agent functionality...")
    try:
        mock_test = await test_mock_agent()
        checks.append(("Mock agent execution", mock_test))
    except Exception as e:
        print(f"  ✗ Could not run mock test: {e}")
        checks.append(("Mock agent execution", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    for check_name, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:8} | {check_name}")
    
    all_passed = all(passed for _, passed in checks)
    
    print("=" * 60)
    if all_passed:
        print("\n✓ Setup is valid! You're ready to use the navigator.")
        print("\nQuick start:")
        print("  python main.py --goal \"Your task here\" --visible --mock")
        print("\nAfter setting GROQ_API_KEY in .env:")
        print("  python main.py --goal \"Your task here\" --visible")
    else:
        print("\n✗ Some checks failed. Please see errors above.")
        print("\nCommon fixes:")
        print("  1. Install dependencies: pip install -r requirements.txt")
        print("  2. Install Playwright: playwright install chromium")
        print("  3. Create .env file: cp .env.template .env")
        print("  4. Add GROQ_API_KEY to .env (get from https://console.groq.com)")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
