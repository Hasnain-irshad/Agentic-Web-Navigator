"""
WSAgent: WebSocket-driven decision agent.

Receives the current DOM observation JSON from the Electron frontend, reasons
over SessionState + TaskState + WorldModel, and returns ONE primitive action.
NEVER executes actions — the Electron renderer owns execution.

Pipeline per step:
  1. Parse incoming DOM state -> Observation
  2. Build WorldModel from Observation
  3. Reconcile SessionState (cart, login, viewed products) from WorldModel
  4. Advance deterministic subgoals (TaskPlanner owns completion, not LLM)
  5. Check step budget + loop detection
  6. Ask LLM for next primitive action, constrained by active subgoal
  7. Resolve logical selectors to real CSS via WorldModel + SessionState
  8. Emit action JSON to the frontend
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from core.observation_extractor import Observation, PageElement
    from core.world_model import WorldModelBuilder, WorldModel, PageState
    from core.llm_prompt_builder import build_action_prompt_v2
    from core.agent_reasoner import AgentReasoner
    from core.element_resolver import parse_ordinal
    from core.session_state import SessionState, TaskState, TaskStatus, SubgoalKind
    from core.task_planner import TaskPlanner
    from core.command_interceptor import intercept as intercept_command
    from schemas.actions import ActionType
    from utils import get_logger
except ImportError:
    from .observation_extractor import Observation, PageElement
    from .world_model import WorldModelBuilder, WorldModel, PageState
    from .llm_prompt_builder import build_action_prompt_v2
    from .agent_reasoner import AgentReasoner
    from .element_resolver import parse_ordinal
    from .session_state import SessionState, TaskState, TaskStatus, SubgoalKind
    from .task_planner import TaskPlanner
    from .command_interceptor import intercept as intercept_command
    from ..schemas.actions import ActionType
    from ..utils import get_logger


logger = get_logger(__name__)


class WSAgent:
    """Per-WebSocket-connection agent. Lives in server.ACTIVE_SESSIONS."""

    def __init__(self, session_id: str) -> None:
        self.session = SessionState(session_id=session_id)
        self.planner = TaskPlanner()
        self.reasoner = AgentReasoner()
        self.recent_steps: list[str] = []   # scoped to active task

    # ════════════════════════════════════════════════════════════════════
    # Command ingestion
    # ════════════════════════════════════════════════════════════════════

    def add_command(self, command: str) -> TaskState:
        """Decompose the new command into a TaskState and activate it.
        Does NOT reset session-level facts — those are what makes follow-ups
        like 'add 2nd item to cart' work."""
        task = self.planner.decompose(command, self.session)
        self.session.start_task(task)
        self.recent_steps = []
        logger.info(f"[WSAgent] Started task {task.task_id[:8]} | intent={task.intent}")
        return task

    def try_intercept(self, command: str) -> Optional[dict[str, Any]]:
        """Rule-based fast path. Returns an action payload for 'go back',
        'refresh', 'scroll', etc. — bypasses LLM entirely. Returns None if
        the command needs planning."""
        payload = intercept_command(command)
        if payload is None:
            return None
        logger.info(f"[WSAgent] Intercepted command '{command}' -> {payload['action']}")
        self.session.history.append(command)
        self.session.conversation.append({
            "role": "user", "content": command, "task_id": None,
        })
        self.session.record_action(payload)
        payload.setdefault("done", True)          # one-shot rule actions finish immediately
        payload.setdefault("task_status", "awaiting_user")
        return payload

    # ════════════════════════════════════════════════════════════════════
    # Observation parsing
    # ════════════════════════════════════════════════════════════════════

    def parse_state(self, state_dict: dict[str, Any]) -> Observation:
        elements = []
        for raw in state_dict.get("elements", []) or []:
            try:
                elements.append(PageElement(
                    index=raw.get("index", 0),
                    tag=raw.get("tag", ""),
                    text=raw.get("text", ""),
                    css_selector=raw.get("css_selector", ""),
                    element_type=raw.get("element_type", raw.get("type", "other")),
                    attributes=raw.get("attributes", {}) or {},
                    is_clickable=raw.get("is_clickable", False),
                    nearby_text=raw.get("nearby_text", ""),
                    bounding_box=raw.get("bounding_box"),
                ))
            except Exception as e:
                logger.warning(f"[WSAgent] Skipping malformed element: {e}")

        return Observation(
            url=state_dict.get("url", ""),
            title=state_dict.get("title", ""),
            elements=elements,
            page_text=state_dict.get("page_text", ""),
            error=state_dict.get("error", ""),
        )

    # ════════════════════════════════════════════════════════════════════
    # Main step loop — called once per WS message
    # ════════════════════════════════════════════════════════════════════

    async def step(self, state_dict: dict[str, Any]) -> dict[str, Any]:
        obs = self.parse_state(state_dict)
        world_model = WorldModelBuilder.build(obs)

        # (A) Reconcile session facts BEFORE reasoning
        task = self.session.active_task
        step_no = task.step_count if task else 0
        self.session.update_from_world_model(world_model, step=step_no)
        # Browser shell snapshot (address bar, active input) from renderer
        self.session.update_browser_shell(state_dict.get("browser_shell"))

        # (B) Task lifecycle gate
        if task is None:
            return self._idle("No active task. Send a command first.")
        if task.status == TaskStatus.SUPERSEDED:
            return self._idle("Task was superseded by a newer command.")
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.AWAITING):
            return self._idle(f"Task already {task.status.value}.")

        # (B.5) Clarification-subgoal fast-path: emit a message, await user.
        # This is triggered when the planner couldn't resolve a domain and
        # the current URL is about:blank/empty — we never auto-go to google.
        cs = task.current_subgoal
        if cs is not None and cs.kind == SubgoalKind.CUSTOM and cs.params.get("reason") == "missing_domain":
            task.status = TaskStatus.AWAITING
            prompt = cs.params.get("prompt") or "Which site should I use?"
            self.session.append_agent_message(prompt)
            return {
                "action": "idle",
                "reasoning": prompt,
                "done": True,
                "task_id": task.task_id,
                "task_status": task.status.value,
            }

        # (C) Advance subgoals if the observation shows they're satisfied
        self.planner.advance_subgoal_if_satisfied(task, self.session, world_model)

        if task.status == TaskStatus.COMPLETED:
            msg = f"Completed: {task.goal}"
            self.session.append_agent_message(msg)
            task.status = TaskStatus.AWAITING
            return {
                "action": "done",
                "reasoning": msg,
                "done": True,
                "task_id": task.task_id,
                "task_status": task.status.value,
                "session_facts": self.session.to_dict(),
            }

        # (D) Loop / DOM-stability / budget guards
        if task.is_looping():
            task.status = TaskStatus.FAILED
            return {
                "action": "done",
                "reasoning": "Stopped due to loop",
                "done": True,
                "task_id": task.task_id,
                "task_status": task.status.value,
            }

        # If the observation hasn't changed for N consecutive steps AND
        # the last emitted action wasn't a scroll, force a strategy change.
        if self.session.dom_has_stalled(threshold=2):
            last = self.session.last_actions[-1] if self.session.last_actions else None
            last_action_type = (last or {}).get("action")
            if last_action_type not in ("scroll", "reload"):
                logger.info("[WSAgent] DOM stalled — forcing scroll to break stagnation")
                return self._emit_action(task, {
                    "action": "scroll",
                    "direction": "down",
                    "reasoning": "DOM unchanged across steps — scrolling to reveal new content",
                })

        task.step_count += 1
        if task.step_count > task.max_steps:
            task.status = TaskStatus.FAILED
            return {
                "action": "done",
                "reasoning": f"Step budget exhausted ({task.max_steps}).",
                "done": True,
                "task_id": task.task_id,
                "task_status": task.status.value,
            }

        # (E) Deterministic shortcut for NAVIGATE — no need to bother the LLM
        shortcut = self._navigation_shortcut(task)
        if shortcut is not None:
            return self._emit_action(task, shortcut)

        # (F) Ask LLM for the next primitive action, constrained by subgoal
        prompt = build_action_prompt_v2(
            world_model=world_model,
            task=task,
            session=self.session,
            recent_steps=self.recent_steps,
        )
        near_limit = (task.max_steps - task.step_count) <= 3
        action = await self.reasoner.decide_action_from_prompt(prompt, is_near_limit=near_limit)

        # Force-override: if LLM emitted `done`, ignore it — planner owns completion
        if action.action_type == ActionType.DONE:
            logger.warning("[WSAgent] LLM tried to emit DONE; overriding to scroll to give planner more signal")
            return self._emit_action(task, {
                "action": "scroll",
                "direction": "down",
                "reasoning": "LLM emitted done but planner disagrees; scrolling to find missing signal.",
            })

        # (F.5) Deterministic action guardrail — reject page-state violations
        corrected = self._guardrail(action, world_model, task)
        if corrected is not None:
            return self._emit_action(task, corrected)

        # (G) Resolve logical selectors to real CSS
        if action.action_type in (ActionType.CLICK, ActionType.TYPE):
            resolution = self._resolve_action_target(action, world_model, task)
            if isinstance(resolution, PageElement):
                action.selector = resolution.css_selector
                action.element_index = resolution.index
            elif isinstance(resolution, dict) and resolution.get("navigate_to"):
                # We need to navigate back to a page that contains the target entity
                logger.info(f"[WSAgent] Redirecting to {resolution['navigate_to']} to reach entity")
                return self._emit_action(task, {
                    "action": "goto",
                    "value": resolution["navigate_to"],
                    "reasoning": resolution.get("reasoning", "Re-navigating to resolve entity reference"),
                })
            else:
                # Can't resolve; ask frontend to scroll and try again
                logger.warning(f"[WSAgent] Could not resolve target '{action.selector}' — emitting scroll")
                return self._emit_action(task, {
                    "action": "scroll",
                    "direction": "down",
                    "reasoning": f"Target '{action.selector}' not visible; scrolling.",
                })

        # (H) Build response payload
        return self._emit_action(task, {
            "action": action.action_type.value,
            "selector": action.selector,
            "value": action.value,
            "key": action.key,
            "direction": action.direction,
            "reasoning": action.reasoning,
        })

    # ════════════════════════════════════════════════════════════════════
    # Resolution helpers
    # ════════════════════════════════════════════════════════════════════

    def _resolve_action_target(
        self,
        action,
        wm: WorldModel,
        task: TaskState,
    ):
        """Map a logical selector to a concrete PageElement, a navigation
        intent dict {"navigate_to": url}, or None if unresolvable.

        Priority:
          1. Subgoal-driven resolution (trust the plan)
          2. Keyword-driven resolution (legacy)
          3. Cross-page entity resolution via session.last_results
        """
        selector = (action.selector or "").lower()
        reasoning = (action.reasoning or "").lower()
        combined = f"{selector} {reasoning}"
        current = task.current_subgoal

        # ── 1. Subgoal-driven resolution ────────────────────────────────
        if current is not None:
            kind = current.kind

            if kind == SubgoalKind.SEARCH and action.action_type == ActionType.TYPE:
                if wm.search and wm.search.found:
                    elem = wm.resolve_element(wm.search.element_index)
                    if elem:
                        if not action.value:
                            action.value = current.params.get("query", "")
                        return elem

            if kind == SubgoalKind.OPEN_RESULT and action.action_type == ActionType.CLICK:
                ordinal = int(current.params.get("ordinal") or 0)  # 1-based
                return self._resolve_nth_result(ordinal, wm)

            if kind == SubgoalKind.ADD_TO_CART and action.action_type == ActionType.CLICK:
                elem = self._resolve_cart_button(wm)
                if elem:
                    return elem

        # ── 2. Keyword-driven (for subgoals like NAVIGATE/CUSTOM or unclear cases) ──
        if "search" in selector and action.action_type == ActionType.TYPE:
            if wm.search and wm.search.found:
                return wm.resolve_element(wm.search.element_index)

        if selector.startswith("item_"):
            try:
                n = int(selector.split("item_", 1)[1])
                return self._resolve_nth_result(n, wm)
            except Exception:
                pass

        if any(kw in combined for kw in ["product", "item", "result", "listing"]):
            ordinal = parse_ordinal(combined)
            if ordinal is not None:
                return self._resolve_nth_result(ordinal + 1, wm)
            if wm.products:
                return wm.resolve_element(wm.products[0].element_index)

        if selector.startswith("action:") or any(kw in combined for kw in ["cart", "buy", "add", "checkout", "purchase"]):
            elem = self._resolve_cart_button(wm)
            if elem:
                return elem

        if selector.startswith("filter:") or any(kw in combined for kw in ["sort", "filter", "price low", "low to high", "high to low"]):
            if wm.filters:
                # Try to match by label token
                tokens = set(combined.replace("filter:", "").split())
                for flt in wm.filters:
                    if any(tok in flt.label.lower() for tok in tokens if len(tok) > 2):
                        elem = wm.resolve_element(flt.element_index)
                        if elem:
                            return elem
                return wm.resolve_element(wm.filters[0].element_index)

        return None

    def _resolve_nth_result(self, ordinal: int, wm: WorldModel):
        """Resolve the Nth result, with cross-page fallback to session memory."""
        if ordinal < 1:
            ordinal = 1

        # Case A: we're on a page that has the products right now
        if wm.products and ordinal <= len(wm.products):
            product = wm.products[ordinal - 1]
            elem = wm.resolve_element(product.element_index)
            if elem:
                return elem

        # Case B: current page doesn't have products, but session remembers them
        if self.session.last_results and ordinal <= len(self.session.last_results):
            target = self.session.last_results[ordinal - 1]
            if target.url and target.url != self.session.url:
                return {
                    "navigate_to": target.url,
                    "reasoning": f"Navigating back to results page to reach item #{ordinal}",
                }

        return None

    def _resolve_cart_button(self, wm: WorldModel):
        """Prefer cart/buy/add buttons; fall back to first action button."""
        if not wm.actions:
            return None
        for act in wm.actions:
            label = act.label.lower()
            if any(k in label for k in ["cart", "buy now", "add to bag", "add to basket", "checkout"]):
                elem = wm.resolve_element(act.element_index)
                if elem:
                    return elem
        return wm.resolve_element(wm.actions[0].element_index)

    # ════════════════════════════════════════════════════════════════════
    # Deterministic action guardrails
    # ════════════════════════════════════════════════════════════════════

    def _guardrail(self, action, wm: WorldModel, task: TaskState) -> Optional[dict[str, Any]]:
        """Reject LLM actions that violate page-state rules. Returns a
        corrective action payload, or None to let the LLM action through.

        Rules:
          - Add-to-cart click is only valid on PRODUCT_PAGE.
          - On LOGIN_PAGE, the only allowed non-login action is `goto`.
          - On SEARCH_RESULTS, `type` is only allowed in the search box
            (re-search). Other `type` actions are treated as drift.
        """
        ps = wm.page_state
        combined = f"{action.selector or ''} {action.reasoning or ''}".lower()
        current = task.current_subgoal
        kind = current.kind if current else None

        # Rule 1: add-to-cart gate
        cart_kw = ("cart", "buy now", "add to bag", "add to basket", "checkout")
        looks_like_cart_click = (
            action.action_type == ActionType.CLICK
            and any(k in combined for k in cart_kw)
        )
        if looks_like_cart_click and ps != PageState.PRODUCT_PAGE:
            logger.warning(
                f"[Guardrail] LLM tried add-to-cart on {ps.value}; correcting."
            )
            if ps == PageState.SEARCH_RESULTS and wm.has_products:
                # Open the first product so we can then legally add-to-cart
                first = wm.products[0]
                elem = wm.resolve_element(first.element_index)
                if elem:
                    return {
                        "action": "click",
                        "selector": elem.css_selector,
                        "reasoning": f"Guardrail: must open a product before add-to-cart (opening '{first.title[:40]}')",
                    }
            # No recoverable correction — scroll to reveal product links
            return {
                "action": "scroll",
                "direction": "down",
                "reasoning": f"Guardrail: add-to-cart not allowed on {ps.value}; scrolling to find a product",
            }

        # Rule 2: LOGIN_PAGE lock-in
        if ps == PageState.LOGIN_PAGE and kind != SubgoalKind.LOGIN:
            # Allow navigation away, but block interactions that don't make sense
            if action.action_type == ActionType.CLICK and not any(
                k in combined for k in ("login", "sign in", "submit", "home", "cancel")
            ):
                return {
                    "action": "goto",
                    "value": f"https://{(self.session.last_search_domain or 'google.com')}",
                    "reasoning": "Guardrail: on a login page but task is not login — navigating away",
                }

        # Rule 3: stray `type` on SEARCH_RESULTS
        if (
            action.action_type == ActionType.TYPE
            and ps == PageState.SEARCH_RESULTS
            and kind != SubgoalKind.SEARCH
            and "search" not in combined
        ):
            logger.warning("[Guardrail] Stray type on SEARCH_RESULTS; converting to scroll")
            return {
                "action": "scroll",
                "direction": "down",
                "reasoning": "Guardrail: unexpected type action on results page",
            }

        # Rule 4: Loop-break fallback — if the last 2 page-level `type` actions
        # made no progress, switch to the browser address bar. This implements
        # the "search bar -> URL bar -> page search fallback" escalation.
        if action.action_type == ActionType.TYPE and action.value:
            recent = [a for a in self.session.last_actions[-2:] if a]
            if (
                len(recent) >= 2
                and all(a.get("action") == "type" for a in recent)
                and self.session.observation_stale_count >= 1
            ):
                logger.warning("[Guardrail] Repeated page-type didn't progress; escalating to browser bar")
                return {
                    "action": "browser_search",
                    "value": action.value,
                    "reasoning": "Guardrail: page input isn't working; escalating to browser address bar",
                }

        return None

    # ════════════════════════════════════════════════════════════════════
    # Deterministic shortcuts
    # ════════════════════════════════════════════════════════════════════

    def _navigation_shortcut(self, task: TaskState) -> Optional[dict[str, Any]]:
        """If the current subgoal is NAVIGATE or BROWSER_BAR_SEARCH and we're
        not there yet, emit the corresponding shell/navigation action directly
        without invoking the LLM. Cheap, reliable, and human-like."""
        sg = task.current_subgoal
        if sg is None:
            return None

        # ── BROWSER-BAR route (preferred): drive the shell address bar ──
        if sg.kind == SubgoalKind.BROWSER_BAR_SEARCH:
            query = (sg.params.get("query") or "").strip()
            domain = (sg.params.get("domain") or "").strip().lower()
            if not query and domain:
                query = domain
            if not query:
                return None

            # Already there?
            if domain and domain in (self.session.url or "").lower():
                return None

            return {
                "action": "browser_search",
                "value": query,
                "reasoning": f"Subgoal BROWSER_BAR_SEARCH -> type '{query}' into address bar",
            }

        # ── Legacy NAVIGATE (direct webview load). Kept for backward compat
        #     but BROWSER_BAR_SEARCH is strongly preferred. ──
        if sg.kind == SubgoalKind.NAVIGATE:
            domain = (sg.params.get("domain") or "").strip().lower()
            url = (sg.params.get("url") or "").strip()

            if url:
                target = url
            elif domain:
                target = f"https://{domain}" if not domain.startswith("http") else domain
            else:
                return None

            if domain and domain in (self.session.url or "").lower():
                return None

            # Even the legacy path prefers the shell bar over webview.loadURL
            return {
                "action": "browser_navigate",
                "value": target,
                "reasoning": f"Subgoal NAVIGATE -> address bar loads {target}",
            }

        return None

    # ════════════════════════════════════════════════════════════════════
    # Emit / bookkeeping
    # ════════════════════════════════════════════════════════════════════

    def _emit_action(self, task: TaskState, payload: dict[str, Any]) -> dict[str, Any]:
        """Finalize the response, record fingerprint + trail, return dict."""
        payload.setdefault("done", False)
        payload.setdefault("task_id", task.task_id)
        payload.setdefault("task_status", task.status.value)

        fp = f"{payload.get('action')}:{payload.get('selector') or payload.get('value') or payload.get('direction') or payload.get('key') or ''}"
        task.record_action(fp)
        # Cross-task session memory
        self.session.record_action(payload)

        trail = fp
        if payload.get("reasoning"):
            trail = f"{fp} -> {payload['reasoning'][:80]}"
        self.recent_steps.append(trail)
        self.recent_steps = self.recent_steps[-10:]

        # Attach a compact view of session facts so the frontend can display
        payload["session_snapshot"] = {
            "url": self.session.url,
            "page_state": self.session.page_state,
            "logged_in": self.session.logged_in,
            "cart_count": len(self.session.cart),
            "last_search": self.session.last_search_query,
            "subgoal": (task.current_subgoal.description if task.current_subgoal else None),
        }
        return payload

    def _idle(self, message: str) -> dict[str, Any]:
        return {
            "action": "idle",
            "done": True,
            "reasoning": message,
            "task_status": "awaiting_user",
        }
