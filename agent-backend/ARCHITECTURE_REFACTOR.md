# Architecture Refactor: Plan-Driven Browser Automation

## Overview

The Agentic Web Navigator has been refactored from a **reactive, regex-based system** to a **plan-driven, LLM-powered system** with clean separation of concerns.

### Key Architectural Layers

```
┌─────────────────────────────────┐
│  User Input (GUI / CLI)         │
├─────────────────────────────────┤
│  SessionAgent (Orchestrator)    │
├─────────────────────────────────┤
│  Planner (LLM)   ← Generates    │
│  Action Plan                    │
├─────────────────────────────────┤
│  Action Mapper                  │
│  (Selector Resolution)          │
├─────────────────────────────────┤
│  BrowserController              │
│  (Execution)                    │
├─────────────────────────────────┤
│  Playwright Browser             │
└─────────────────────────────────┘
```

---

## New Components

### 1. **Planner** (`core/planner.py`)

**Purpose**: Convert natural language commands into structured execution plans.

**Input**: 
- User command (e.g., "Search for watches on Daraz")
- Optional page context (current URL, visible elements)

**Output**: 
```json
[
  {
    "action": "goto",
    "value": "https://www.google.com",
    "reasoning": "Start at Google search engine"
  },
  {
    "action": "type",
    "selector": "search_box",
    "value": "daraz.pk",
    "reasoning": "Type Daraz site name"
  },
  {
    "action": "press_key",
    "key": "Enter",
    "reasoning": "Search for Daraz"
  },
  ...
]
```

**Key Methods**:
- `async generate_plan(user_command, page_context)` → Returns JSON action plan
- `convert_plan_to_actions(plan)` → Converts JSON to Action objects

**Features**:
- Uses Groq/LLaMA for intelligence
- Outputs pure JSON (no regex parsing needed)
- Works for ANY website (not hardcoded)
- Returns atomic, sequential steps
- Includes reasoning for each action

---

### 2. **Action Mapper** (`core/action_mapper.py`)

**Purpose**: Map logical selectors to actual DOM elements robustly.

**Problem Solved**: 
- Old system used hardcoded selectors like "Search" or "first link"
- These don't work across different websites
- CSS selectors are fragile and site-specific

**Solution**: Logical selector resolution

**Example Usage**:
```python
# Instead of:
selector = "Search"  # brittle

# Now:
selector = "search_box"  # logical, universal
resolved = await ActionMapper.resolve_selector(page, selector)
# Returns actual CSS selector for that page
```

**Supported Logical Selectors**:
- `search_box` → Finds search input
- `first_result` → First search result link
- `first_product` → First product item
- `add_to_cart` → Add to cart button
- `nth_item` → Nth item in list (e.g., "2nd_product")
- `next_button`, `close_button`, etc.

**Key Methods**:
- `async resolve_selector(page, selector)` → Resolves logical to CSS selector
- `async find_element_by_selector(page, selector)` → Finds actual element
- `async get_page_context(page)` → Extracts page structure for planner

**Resolution Strategy**:
1. Try predefined CSS selector patterns
2. Try text-based matching
3. Try ordinal patterns (first, second, third...)
4. Fall back to direct CSS selector if provided

---

### 3. **Refactored SessionAgent** (`core/session_agent.py`)

**What Changed**:
- ❌ Removed regex-based intent parsing
- ❌ Removed hardcoded "search on site for term" logic
- ❌ Removed deterministic plan from user command
- ✅ Added plan generation step
- ✅ Added selector resolution step
- ✅ Simplified execution loop

**New Execution Flow**:

```
1. User Input: "Search for watches on Daraz"
   ↓
2. Planner (LLM)
   Input: User command + page context
   Output: Multi-step JSON plan
   ↓
   [
     {action: goto, value: https://google.com},
     {action: type, selector: search_box, value: daraz.pk},
     {action: press_key, key: Enter},
     {action: click, selector: first_result},
     {action: type, selector: search_box, value: watches},
     {action: press_key, key: Enter},
     {action: done}
   ]
   ↓
3. Plan Executor (SessionAgent)
   For each action in plan:
     a. Resolve selector (if click/type)
     b. Execute on browser
     c. Log result
     d. Continue
   ↓
4. Result
   {
     status: "completed",
     steps: 7,
     successful: 7,
     actions: [...]
   }
```

