"""
API REFERENCE - Agentic AI Web Navigator

Complete API documentation for all public classes and methods.
"""

# ==============================================================================
# TABLE OF CONTENTS
# ==============================================================================

1. WebNavigatorAgent - Main orchestrator
2. BrowserController - Browser automation
3. ObservationExtractor - Element extraction
4. AgentReasoner - LLM reasoning
5. MemoryStore - Context management
6. Action - Action schema
7. Config - Configuration

# ==============================================================================
# 1. WebNavigatorAgent
# ==============================================================================

from main import WebNavigatorAgent

CONSTRUCTOR
───────────
WebNavigatorAgent(
    goal: str,
    max_steps: int | None = None,
    headless: bool | None = None,
    use_mock: bool = False
)

Parameters:
  goal (str)
    Natural language task description.
    Example: "Search for Python on Google"
    Required: Yes

  max_steps (int | None)
    Maximum number of steps to execute.
    Default: Config.MAX_STEPS (20)
    Range: 1-100 (recommended)
    
  headless (bool | None)
    Whether to run browser hidden.
    True = hidden (faster)
    False = visible (for debugging)
    Default: Config.HEADLESS (True)
    
  use_mock (bool)
    Use MockReasoner instead of LLM.
    True = no API calls, predefined behavior
    False = real Groq LLM calls
    Default: False

ASYNC METHOD: run()
──────────────────
async def run() -> dict:

Returns: Task execution summary dictionary

Return Dictionary Structure:
{
    "goal": str,              # Original task
    "status": str,            # "completed" | "failed" | "incomplete" | "error"
    "total_steps": int,       # Steps executed
    "max_steps": int,         # Step limit
    "successful_actions": int, # Actions that succeeded
    "failed_actions": int,    # Actions that failed
    "action_sequence": [
        {
            "step": int,
            "action": str,           # e.g., "goto", "click", "type"
            "success": bool,
            "message": str,          # Result description
        },
        ...
    ],
    "error": str | None,      # Error message if failed
}

Usage Example:
──────────────
import asyncio
from main import WebNavigatorAgent

async def main():
    agent = WebNavigatorAgent(
        goal="Search for Python on Google",
        max_steps=10,
        headless=False,
        use_mock=False
    )
    
    result = await agent.run()
    
    print(f"Status: {result['status']}")
    print(f"Steps: {result['total_steps']}")
    print(f"Successful: {result['successful_actions']}")

asyncio.run(main())


# ==============================================================================
# 2. BrowserController
# ==============================================================================

from core.browser_controller import BrowserController

CLASS: BrowserController
─────────────────────────

Manages Playwright browser lifecycle and action execution.

CONSTRUCTOR
───────────
BrowserController(headless: bool | None = None)

Parameters:
  headless (bool | None)
    Browser display mode.
    Default: Config.HEADLESS

ASYNC CONTEXT MANAGER
─────────────────────
async with BrowserController() as browser:
    # Browser is available here
    result = await browser.execute_action(action)
# Browser is automatically closed

ASYNC METHODS

start() → None
  Launch browser instance.
  Called automatically in async context manager.
  
  Raises: RuntimeError if browser fails to start

stop() → None
  Close browser and cleanup resources.
  Called automatically in async context manager.

get_current_page() → Page
  Get the currently active Playwright Page object.
  
  Returns: Playwright Page object
  Raises: RuntimeError if no page is available

execute_action(action: Action) → ActionResult
  Execute a browser action.
  
  Parameters:
    action (Action): Action to execute
  
  Returns: ActionResult with success/failure details
  
  Example:
    action = Action(
        action_type=ActionType.GOTO,
        value="https://example.com",
        reasoning="Navigate to example"
    )
    result = await browser.execute_action(action)
    print(result.message)

Usage Example:
──────────────
async def navigate():
    async with BrowserController(headless=False) as browser:
        # Navigate to a website
        action = Action(
            action_type=ActionType.GOTO,
            value="https://google.com",
            reasoning="Go to Google"
        )
        result = await browser.execute_action(action)
        
        if result.success:
            page = await browser.get_current_page()
            print(f"Current URL: {page.url}")
        else:
            print(f"Error: {result.message}")


