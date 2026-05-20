"""
LLM Prompt Builder: Generates structured prompts from WorldModel.

The LLM NEVER sees raw DOM. It only sees the compact WorldModel output
plus strict behavioral instructions.
"""

from typing import Optional, List

try:
    from core.world_model import WorldModel, PageState
    from utils import get_logger
except ImportError:
    from .world_model import WorldModel, PageState
    from ..utils import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# System Prompt — strict behavioral constraints for the LLM
# ═══════════════════════════════════════════════════════════════════════════

ACTION_SYSTEM_PROMPT = """You are a web automation agent operating in a real browser environment. You MUST follow strict execution control rules to prevent infinite loops, repeated actions, and redundant clicks.

## CORE RULE: STATE-AWARE EXECUTION
You must maintain an internal task state and update it after every step.
State includes:
- current_page_type: (HOME, SEARCH_RESULTS, PRODUCT_PAGE, LOGIN_PAGE, UNKNOWN)
- goal: user objective
- visited_elements: list of element identifiers already interacted with
- last_action: previous action executed
- repetition_count: number of repeated actions on same target

## STOP CONDITION (VERY IMPORTANT)
You MUST STOP execution (set stop_decision to "YES") when ANY of the following is true:
- The goal is completed (e.g., product page opened, login successful, item added to cart)
- No new meaningful action is available
- The same action is attempted more than 2 times consecutively
- The page state does not change after an action

## ANTI-LOOP RULES
- NEVER click the same element more than once unless page state has changed.
- NEVER repeat the same action sequence (detect loops based on STEPS COMPLETED).
- If the same target appears again, choose the next best alternative.
- If no progress is observed after 2 steps, change strategy (scroll, open item, refine search, or mark done).

## PAGE TRANSITION RULES
You MUST update page state after navigation:
- SEARCH_RESULTS → PRODUCT_PAGE when a product is clicked
- HOME → SEARCH_RESULTS after search submit
- Any page → UNKNOWN if DOM is unstable or empty

## ACTION DEPENDENCY RULES
For ecommerce tasks:
IF goal contains "add to cart":
- Step 1: search
- Step 2: open product page (MANDATORY)
- Step 3: ONLY THEN attempt add_to_cart
If not on product page, DO NOT search for add_to_cart button.

IF goal contains "login":
- Step 1: open login page
- Step 2: fill form
- Step 3: submit
- STOP after successful login

## REPEAT DETECTION RULE
Track last 3 actions. If:
- same action AND same target AND same page state -> BLOCK action and replan immediately.

## ACTION FORMAT (CRITICAL)
You must output EXACTLY ONE action in JSON format. Do not write text outside the JSON.
{
  "updated_state": "<HOME|SEARCH_RESULTS|PRODUCT_PAGE|LOGIN_PAGE|UNKNOWN>",
  "stop_decision": "<YES|NO>",
  "action": "goto" | "type" | "click" | "press_key" | "scroll" | "wait" | "done",
  "target": "<what to interact with>",
  "value": "<text to type / URL to goto>",
  "key": "<key name, if press_key>",
  "reasoning": "<brief explanation of your decision>"
}

## TARGET VALUES
- "goto" → requires "value" with the exact URL
- "search_input" → the search box
- "item_N" → click the Nth item (e.g. "item_1")
- "action:Label" → click action button by its label
- "filter:Label" → click filter by its label
- "search_button" → click search submit
"""


def build_action_prompt(
    world_model: WorldModel,
    goal: str,
    step_history: Optional[List[str]] = None,
    chat_history: Optional[List[dict]] = None
) -> str:
    """
    Legacy prompt builder. Kept for SessionAgent (Playwright-driven path).
    New WSAgent uses build_action_prompt_v2 with task + session.
    """
    sections = []

    # Session Memory
    if chat_history and len(chat_history) > 1:
        history_text = "\n".join(f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history[:-1])
        sections.append(f"## SESSION CONTEXT (Previous Commands)\n{history_text}")

    # Goal
    sections.append(f"## CURRENT GOAL\n{goal}")
    if step_history:
        history_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(step_history[-5:]))
        sections.append(f"## STEPS COMPLETED\n{history_text}")

    # World model
    sections.append(f"## CURRENT PAGE STATE\n{world_model.to_prompt()}")

    # Explicit available actions based on page state
    sections.append(_build_action_hints(world_model))

    # Final instruction
    sections.append("## YOUR TASK\nAnalyze the page state and goal. Decide the SINGLE next action. Return ONLY a JSON object.")

    return "\n\n".join(sections)