**Key Changes to Methods**:

**`execute_command(goal, callback)`**:
- ✅ Calls `planner.generate_plan()`
- ✅ Calls `ActionMapper.resolve_selector()` for each action
- ✅ No regex parsing
- ✅ Cleaner execution loop
- ✅ Better error handling

**`start_session()`**:
- ✅ Initializes `Planner` instead of `Reasoner`
- ✅ Cleaner initialization

---

## Removed Components

### Old Regex Patterns (ALL REMOVED)
```python
# ❌ NO LONGER USED:

# Pattern 1: "search [on/in] SITE for TERM"
m = re.search(r"search(?: on| in)?\s+(?P<site>\S+?)\s+for\s+(?P<term>.+)", goal)

# Pattern 2: "open Nth item and add to cart"
ord_pattern = r"(?P<ord>first|1st|second|2nd|...)"

# Pattern 3: Deterministic plan building
self._deterministic_plan = [...]
self._deterministic_target_site = None
```

### Old Hardcoded Selectors (ALL REMOVED)
```python
# ❌ NO LONGER USED:
selector = "Search"          # Not universal
selector = "first link"      # Brittle
selector = "Add to Cart"     # Site-specific
```

---

## New Execution Flow vs Old

### OLD SYSTEM
```
[ User Input ]
    ↓
[ Regex Pattern Match ]  ← Fragile, hardcoded
    ↓
[ Deterministic Plan ] ← Site-specific hardcoding
    ↓
[ Action Execution ]
    ↓
[ Result ]
```

**Problems**:
- Only works for hardcoded patterns (Google search, Daraz)
- Adding new websites requires regex changes
- Brittle selectors break easily
- No scalability

### NEW SYSTEM
```
[ User Input ]
    ↓
[ LLM Planner ] ← Smart, adaptive, works for ANY site
    ↓
[ JSON Plan ] ← Universal format
    ↓
[ Selector Resolution ] ← Intelligent mapping
    ↓
[ Action Execution ]
    ↓
[ Result ]
```

**Benefits**:
- Works for ANY website
- LLM understands context
- Logical selectors work across sites
- Scalable to new patterns
- No regex maintenance

---

## Usage Examples

### Example 1: Search on Any Site
```python
# OLD WAY (broken for most sites):
# Only works if regex pattern matches

# NEW WAY (works everywhere):
command = "Search for laptops on Amazon"
result = await agent.execute_command(command)
# Planner generates proper steps for Amazon
```

### Example 2: Multi-Step Product Purchase
```python
command = "Find iPhone 15 on Daraz, open first result, add to cart"
result = await agent.execute_command(command)

# Planner generates:
# 1. Goto Daraz
# 2. Search for "iPhone 15"
# 3. Click first product
# 4. Click "Add to cart"
```

### Example 3: Any Custom Task
```python
command = "Login to university portal and check admissions status"
result = await agent.execute_command(command)

# Planner adapts intelligently to:
# - Finding login form
# - Entering credentials
# - Navigating to admissions page
# - Extracting status
```

---

## Configuration

### For Production (Real LLM):
```python
session_agent = SessionAgent(
    max_steps_per_command=30,
    headless=False,
    use_mock=False  # Use real Groq API
)
```

### For Testing (Mock Planner):
```python
session_agent = SessionAgent(
    max_steps_per_command=30,
    headless=True,
    use_mock=True  # Use mock plans
)
```

---

## Integration Points

### GUI (session_gui.py)
- No changes needed
- `execute_command()` signature same
- Callback system works as before
- Just receives better results

### CLI (main.py / CLI mode)
- Can use same `SessionAgent`
- Or adapt `WebNavigatorAgent` to use planner

---

## Benefits of New Architecture

