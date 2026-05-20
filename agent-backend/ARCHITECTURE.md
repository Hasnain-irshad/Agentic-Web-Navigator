"""
ARCHITECTURE DOCUMENTATION
Agentic AI Web Navigator

This document describes the system architecture and design decisions.
"""

# ==============================================================================
# 1. SYSTEM OVERVIEW
# ==============================================================================

The Agentic Web Navigator is a multi-component system that autonomously navigates
websites to complete user-specified tasks. The system uses an observe-reason-execute
loop powered by an LLM (Groq/Llama).

Key Design Principles:
  - Separation of Concerns: Each component has a single responsibility
  - No Raw HTML Parsing: Uses only Playwright locators (observable elements)
  - Deterministic Actions: Strict action schema with validation
  - LLM-Driven Intelligence: Reasoning happens in the LLM, not hardcoded logic
  - Explicit Error Handling: All failures are logged and reported
  - Modular Architecture: Components are independently testable

# ==============================================================================
# 2. COMPONENT ARCHITECTURE
# ==============================================================================

┌─────────────────────────────────────────────────────────────────────────────┐
│                         WebNavigatorAgent (Orchestrator)                      │
│                                                                               │
│  Responsibilities:                                                           │
│  - Initialize all components                                                 │
│  - Coordinate the observe → reason → execute → store loop                    │
│  - Handle task lifecycle and termination                                     │
│  - Generate final summary report                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                  ┌──────────────────┼──────────────────┬───────────────────┐
                  │                  │                  │                   │
        ┌─────────▼──────────┐ ┌────▼──────────┐ ┌────▼──────────┐ ┌──────▼─────────┐
        │ BrowserController   │ │ObservationExt │ │ AgentReasoner │ │  MemoryStore    │
        │                     │ │                │ │               │ │                 │
        │ Responsibilities:   │ │Responsibilities│ │Responsibilities│ │Responsibilities│
        │ - Launch browser    │ │ - Extract page │ │ - LLM API call │ │ - Store history │
        │ - Execute actions   │ │   elements     │ │ - Parse actions │ │ - Provide      │
        │ - Tab management    │ │ - Generate     │ │ - Retry invalid │ │   context      │
        │ - Page state        │ │   descriptions │ │   responses     │ │ - Generate     │
        │                     │ │                │ │                 │ │   summaries    │
        └─────────────────────┘ └────────────────┘ └─────────────────┘ └─────────────────┘
                  │                  │                  │                   │
        ┌─────────▼──────────┐ ┌────▼──────────┐ ┌────▼──────────┐ ┌──────▼─────────┐
        │ Playwright Page     │ │ Locator API    │ │Groq HTTP API  │ │ In-Memory Deque │
        │ Objects            │ │ (No HTML)      │ │ (+ retry logic)│ │ (sliding window)│
        └─────────────────────┘ └────────────────┘ └─────────────────┘ └─────────────────┘

# ==============================================================================
# 3. DATA FLOW
# ==============================================================================

Step-by-step execution flow:

1. INITIALIZATION
   ├─ Create WebNavigatorAgent with goal
   ├─ Initialize MemoryStore with goal and max_steps
   ├─ Launch BrowserController (start Playwright)
   ├─ Create ObservationExtractor
   └─ Create AgentReasoner (connect to Groq API)

2. MAIN LOOP (while step_count < max_steps)
   
   a) OBSERVE
      └─ ObservationExtractor.extract(current_page)
         ├─ Extract visible buttons, links, inputs, headings
         ├─ Generate element selectors (CSS, text, role-based)
         ├─ Create formatted page description
         └─ Return Observation object
   
   b) BUILD CONTEXT
      └─ MemoryStore.get_context(current_observation)
         ├─ Get task goal
         ├─ Get recent action history (sliding window)
         ├─ Format for LLM prompt
         └─ Return Context object
   
   c) REASON
      └─ AgentReasoner.decide_action(context)
         ├─ Build prompt from system + context
         ├─ Call Groq API with timeout
         ├─ Parse JSON response into Action
         ├─ Validate action schema
         ├─ Retry on JSON parse errors (max 3 attempts)
         └─ Return Action object
   
   d) EXECUTE
      └─ BrowserController.execute_action(action)
         ├─ Route to action handler (click, type, scroll, etc)
         ├─ Wait for page state changes
         ├─ Catch exceptions as failures
         ├─ Return ActionResult object
         └─ Return to main loop
   
   e) STORE
      └─ MemoryStore.add_entry(action, result, new_observation)
         ├─ Increment step counter
         ├─ Create MemoryEntry
         ├─ Store in history
         └─ Update in-memory sliding window
   
   f) CHECK TERMINATION
      ├─ If action_type == "done"
      │  └─ Break loop (success)
      ├─ If step_count >= max_steps
      │  └─ Break loop (limit reached)
      └─ Else: continue to next iteration