def build_action_prompt_v2(
    world_model: WorldModel,
    task: object,
    session: object,
    recent_steps: Optional[List[str]] = None,
) -> str:
    """
    New prompt builder. Gives the LLM four distinct sections:

      1. CONVERSATION        - prior user commands in this session
      2. CURRENT TASK        - goal + active subgoal (WHAT to do next)
      3. SESSION FACTS       - cart, login, last search, currently viewing
      4. CURRENT PAGE STATE  - world model (what's actually visible)

    The LLM's job is narrow: pick the next primitive action that advances
    the ACTIVE subgoal. Task completion is decided by TaskPlanner, not LLM.
    """
    sections: list[str] = []

    # 1. Conversation context (prior commands only — exclude current)
    convo = getattr(session, "conversation", None) or []
    prior = [c for c in convo if c.get("task_id") != getattr(task, "task_id", None)]
    if prior:
        lines = []
        for msg in prior[-6:]:
            role = str(msg.get("role", "user")).capitalize()
            content = str(msg.get("content", ""))[:200]
            lines.append(f"{role}: {content}")
        sections.append("## CONVERSATION HISTORY\n" + "\n".join(lines))

    # 2. Current task + active subgoal
    task_lines = [f"Goal: {getattr(task, 'goal', '')}"]
    task_lines.append(f"Intent: {getattr(task, 'intent', 'generic')}")
    task_lines.append(f"Step: {getattr(task, 'step_count', 0)}/{getattr(task, 'max_steps', 25)}")
    subgoals = getattr(task, "subgoals", []) or []
    if subgoals:
        task_lines.append("Subgoal progress:")
        for i, sg in enumerate(subgoals):
            marker = "→" if i == getattr(task, "current_subgoal_idx", 0) else " "
            status = getattr(sg, "status", "?")
            desc = getattr(sg, "description", "") or getattr(getattr(sg, "kind", None), "value", "?")
            task_lines.append(f"  {marker} [{status}] {desc}")
    current = getattr(task, "current_subgoal", None)
    if current is not None:
        kind_val = getattr(getattr(current, "kind", None), "value", "?")
        task_lines.append(f"\nACTIVE SUBGOAL: {getattr(current, 'description', '') or kind_val}")
        task_lines.append(f"Kind: {kind_val}   Params: {getattr(current, 'params', {})}")
    sections.append("## CURRENT TASK\n" + "\n".join(task_lines))

    # 3. Session facts — durable state learned across steps
    if hasattr(session, "facts_summary"):
        sections.append(f"## SESSION FACTS\n{session.facts_summary()}")

    # 3.5 Browser shell snapshot + priority rule
    shell = getattr(session, "browser_shell", {}) or {}
    if shell:
        sections.append(
            "## BROWSER SHELL\n"
            f"- search_bar_available: {shell.get('search_bar_available', False)}\n"
            f"- active_input: {shell.get('active_input', 'none')}\n"
            f"- current_url: {shell.get('current_url', '')}\n"
            "\n"
            "PRIORITY RULE (IMPORTANT):\n"
            "  1. Browser search/address bar  ← preferred for site navigation\n"
            "  2. Page DOM search box         ← only for searching within a site\n"
            "  3. Page DOM buttons / links    ← interactions inside a site\n"
            "If the goal is to REACH a site, emit `browser_search` (the shell\n"
            "handles it like a human typing into the address bar). Do NOT open\n"
            "a new tab. Do NOT invoke an external search engine."
        )

    # 4. Recent action trail (last 5 steps within THIS task)
    if recent_steps:
        trail = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(recent_steps[-5:]))
        sections.append(f"## RECENT STEPS\n{trail}")

    # 5. World model (current page)
    sections.append(f"## CURRENT PAGE STATE\n{world_model.to_prompt()}")

    # 6. Constraints derived from the active subgoal
    sections.append(_build_subgoal_constraints(current, world_model))

    # 7. Available primitive actions
    sections.append(_build_action_hints(world_model))

    # 8. Final instruction
    sections.append(
        "## YOUR TASK\n"
        "Pick the SINGLE next primitive action that advances the ACTIVE SUBGOAL.\n"
        "Rules:\n"
        "- Do NOT emit `done` — the planner decides completion.\n"
        "- Do NOT repeat the last action if the page state didn't change.\n"
        "- If the ACTIVE subgoal's target element is not visible, prefer `scroll` or `goto` over guessing.\n"
        "- Return ONLY a JSON object in the format shown in the system prompt."
    )

    return "\n\n".join(sections)