# ==============================================================================
# 3. ObservationExtractor
# ==============================================================================

from core.observation_extractor import ObservationExtractor, Observation

CLASS: ObservationExtractor
────────────────────────────

Extracts visible, interactive page elements.

CONSTRUCTOR
───────────
ObservationExtractor(max_elements: int | None = None)

Parameters:
  max_elements (int | None)
    Maximum number of elements to extract.
    Default: Config.OBSERVATION_MAX_ELEMENTS (50)

ASYNC METHOD: extract()
───────────────────────
async def extract(page: Page) -> Observation

Extracts observable state from current page.

Parameters:
  page (Page): Playwright Page object

Returns: Observation object containing:
  - url (str): Current page URL
  - title (str): Page title
  - elements (list[PageElement]): Interactive elements
  - page_text (str): Visible text summary
  - error (str): Error message if extraction failed

Usage Example:
──────────────
from core import ObservationExtractor, BrowserController

async def observe_page():
    async with BrowserController() as browser:
        extractor = ObservationExtractor(max_elements=30)
        
        page = await browser.get_current_page()
        await page.goto("https://example.com")
        
        observation = await extractor.extract(page)
        
        print(f"URL: {observation.url}")
        print(f"Title: {observation.title}")
        print(f"Elements found: {len(observation.elements)}")
        
        for elem in observation.elements:
            print(f"  [{elem.element_type}] {elem.text}")


# ==============================================================================
# 4. AgentReasoner
# ==============================================================================

from core.agent_reasoner import AgentReasoner, MockReasoner
from core.memory_store import Context

CLASS: AgentReasoner
────────────────────

LLM-based decision engine using Groq.

CONSTRUCTOR
───────────
AgentReasoner(
    api_key: str | None = None,
    model: str | None = None
)

Parameters:
  api_key (str | None)
    Groq API key.
    Default: Config.GROQ_API_KEY from .env
    Required: Yes
    
  model (str | None)
    LLM model to use.
    Default: Config.LLM_MODEL
    Options: "llama-3.1-8b-instant", "mixtral-8x7b-32768", etc.

ASYNC METHOD: decide_action()
─────────────────────────────
async def decide_action(context: Context) -> Action

Decides next action based on context.

Parameters:
  context (Context): Current context with:
    - goal (str): Task goal
    - current_observation (Observation): Current page state
    - history (list[MemoryEntry]): Action history
    - step_count (int): Current step
    - max_steps (int): Maximum steps

Returns: Action object to execute

Raises:
  RuntimeError: If LLM API fails (returns DONE action as fallback)
  ValueError: If response cannot be parsed

Usage Example:
──────────────
from core import AgentReasoner
from core.memory_store import MemoryStore

async def reason():
    reasoner = AgentReasoner()
    memory = MemoryStore("Find AI articles", 20)
    
    # ... perform observations and actions ...
    
    context = memory.get_context(observation)
    action = await reasoner.decide_action(context)
    
    print(f"Decided action: {action.action_type.value}")
    print(f"Reasoning: {action.reasoning}")


CLASS: MockReasoner
───────────────────

Mock reasoner for testing (no API calls).

CONSTRUCTOR
───────────
MockReasoner()

ASYNC METHOD: decide_action()
─────────────────────────────
async def decide_action(context: Context) -> Action

Returns predefined action sequence for testing.

Returns: Action (predetermined sequence)

Usage Example:
──────────────
from core.agent_reasoner import MockReasoner

async def test_without_api():
    reasoner = MockReasoner()
    
    # Get actions without making API calls
    action1 = await reasoner.decide_action(context)  # GOTO
    action2 = await reasoner.decide_action(context)  # TYPE
    action3 = await reasoner.decide_action(context)  # DONE


# ==============================================================================
# 5. MemoryStore
# ==============================================================================

from core.memory_store import MemoryStore, Context, MemoryEntry

CLASS: MemoryStore
──────────────────

Maintains action history and task context.

CONSTRUCTOR
───────────
MemoryStore(goal: str, max_steps: int)

