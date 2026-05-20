"""
CommandInterceptor: rule-based fast path for simple navigational commands.

These commands bypass the LLM entirely — there is nothing for a planner to
reason about, and hitting the LLM adds latency and a risk of misinterpretation
("go back" could otherwise be mistaken for a navigation goal to a site called
"back").

Handled commands:
    - "go back" / "back" / "previous page"      -> browser back
    - "go forward" / "forward"                  -> browser forward
    - "refresh" / "reload"                      -> reload page
    - "scroll up"                               -> scroll up
    - "scroll down" / "scroll"                  -> scroll down
    - "scroll to top"                           -> scroll to top
    - "scroll to bottom"                        -> scroll to bottom

A match returns a single primitive-action dict ready to send to the Electron
frontend. The backend emits the action and immediately marks the task AWAITING
(no further reasoning needed).
"""

from __future__ import annotations

import re
from typing import Optional


# Rules are checked in order; first match wins.
# Each rule is (regex, action_payload_builder).
_RULES: list[tuple[re.Pattern, dict]] = [
    # Back / forward
    (re.compile(r"^\s*(?:please\s+)?(?:go\s+)?back\s*$", re.I),
     {"action": "back", "reasoning": "User requested browser back"}),
    (re.compile(r"^\s*previous\s+page\s*$", re.I),
     {"action": "back", "reasoning": "User requested previous page"}),
    (re.compile(r"^\s*(?:please\s+)?(?:go\s+)?forward\s*$", re.I),
     {"action": "forward", "reasoning": "User requested browser forward"}),

    # Reload
    (re.compile(r"^\s*(?:please\s+)?(?:refresh|reload)(?:\s+(?:the\s+)?page)?\s*$", re.I),
     {"action": "reload", "reasoning": "User requested page reload"}),

    # Scroll variants (order matters: specific before generic)
    (re.compile(r"^\s*scroll\s+to\s+top\s*$", re.I),
     {"action": "scroll", "direction": "top", "reasoning": "User requested scroll to top"}),
    (re.compile(r"^\s*scroll\s+to\s+bottom\s*$", re.I),
     {"action": "scroll", "direction": "bottom", "reasoning": "User requested scroll to bottom"}),
    (re.compile(r"^\s*(?:page\s+)?up\s*$", re.I),
     {"action": "scroll", "direction": "up", "reasoning": "User requested scroll up"}),
    (re.compile(r"^\s*scroll\s+up\s*$", re.I),
     {"action": "scroll", "direction": "up", "reasoning": "User requested scroll up"}),
    (re.compile(r"^\s*(?:page\s+)?down\s*$", re.I),
     {"action": "scroll", "direction": "down", "reasoning": "User requested scroll down"}),
    (re.compile(r"^\s*scroll(?:\s+down)?\s*$", re.I),
     {"action": "scroll", "direction": "down", "reasoning": "User requested scroll"}),

    # Close / stop
    (re.compile(r"^\s*(?:stop|cancel|abort)\s*$", re.I),
     {"action": "idle", "reasoning": "User requested stop", "done": True}),
]


def intercept(command: str) -> Optional[dict]:
    """Return a primitive action dict if the command matches a rule, else None.
    The returned dict has `action` and `reasoning` at minimum."""
    if not command:
        return None
    for regex, payload in _RULES:
        if regex.match(command):
            # Shallow copy so callers can mutate safely
            return dict(payload)
    return None


def is_intercepted(command: str) -> bool:
    return intercept(command) is not None