def _build_subgoal_constraints(current_subgoal: Optional[object], wm: WorldModel) -> str:
    """Turn the active subgoal into concrete DO/DON'T rules for the LLM.
    This is what prevents category drift and irrelevant clicks."""
    lines = ["## SUBGOAL CONSTRAINTS"]
    if current_subgoal is None:
        lines.append("- No active subgoal. If the page looks idle, wait for next command.")
        return "\n".join(lines)

    kind = getattr(getattr(current_subgoal, "kind", None), "value", "")
    params = getattr(current_subgoal, "params", {}) or {}

    if kind == "navigate":
        dom = params.get("domain") or params.get("url") or ""
        url = f"https://{dom}" if dom and not dom.startswith("http") else dom
        lines.append(f"- You MUST navigate to `{dom}` via the ADDRESS BAR.")
        lines.append(f'- Emit: {{"action": "browser_search", "value": "{dom}"}}   (preferred)')
        lines.append(f'- Fallback only if shell is not available: {{"action": "goto", "value": "{url}"}}')
        lines.append("- Do NOT click search, products, or filters until navigation succeeds.")

    elif kind == "browser_bar_search":
        q = params.get("query") or params.get("domain") or ""
        lines.append(f"- Type `{q}` into the BROWSER ADDRESS BAR (shell, not page DOM).")
        lines.append(f'- Emit: {{"action": "browser_search", "value": "{q}"}}')
        lines.append("- Do NOT interact with any page-level input for this subgoal.")
        lines.append("- Do NOT open a new tab; the shell drives the existing one.")

    elif kind == "search":
        q = params.get("query", "")
        lines.append(f"- You MUST search for `{q}`.")
        if wm.search and wm.search.found:
            lines.append(f'- Step 1: type in search box: {{"action": "type", "target": "search_input", "value": "{q}"}}')
            lines.append('- Step 2: press Enter: {"action": "press_key", "key": "Enter"}')
        else:
            lines.append("- Search box not visible. Try scrolling up, or goto the homepage of the target site.")
        lines.append("- Do NOT click products, actions, or filters during this subgoal.")

    elif kind == "open_result":
        ordinal = params.get("ordinal", 1)
        lines.append(f"- You MUST open the #{ordinal} result.")
        lines.append(f'- Emit: {{"action": "click", "target": "item_{ordinal}"}}')
        lines.append("- Do NOT type, do NOT search, do NOT click filters.")
        lines.append("- If the result is off-screen, scroll down once then click.")

    elif kind == "add_to_cart":
        lines.append("- You MUST click an Add-to-Cart / Buy button on the CURRENT product page.")
        if wm.actions:
            labels = ", ".join(a.label for a in wm.actions[:5])
            lines.append(f"- Visible action buttons: {labels}")
            lines.append('- Prefer: {"action": "click", "target": "action:Add to Cart"}')
        else:
            lines.append("- No action buttons visible. Scroll down to reveal cart button.")
        lines.append("- Do NOT navigate away. Do NOT click another product.")

    elif kind == "login":
        lines.append("- You MUST complete the login flow.")
        lines.append("- Find email/username field, fill it, find password field, fill it, submit.")
        lines.append("- If credentials are missing in params, emit {\"action\": \"wait\"} and stop.")

    elif kind == "checkout":
        lines.append("- You MUST reach the checkout page.")
        lines.append("- Click 'Proceed to Checkout' / 'Checkout' button on cart page.")

    else:
        lines.append("- Choose the action most aligned with the user's original goal.")

    return "\n".join(lines)


def _build_action_hints(wm: WorldModel) -> str:
    """Generate explicit hints about what actions are available right now."""
    hints = ["## AVAILABLE ACTIONS RIGHT NOW"]

    if wm.search and wm.search.found:
        hints.append('- Type in search box: {"action": "type", "target": "search_input", "value": "your query"}')

    if wm.products:
        hints.append(f'- Click any of {len(wm.products)} items: {{"action": "click", "target": "item_N"}} where N is 1-{len(wm.products)}')

    if wm.actions:
        for a in wm.actions:
            hints.append(f'- {a.label}: {{"action": "click", "target": "action:{a.label}"}}')

    if wm.filters:
        for f in wm.filters:
            hints.append(f'- {f.label}: {{"action": "click", "target": "filter:{f.label}"}}')

    hints.append('- Navigate to a known URL: {"action": "goto", "value": "https://..."}')
    hints.append('- Type in search box: {"action": "type", "target": "search_input", "value": "..."}')
    hints.append('- Press Enter: {"action": "press_key", "key": "Enter"}')
    hints.append('- Scroll down: {"action": "scroll", "target": "down"}')
    hints.append('- Mark done: {"action": "done"}')

    if not wm.search or not wm.search.found:
        if not wm.products and not wm.actions:
            hints.append('- Wait for page load: {"action": "wait"}')

    return "\n".join(hints)


def get_system_prompt() -> str:
    """Return the system prompt for the action-deciding LLM."""
    return ACTION_SYSTEM_PROMPT