3. SUMMARIZATION
   ├─ Generate MemoryStore summary
   ├─ Count successful vs failed actions
   ├─ Determine final status (completed/failed/incomplete)
   └─ Return summary dict

# ==============================================================================
# 4. ACTION EXECUTION FLOW
# ==============================================================================

Each action goes through validation and execution:

Input: Action object
  │
  ├─ Route to handler based on action_type
  │
  ├─── GOTO ────────────┐
  │                    ├─► Validate URL (ensure https://)
  │                    ├─► page.goto(url, wait_until="domcontentloaded")
  │                    └─► Return success/failure
  │
  ├─── CLICK ───────────┐
  │                    ├─► Find element using multiple strategies:
  │                    │   1. CSS selector
  │                    │   2. text-based locator
  │                    │   3. Placeholder locator
  │                    │   4. Label locator
  │                    │   5. Role-based locator
  │                    ├─► element.click()
  │                    ├─► Wait for page changes
  │                    └─► Return success/failure
  │
  ├─── TYPE ────────────┐
  │                    ├─► Find input element (same strategies)
  │                    ├─► element.fill(value) (clears + types)
  │                    └─► Return success/failure
  │
  ├─── SCROLL ──────────┐
  │                    ├─► Validate direction (up/down)
  │                    ├─► page.evaluate(window.scrollBy)
  │                    └─► Return success/failure
  │
  ├─── BACK ────────────┐
  │                    ├─► page.go_back(wait_until="domcontentloaded")
  │                    └─► Return success/failure
  │
  ├─── NEW_TAB ─────────┐
  │                    ├─► context.new_page()
  │                    ├─► Add to pages list
  │                    ├─► Set as current page
  │                    └─► Return success/failure
  │
  ├─── CLOSE_TAB ───────┐
  │                    ├─► Check: not last page
  │                    ├─► page.close()
  │                    ├─► Remove from pages list
  │                    ├─► Adjust current page index
  │                    └─► Return success/failure
  │
  └─── DONE ────────────┐
                       └─► Return success (terminates loop)

# ==============================================================================
# 5. ELEMENT EXTRACTION STRATEGY
# ==============================================================================

The system extracts different element types and generates selectors:

Element Type         Extraction Method                Selector Strategy
────────────────────────────────────────────────────────────────────────
Buttons              <button> elements, <input        Text-based: "button:has-text(...)"
                     type=submit/button>              CSS: "button[value='...']"

Links                <a href="..."> elements          Text-based: "a:has-text(...)"
                                                      With href in attributes

Inputs               <input>, <textarea>              ID-based: "#id"
                                                      Name-based: "[name='...']"
                                                      Placeholder: "[placeholder='...']"

Headings             <h1>, <h2>, <h3>                 Text-based: "h1:has-text(...)"
                                                      For context

Key Design Decisions:
  1. NO innerHTML/textContent extraction - Uses Playwright locators only
  2. Multiple selector strategies - Increases success rate finding elements
  3. Visibility check - Only returns visible elements
  4. Text truncation - Long texts cut to 100-150 chars for readability
  5. Max element limit - Default 50 to avoid overwhelming LLM

# ==============================================================================
# 6. LLM PROMPT STRUCTURE
# ==============================================================================

The prompt sent to Groq LLM is structured as:

┌─────────────────────────────────────────┐
│ SYSTEM PROMPT (Fixed Instruction)       │
│                                          │
│ - Action definitions (GOTO, CLICK, etc) │
│ - JSON format requirements               │
│ - Rules and constraints                 │
│ - Output format specification           │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ USER PROMPT (Dynamic Context)           │
│                                          │
│ TASK GOAL:                              │
│   {user's goal}                         │
│                                          │
│ Progress: Step N/Max                    │
│                                          │
│ ACTION HISTORY:                         │
│   [Step 1] ✓ GOTO: Navigated to ...   │
│   [Step 2] ✗ CLICK: Element not found │
│   ...                                   │
│                                          │
│ CURRENT PAGE STATE:                     │
│   URL: {current_url}                   │
│   Title: {page_title}                  │
│                                          │
│   Interactive Elements:                 │
│   [1] BUTTON: "Search"                 │
│   [2] INPUT: "Search box" (placeholder) │
│   [3] LINK: "Documentation" -> /docs   │
│   ...                                   │
│                                          │
│   Page Content Summary:                 │
│   {truncated visible text}              │
│                                          │
│ ⚠️  WARNING (if near step limit):      │
│   Only N steps remaining!              │
└─────────────────────────────────────────┘

LLM Response Expected:
  {
    "action_type": "click",
    "selector": "Search",
    "reasoning": "The user wants to search. I'll click the search button."
  }

# ==============================================================================
# 7. ERROR HANDLING STRATEGY
# ==============================================================================

The system handles errors at multiple levels:

Level 1: ACTION EXECUTION
  │
  ├─ Try/catch around each browser action
  │ └─ Log error, return ActionResult(success=False)
  │
  └─ Non-fatal: Loop continues, LLM sees failure and adjusts

Level 2: LLM REASONING
  │
  ├─ JSON parse errors
  │ └─ Retry mechanism (max 3 attempts) with error context
  │
  ├─ Invalid action schema
  │ └─ Caught by Action.from_dict() validation
  │
  └─ API failures
     └─ Caught, logged, return safe fallback (DONE action)

Level 3: COMPONENT LIFECYCLE
  │
  ├─ Browser startup failures
  │ └─ Caught in __aenter__, logged, re-raised
  │
  ├─ Page navigation timeouts
  │ └─ Caught in execute_action, returned as ActionResult
  │
  └─ Browser cleanup failures
     └─ Caught in __aexit__, logged (non-fatal)

Level 4: ORCHESTRATION
  │
  ├─ Critical errors (browser crash)
  │ └─ Break loop, return error in summary
  │
  └─ Non-critical errors (element not found)
     └─ Log, continue loop

# ==============================================================================
# 8. STATE MANAGEMENT
# ==============================================================================

Key State Objects:

Action (Schema)
  ├─ action_type: ActionType enum
  ├─ selector: str (element target)
  ├─ value: str (input value or URL)
  ├─ direction: str (scroll direction)
  └─ reasoning: str (why this action)

ActionResult
  ├─ success: bool
  ├─ message: str
  └─ data: dict (additional info)

Observation
  ├─ url: str (current page URL)
  ├─ title: str (page title)
  ├─ elements: list[PageElement] (interactive elements)
  ├─ page_text: str (visible text summary)
  └─ error: str (extraction errors if any)

PageElement
  ├─ tag: str (HTML tag)
  ├─ text: str (visible text)
  ├─ selector: str (Playwright selector)
  ├─ element_type: str (button, link, input, heading)
  └─ attributes: dict (href, placeholder, etc)

MemoryEntry
  ├─ step: int (step number)
  ├─ action: Action
  ├─ result: ActionResult
  ├─ observation_summary: str (URL + title)
  └─ timestamp: datetime

Context (for LLM prompt)
  ├─ goal: str
  ├─ current_observation: Observation
  ├─ history: list[MemoryEntry] (sliding window)
  ├─ step_count: int
  └─ max_steps: int

# ==============================================================================
# 9. CONCURRENCY MODEL
# ==============================================================================

The system uses Python's async/await for concurrency:

  - WebNavigatorAgent.run() is async
  - All component methods are async
  - Uses asyncio for task orchestration
  - Playwright is async-native
  - Groq API calls are sync (but called from async context)

Benefits:
  - Allows browser waits without blocking
  - Can handle multiple steps efficiently
  - Scalable for future multi-agent scenarios

Limitations:
  - Single agent per run (sequential tasks)
  - API calls are blocking (LLM reasoning)
  - Future: Could implement task queue system

# ==============================================================================
# 10. CONFIGURATION & EXTENSIBILITY
# ==============================================================================

Config Class (config.py)
  ├─ GROQ_API_KEY: LLM API authentication
  ├─ LLM_MODEL: Which Llama model to use
  ├─ LLM_TEMPERATURE: Creativity (0=deterministic)
  ├─ LLM_MAX_TOKENS: Response length limit
  ├─ HEADLESS: Browser mode
  ├─ BROWSER_TIMEOUT: Action wait time
  ├─ MAX_STEPS: Default step limit
  └─ OBSERVATION_MAX_ELEMENTS: Element extraction limit

Extension Points:

1. New Actions
   - Add to ActionType enum
   - Implement handler in BrowserController
   - Update system prompt in AgentReasoner
   - Add validation in Action._validate()

2. New Element Types
   - Add extraction method in ObservationExtractor
   - Call from extract() method
   - Ensure selector strategy works

3. Alternative LLM
   - Replace AgentReasoner with new LLM client
   - Keep Action/ActionResult interface
   - Maintain system prompt format

4. Custom Element Selection
   - Override _find_element() in BrowserController
   - Implement different selector strategies
   - Can add ML-based element identification

# ==============================================================================
# 11. PERFORMANCE CHARACTERISTICS
# ==============================================================================

Metrics & Bottlenecks:

1. Element Extraction
   ├─ Buttons: ~5-15 (limited extraction)
   ├─ Links: ~10-20
   ├─ Inputs: ~5-10
   ├─ Total: ~50 (configurable max)
   └─ Impact: ~100-500ms per page

2. LLM API Call
   ├─ Network latency: ~500-2000ms
   ├─ Model inference: ~1000-3000ms
   ├─ Total: ~2-5 seconds per action
   └─ Impact: DOMINANT bottleneck

3. Browser Action
   ├─ Click/Type: ~100-500ms
   ├─ Navigation: ~1000-5000ms (depends on page load)
   ├─ Scroll: ~50-200ms
   └─ Impact: ~5-10 seconds per cycle

Typical Cycle Time
  └─ Observe (500ms) + Reason (3s) + Execute (2s) + Store (50ms) ≈ 5-6 seconds

Optimization Opportunities
  1. Batch element extraction (parallel async locators)
  2. Cache page observations (reduce re-extraction)
  3. Parallel action execution (multiple browser instances)
  4. Smaller LLM model for faster inference
  5. Prompt optimization (shorter context)

# ==============================================================================
# 12. TESTING & VALIDATION
# ==============================================================================

Testing Strategy:

Unit Tests (per component)
  - Action validation (Action._validate)
  - Config loading (Config class)
  - Logger creation (get_logger)
  - Memory store operations

Integration Tests
  - Browser + ObservationExtractor
  - Agent + Mock Reasoner
  - Full loop with mock

System Tests
  - End-to-end with real LLM
  - Multiple task scenarios
  - Error recovery

Mock Reasoner
  - Predefined action sequence
  - No API calls required
  - Fast testing without credentials

Validation Tools
  - quickstart.py: Environment validation
  - main.py --mock: Mock agent execution
  - Config.validate(): API key verification

# ==============================================================================
# 13. PRODUCTION DEPLOYMENT
# ==============================================================================

Considerations for production:

1. Resource Management
   ├─ Browser pooling (reuse instances)
   ├─ Memory limits for long-running agents
   └─ Rate limiting for API calls

2. Error Recovery
   ├─ Automatic restart on browser crash
   ├─ Exponential backoff for API failures
   └─ Task queue for retry

3. Monitoring & Logging
   ├─ Centralized logging (file + stdout)
   ├─ Metrics collection (step time, success rate)
   └─ Error alerting

4. Scale Considerations
   ├─ Multi-agent orchestration
   ├─ Task distribution (queue-based)
   └─ Result aggregation

5. Security
   ├─ API key management (secrets vault)
   ├─ URL validation (prevent malicious sites)
   ├─ Timeout enforcement
   └─ Sandboxed browser execution

# ==============================================================================

End of Architecture Documentation