Parameters:
  goal (str): Task goal
  max_steps (int): Maximum steps allowed

PROPERTIES

goal (str, read-only)
  Current task goal.

step_count (int, read-only)
  Number of steps executed so far.

max_steps (int, read-only)
  Maximum steps allowed.

METHODS

add_entry(
    action: Action,
    result: ActionResult,
    observation: Observation
) → None

Records action execution and result.

Parameters:
  action (Action): Action that was executed
  result (ActionResult): Result of execution
  observation (Observation): Page state after action

get_context(
    current_observation: Observation,
    history_limit: int = 10
) → Context

Gets context for LLM reasoning.

Parameters:
  current_observation (Observation): Current page state
  history_limit (int): Max history entries to include
  
Returns: Context object with formatted information for LLM

get_summary() → dict

Gets task execution summary.

Returns: Dictionary with:
  - goal (str)
  - status (str): "completed", "failed", "incomplete"
  - total_steps (int)
  - max_steps (int)
  - successful_actions (int)
  - failed_actions (int)
  - action_sequence (list)

is_at_limit() → bool

Checks if step limit reached.

Returns: True if step_count >= max_steps

clear() → None

Clear all memory entries and reset counters.

Usage Example:
──────────────
from core.memory_store import MemoryStore

memory = MemoryStore("Find articles", 20)

# Record actions
memory.add_entry(action1, result1, observation1)
memory.add_entry(action2, result2, observation2)

# Get context for LLM
context = memory.get_context(current_observation)

# Get summary
summary = memory.get_summary()
print(f"Status: {summary['status']}")
print(f"Steps: {summary['total_steps']}/20")

# Check limits
if memory.is_at_limit():
    print("Step limit reached")


# ==============================================================================
# 6. Action Schema
# ==============================================================================

from schemas.actions import Action, ActionType, ActionResult

ENUM: ActionType
─────────────────

Valid action types:

ActionType.GOTO       - Navigate to URL
ActionType.CLICK      - Click element
ActionType.TYPE       - Type text
ActionType.SCROLL     - Scroll page
ActionType.BACK       - Go back
ActionType.NEW_TAB    - Open new tab
ActionType.CLOSE_TAB  - Close tab
ActionType.DONE       - Complete task


CLASS: Action
─────────────

Represents a single browser action.

CONSTRUCTOR
───────────
Action(
    action_type: ActionType,
    selector: str | None = None,
    value: str | None = None,
    direction: str | None = None,
    reasoning: str = ""
)

Parameters:
  action_type (ActionType): Type of action (required)
  selector (str | None): Element target (for click/type)
  value (str | None): Value (for type) or URL (for goto)
  direction (str | None): Scroll direction ("up"/"down")
  reasoning (str): LLM's reasoning (optional)

VALIDATION

Actions are validated on creation:

GOTO
  - Requires: value (URL)
  - Validates: Proper URL format
  - Auto-fixes: Adds https:// if missing

CLICK
  - Requires: selector
  - Validates: Non-empty selector

TYPE
  - Requires: selector, value
  - Validates: Both non-empty

SCROLL
  - Requires: direction
  - Validates: direction in ("up", "down")

Raises: ValueError if validation fails

METHODS

to_dict() → dict
  Converts action to dictionary.
  
  Returns:
  {
      "action_type": str,
      "selector": str | None,
      "value": str | None,
      "direction": str | None,
      "reasoning": str,
  }

from_dict(data: dict) → Action (class method)
  Creates Action from dictionary.
  
  Parameters:
    data (dict): Dictionary with action data
  
  Returns: Validated Action object
  Raises: ValueError if invalid

Usage Examples:
───────────────

# GOTO action
action = Action(
    action_type=ActionType.GOTO,
    value="https://google.com",
    reasoning="Navigate to Google"
)

# CLICK action
action = Action(
    action_type=ActionType.CLICK,
    selector="Search",
    reasoning="Click search button"
)

# TYPE action
action = Action(
    action_type=ActionType.TYPE,
    selector="search box",
    value="Python",
    reasoning="Enter search query"
)