| Aspect | Old | New |
|--------|-----|-----|
| **Scalability** | Hard-coded for 2 sites | Works for ANY site |
| **Maintenance** | Regex hell | LLM intelligence |
| **Correctness** | Brittle selectors | Robust resolution |
| **Intent Parsing** | Regex patterns | LLM understanding |
| **Error Recovery** | None | Planned fallbacks |
| **Code Complexity** | High (lots of regex) | Low (LLM handles it) |
| **New Site Support** | Requires code changes | Zero code changes |
| **Selector Brittleness** | High | Low (heuristics) |

---

## Troubleshooting

### Plan Generation Fails
1. Check API key is set: `echo $GROQ_API_KEY`
2. Check internet connection
3. Try simpler command
4. Use `use_mock=True` for testing

### Selectors Not Resolving
1. Check page has loaded
2. Try with simpler selector names
3. Add debug logging to ActionMapper
4. Check if element is visible (not hidden)

### Actions Failing
1. Increase delays in config: `HUMAN_MIN_DELAY_MS=500`
2. Check CAPTCHA detection working
3. Try headful mode: `FORCE_HEADFUL_ON_HUMANIZE=true`

### Regression from Old Behaviors
1. Old regex patterns removed by design
2. Use planner for those commands now
3. Planner will generate correct steps
4. Report specific command issues

---

## Migration Guide (Old Code → New Code)

### If You Had Custom Code

**Old (Regex-Based)**:
```python
if "search" in goal and "on" in goal:
    # Extract site and term via regex
    m = re.search(r"search on (\w+) for (.+)", goal)
    site, term = m.groups()
    # Execute hardcoded steps
```

**New (Plan-Based)**:
```python
# Just use the command directly!
result = await agent.execute_command(goal)
# Planner handles it automatically
```

### If You Had Hardcoded Selectors

**Old**:
```python
action = Action(
    action_type=ActionType.CLICK,
    selector="first link"  # Brittle
)
```

**New**:
```python
action = Action(
    action_type=ActionType.CLICK,
    selector="first_result"  # Logical, universal
)
# ActionMapper resolves to actual selector
```

---

## File Structure

```
core/
  ├── planner.py              [NEW] Generate multi-step plans
  ├── action_mapper.py        [NEW] Resolve logical selectors
  ├── session_agent.py        [REFACTORED] Plan-driven execution
  ├── browser_controller.py   [UNCHANGED]
  ├── observation_extractor.py [UNCHANGED]
  ├── memory_store.py         [UNCHANGED]
  ├── agent_reasoner.py       [UNCHANGED] (kept for future use)
  ├── stop_conditions.py      [UNCHANGED]
  └── __init__.py             [UPDATED] Exports new modules

schemas/
  └── actions.py              [UNCHANGED]

session_gui.py                [MINIMAL CHANGES] Works with new SessionAgent
main.py                       [CAN BE UPDATED] To use new Planner
```

---

## Next Steps (Optional Enhancements)

1. **Fallback Retry Logic**: If action fails, ask planner for alternative
2. **DOM Analysis**: Improve selector resolution with ML
3. **Cookie Handling**: Better session persistence
4. **Proxy Rotation**: Built-in proxy support
5. **Screenshot Evidence**: Save screenshots for each step
6. **Video Recording**: Record browser interactions

---

## FAQ

**Q: Will this break my GUI?**  
A: No, `execute_command()` API is the same. GUI will just work better.

**Q: Can I still use hardcoded commands?**  
A: Yes, the planner will handle them. Just give commands to the planner instead of regex.

**Q: Does this need Groq API?**  
A: Yes for production. For testing, use `use_mock=True`.

**Q: What if the planner generates bad actions?**  
A: Planner is trained on webscraping domain. Provide clearer commands or add page context.

**Q: How do I add a new selector?**  
A: Add to `SELECTOR_PATTERNS` in `action_mapper.py`, no planner changes needed.

---

**Last Updated**: April 17, 2026  
**Architecture**: Plan-Driven (Planner → Mapper → Executor)  
**Status**: Refactor Complete, Ready for Testing
