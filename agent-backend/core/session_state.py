"""
SessionState / TaskState / Subgoal: the persistent state layer for the WS agent.

Three lifetimes:
  SessionState   - persists for the lifetime of a WebSocket connection
  TaskState      - one per user command (nested inside SessionState)
  WorldModel     - rebuilt every step from DOM (see world_model.py)

SessionState holds durable *facts* (cart, login, viewed products, last search).
TaskState holds *goal progress* (subgoals, step budget, loop-protection).
WorldModel holds *what is on screen right now*.

These must NOT be merged. They have different update cadences and consumers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════════
# Entities tracked across the session
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ViewedProduct:
    """A product seen on a search-results page (or opened as a product page)."""
    rank: int                 # 1-based ordinal from the results page (0 if ad-hoc)
    title: str
    price: str = ""
    url: str = ""
    captured_at_step: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "title": self.title,
            "price": self.price,
            "url": self.url,
            "captured_at_step": self.captured_at_step,
        }


@dataclass
class CartItem:
    title: str
    price: str = ""
    quantity: int = 1
    added_at_step: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "price": self.price,
            "quantity": self.quantity,
            "added_at_step": self.added_at_step,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Task lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TaskStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING = "awaiting_user"      # task done, waiting for next command
    BLOCKED = "blocked"             # captcha / login wall / verification
    SUPERSEDED = "superseded"       # user issued a new command mid-task


class SubgoalKind(Enum):
    """Machine-verifiable subgoal types. The planner checks each against
    SessionState + WorldModel deterministically — the LLM is NOT trusted to
    emit `done`."""
    NAVIGATE = "navigate"                      # params: {"domain": "daraz.pk"} OR {"url": "..."}
    BROWSER_BAR_SEARCH = "browser_bar_search"  # params: {"query": "youtube"} — type in shell address bar
    SEARCH = "search"                          # params: {"query": "laptops"} — page-level search input
    OPEN_RESULT = "open_result"                # params: {"ordinal": 2}  (1-based)
    ADD_TO_CART = "add_to_cart"                # params: {"pre_cart_count": 0}
    LOGIN = "login"                            # params: {}
    CHECKOUT = "checkout"                      # params: {}
    CUSTOM = "custom"                          # free-form; never auto-verifies


@dataclass
class Subgoal:
    kind: SubgoalKind
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    status: str = "pending"          # pending | active | done | skipped | failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "params": self.params,
            "description": self.description,
            "status": self.status,
        }


@dataclass
class TaskState:
    task_id: str
    goal: str                                   # raw user command
    intent: str                                 # "search" | "open_product" | "add_to_cart" | "login" | "navigate" | "generic"
    subgoals: list[Subgoal] = field(default_factory=list)
    current_subgoal_idx: int = 0
    step_count: int = 0
    max_steps: int = 25
    status: TaskStatus = TaskStatus.ACTIVE
    # sliding window of recent action fingerprints for RepetitionDetector
    action_fingerprints: list[str] = field(default_factory=list)
    # resolved entity references (e.g. {"ordinal": 2}) extracted from NL command
    referenced_entities: dict[str, Any] = field(default_factory=dict)

    @property
    def current_subgoal(self) -> Optional[Subgoal]:
        if 0 <= self.current_subgoal_idx < len(self.subgoals):
            return self.subgoals[self.current_subgoal_idx]
        return None

    @property
    def is_complete(self) -> bool:
        return all(sg.status in ("done", "skipped") for sg in self.subgoals)

    def record_action(self, fingerprint: str, window: int = 6) -> None:
        self.action_fingerprints.append(fingerprint)
        if len(self.action_fingerprints) > window:
            self.action_fingerprints = self.action_fingerprints[-window:]

    def is_looping(self) -> bool:
        """Detect A-B-A-B or A-A-A patterns in the last 6 actions."""
        fp = self.action_fingerprints
        if len(fp) >= 3 and fp[-1] == fp[-2] == fp[-3]:
            return True
        if len(fp) >= 4 and fp[-1] == fp[-3] and fp[-2] == fp[-4]:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "intent": self.intent,
            "subgoals": [sg.to_dict() for sg in self.subgoals],
            "current_subgoal_idx": self.current_subgoal_idx,
            "step_count": self.step_count,
            "max_steps": self.max_steps,
            "status": self.status.value,
            "referenced_entities": self.referenced_entities,
        }


# ═══════════════════════════════════════════════════════════════════════════
# SessionState — persists across tasks
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SessionState:
    session_id: str

    # Current + previous page snapshot (updated each step from WorldModel)
    url: str = ""
    previous_url: str = ""                # last non-current URL seen; supports "go back"
    page_state: str = "GENERIC"           # mirrors WorldModel.page_state.value

    # Durable facts learned from observation
    logged_in: bool = False
    user_label: str = ""                   # detected username/email if visible
    cart: list[CartItem] = field(default_factory=list)

    # Entity memory — the bridge that makes follow-ups work across page transitions
    last_search_query: str = ""
    last_search_domain: str = ""
    last_results: list[ViewedProduct] = field(default_factory=list)
    currently_viewing: Optional[ViewedProduct] = None

    # Conversation + tasks
    conversation: list[dict[str, Any]] = field(default_factory=list)
    history: list[str] = field(default_factory=list)          # raw user commands, in order
    tasks: list[TaskState] = field(default_factory=list)
    active_task: Optional[TaskState] = None

    # Cross-task action + observation memory
    last_actions: list[dict[str, Any]] = field(default_factory=list)   # last 10 actions across ALL tasks
    last_observation_hash: str = ""                                     # rolling hash of URL+title+element count
    observation_stale_count: int = 0                                     # consecutive identical observations

    # Browser shell snapshot (renderer chrome — NOT the webview DOM).
    # Populated from the frontend state payload each step. This is the agent's
    # view of what's in the address bar vs. what's on the page.
    browser_shell: dict[str, Any] = field(default_factory=lambda: {
        "search_bar_available": False,
        "active_input": "none",      # "search_bar" | "page_input" | "none"
        "current_url": "",
    })

    # ── Task management ──────────────────────────────────────────────────

    def start_task(self, task: TaskState) -> None:
        # Mark any prior active task as superseded
        if self.active_task and self.active_task.status == TaskStatus.ACTIVE:
            self.active_task.status = TaskStatus.SUPERSEDED
        self.tasks.append(task)
        self.active_task = task
        self.history.append(task.goal)
        self.conversation.append({
            "role": "user",
            "content": task.goal,
            "task_id": task.task_id,
        })

    def append_agent_message(self, content: str) -> None:
        task_id = self.active_task.task_id if self.active_task else None
        self.conversation.append({
            "role": "agent",
            "content": content,
            "task_id": task_id,
        })

    # ── Fact reconciliation from WorldModel ──────────────────────────────

    def update_from_world_model(self, wm: Any, step: int) -> None:
        """Called BEFORE LLM reasoning every step. Updates durable facts from
        the current page. Must not mutate the WorldModel."""
        # page snapshot — track previous URL for "go back" support
        new_url = getattr(wm, "url", "") or ""
        if new_url and new_url != self.url:
            self.previous_url = self.url
            self.url = new_url
        elif not self.url:
            self.url = new_url

        ps = getattr(wm, "page_state", None)
        self.page_state = ps.value if ps is not None and hasattr(ps, "value") else str(ps or "GENERIC")

        # ── DOM stability detector ────────────────────────────────────
        # Compute a cheap hash of (url, title, element-count-buckets) and track
        # how many consecutive steps observed the same state.
        import hashlib
        title = getattr(wm, "title", "") or ""
        n_products = len(getattr(wm, "products", []) or [])
        n_actions = len(getattr(wm, "actions", []) or [])
        n_filters = len(getattr(wm, "filters", []) or [])
        has_search = bool(getattr(wm, "search", None) and getattr(wm.search, "found", False))
        obs_sig = f"{self.url}|{title}|{self.page_state}|p={n_products}|a={n_actions}|f={n_filters}|s={int(has_search)}"
        h = hashlib.md5(obs_sig.encode()).hexdigest()
        if h == self.last_observation_hash and step > 1:
            self.observation_stale_count += 1
        else:
            self.observation_stale_count = 0
            self.last_observation_hash = h

        # imports done lazily to keep this module light
        try:
            from core.world_model import PageState, extract_cart_items, detect_logged_in, first_price
        except ImportError:
            from .world_model import PageState, extract_cart_items, detect_logged_in, first_price

        # Login inference — works on any page
        if detect_logged_in(wm):
            self.logged_in = True

        if ps == PageState.SEARCH_RESULTS and getattr(wm, "products", None):
            self.last_results = [
                ViewedProduct(
                    rank=p.rank,
                    title=p.title,
                    price=p.price,
                    url=self.url,
                    captured_at_step=step,
                )
                for p in wm.products
            ]
            self.currently_viewing = None

        elif ps == PageState.PRODUCT_PAGE:
            self.currently_viewing = ViewedProduct(
                rank=0,
                title=getattr(wm, "title", "") or "",
                price=first_price(wm),
                url=self.url,
                captured_at_step=step,
            )

        elif ps == PageState.CART_PAGE:
            # Trust DOM over any local cart state
            new_cart = extract_cart_items(wm)
            if new_cart is not None:
                self.cart = new_cart

    # ── Browser shell snapshot (from frontend) ───────────────────────────

    def update_browser_shell(self, shell_dict: dict[str, Any] | None) -> None:
        """Merge the renderer-side browser shell snapshot. Called once per
        incoming WS message before reasoning. Missing keys retain defaults."""
        if not shell_dict:
            return
        # Only accept whitelisted keys to prevent prompt pollution
        for k in ("search_bar_available", "active_input", "current_url"):
            if k in shell_dict:
                self.browser_shell[k] = shell_dict[k]

    # ── Cross-task action memory ─────────────────────────────────────────

    def record_action(self, action_payload: dict[str, Any]) -> None:
        """Record the emitted action across the whole session (not just one task)."""
        self.last_actions.append({
            "action": action_payload.get("action"),
            "selector": action_payload.get("selector"),
            "value": action_payload.get("value"),
            "key": action_payload.get("key"),
            "direction": action_payload.get("direction"),
            "task_id": self.active_task.task_id if self.active_task else None,
        })
        if len(self.last_actions) > 10:
            self.last_actions = self.last_actions[-10:]

    def dom_has_stalled(self, threshold: int = 2) -> bool:
        """True if the observation has been identical for `threshold` consecutive steps.
        Triggers a strategy change (e.g. scroll, reload, abort)."""
        return self.observation_stale_count >= threshold

    # ── Serialization for prompt / debugging ─────────────────────────────

    def facts_summary(self) -> str:
        """Compact human-readable fact block for LLM prompt."""
        lines = []
        lines.append(f"- logged_in: {self.logged_in}")
        if self.user_label:
            lines.append(f"- user: {self.user_label}")
        lines.append(f"- cart_items: {len(self.cart)}")
        if self.cart:
            for c in self.cart[:5]:
                lines.append(f"    * {c.title[:60]} (x{c.quantity}) {c.price}")
        if self.last_search_query:
            lines.append(f"- last_search: \"{self.last_search_query}\""
                         + (f" on {self.last_search_domain}" if self.last_search_domain else ""))
        if self.last_results:
            lines.append(f"- last_results: {len(self.last_results)} items remembered")
            for p in self.last_results[:5]:
                price = f" - {p.price}" if p.price else ""
                lines.append(f"    {p.rank}. {p.title[:60]}{price}")
        if self.currently_viewing:
            cv = self.currently_viewing
            lines.append(f"- currently_viewing: {cv.title[:80]}"
                         + (f" ({cv.price})" if cv.price else ""))
        return "\n".join(lines) if lines else "(no facts yet)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "url": self.url,
            "page_state": self.page_state,
            "logged_in": self.logged_in,
            "user_label": self.user_label,
            "cart": [c.to_dict() for c in self.cart],
            "last_search_query": self.last_search_query,
            "last_search_domain": self.last_search_domain,
            "last_results": [p.to_dict() for p in self.last_results],
            "currently_viewing": self.currently_viewing.to_dict() if self.currently_viewing else None,
            "active_task": self.active_task.to_dict() if self.active_task else None,
            "task_count": len(self.tasks),
        }


def new_task_id() -> str:
    return str(uuid.uuid4())