# SCROLL action
action = Action(
    action_type=ActionType.SCROLL,
    direction="down",
    reasoning="Scroll for more results"
)

# Serialization
data = action.to_dict()
action2 = Action.from_dict(data)


CLASS: ActionResult
───────────────────

Result of action execution.

ATTRIBUTES

success (bool): Action succeeded
message (str): Result description
data (dict): Additional result data

METHODS

to_dict() → dict
  Returns: Dictionary representation of result

Usage Example:
──────────────
from schemas import ActionResult

result = ActionResult(
    success=True,
    message="Clicked search button successfully",
    data={"url": "https://google.com/search?q=test"}
)

print(f"Success: {result.success}")
print(f"Message: {result.message}")


# ==============================================================================
# 7. Config
# ==============================================================================

from config import Config

CLASS: Config
─────────────

Configuration management from environment.

CLASS ATTRIBUTES (All Read-Only)

GROQ_API_KEY (str)
  Groq API key for LLM access.
  From: GROQ_API_KEY environment variable
  Required: Yes (unless using --mock)

LLM_MODEL (str)
  Model to use for reasoning.
  From: LLM_MODEL environment variable
  Default: "llama-3.1-8b-instant"

LLM_TEMPERATURE (float)
  Model creativity/randomness (0.0-2.0).
  From: LLM_TEMPERATURE environment variable
  Default: 0.1
  Lower = more deterministic
  Higher = more creative

LLM_MAX_TOKENS (int)
  Max response length.
  From: LLM_MAX_TOKENS environment variable
  Default: 1024

HEADLESS (bool)
  Browser display mode.
  From: HEADLESS environment variable
  Default: true
  True = hidden browser
  False = visible browser

BROWSER_TIMEOUT (int)
  Action timeout in milliseconds.
  From: BROWSER_TIMEOUT environment variable
  Default: 30000 (30 seconds)

MAX_STEPS (int)
  Default maximum steps per task.
  From: MAX_STEPS environment variable
  Default: 20

OBSERVATION_MAX_ELEMENTS (int)
  Maximum elements to extract per page.
  From: OBSERVATION_MAX_ELEMENTS environment variable
  Default: 50

CLASS METHODS

validate() → None (class method)
  Validates required configuration.
  
  Raises: ValueError if GROQ_API_KEY not set
  
  Usage:
    try:
        Config.validate()
    except ValueError as e:
        print(f"Config error: {e}")

ENVIRONMENT FILE EXAMPLE (.env)

# Groq LLM Settings
GROQ_API_KEY=gsk_xxxxxxxxxxx
LLM_MODEL=llama-3.1-8b-instant
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=1024

# Browser Settings
HEADLESS=true
BROWSER_TIMEOUT=30000

# Agent Settings
MAX_STEPS=20
OBSERVATION_MAX_ELEMENTS=50


# ==============================================================================
# COMPLETE WORKFLOW EXAMPLE
# ==============================================================================

import asyncio
from main import WebNavigatorAgent
from core import BrowserController, ObservationExtractor
from schemas import Action, ActionType

async def complete_workflow():
    # Option 1: Using WebNavigatorAgent (High-level)
    agent = WebNavigatorAgent(
        goal="Find Python articles on GitHub",
        max_steps=15,
        headless=False
    )
    result = await agent.run()
    print(f"Task result: {result['status']}")
    
    # Option 2: Manual control (Low-level)
    async with BrowserController(headless=False) as browser:
        extractor = ObservationExtractor()
        
        # Navigate
        action = Action(
            action_type=ActionType.GOTO,
            value="https://github.com",
            reasoning="Go to GitHub"
        )
        result = await browser.execute_action(action)
        print(f"Navigated: {result.success}")
        
        # Observe
        page = await browser.get_current_page()
        observation = await extractor.extract(page)
        print(f"Found {len(observation.elements)} elements")
        
        # Search
        action = Action(
            action_type=ActionType.CLICK,
            selector="Search",
            reasoning="Click search"
        )
        result = await browser.execute_action(action)

asyncio.run(complete_workflow())


# ==============================================================================
# END OF API REFERENCE
# ==============================================================================
