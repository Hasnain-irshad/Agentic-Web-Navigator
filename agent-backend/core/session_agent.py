"""
SessionAgent: World-Model-driven browser session agent.

Key architecture change: The LLM NEVER sees raw DOM.
Instead, it receives a structured WorldModel and returns structured actions.

Pipeline per step:
1. EXTRACT  — JS injection extracts real DOM elements
2. BUILD    — WorldModelBuilder converts elements → structured WorldModel
3. PROMPT   — LLM receives compact world model, decides next action
4. RESOLVE  — Action target is resolved back to real CSS selector
5. EXECUTE  — Playwright executes with the real selector
6. VERIFY   — Post-action validation
"""

import asyncio
import json
import random
import re
from typing import Optional

try:
    from core import BrowserController, ObservationExtractor, MemoryStore, AgentReasoner
    from core.agent_reasoner import MockReasoner
    from core.planner import Planner
    from core.world_model import WorldModel, WorldModelBuilder, PageState
    from core.llm_prompt_builder import build_action_prompt, get_system_prompt
    from core.element_resolver import (
        IntentType, detect_intent, ElementResolver,
        parse_ordinal, validate_element_basic
    )
    from core.stop_conditions import should_stop, CompletionDetector, RepetitionDetector
    from schemas import ActionType, Action
    from config import Config
    from utils import get_logger
except ImportError:
    from .browser_controller import BrowserController
    from .observation_extractor import ObservationExtractor
    from .memory_store import MemoryStore
    from .agent_reasoner import AgentReasoner, MockReasoner
    from .planner import Planner
    from .world_model import WorldModel, WorldModelBuilder, PageState
    from .llm_prompt_builder import build_action_prompt, get_system_prompt
    from .element_resolver import (
        IntentType, detect_intent, ElementResolver,
        parse_ordinal, validate_element_basic
    )
    from .stop_conditions import should_stop, CompletionDetector, RepetitionDetector
    from ..schemas import ActionType, Action
    from ..config import Config
    from ..utils import get_logger


logger = get_logger(__name__)


class SessionAgent:
    """
    World-Model-driven browser session agent.

    The LLM never sees raw DOM. It only sees structured WorldModel output
    and returns structured actions that reference world model items.
    """

    def __init__(
        self,
        max_steps_per_command: int = 20,
        headless: bool = False,
        use_mock: bool = False,
    ) -> None:
        self._max_steps = max_steps_per_command
        self._headless = headless
        self._use_mock = use_mock

        self._browser: Optional[BrowserController] = None
        self._extractor = ObservationExtractor()
        self._memory: Optional[MemoryStore] = None
        self._planner: Optional[Planner] = None
        self._reasoner = None
        self._is_running = False
        self._current_goal = ""
        self._command_history: list[dict] = []
        self._command_lock: Optional[asyncio.Lock] = None
        self._step_history: list[str] = []

    @property
    def is_active(self) -> bool:
        return self._browser is not None and self._is_running

    async def start_session(self) -> dict:
        if self._is_running:
            return {"status": "already_running", "message": "Session already active"}

        try:
            logger.info("Starting browser session...")

            if not self._use_mock:
                Config.validate()
                self._planner = Planner()
                self._reasoner = AgentReasoner()
            else:
                self._reasoner = MockReasoner()

            self._browser = BrowserController(headless=self._headless)
            await self._browser.start()
            self._is_running = True
            self._command_lock = asyncio.Lock()

            logger.info("Browser session started successfully")
            return {
                "status": "started",
                "message": "Browser session started. Enter commands to interact."
            }

        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            return {"status": "error", "message": str(e)}

    # ══════════════════════════════════════════════════════════════════════
    # Main Command Execution
    # ══════════════════════════════════════════════════════════════════════

    async def execute_command(self, goal: str, callback=None) -> dict:
        """
        Execute a command using the world-model-driven pipeline.
        """
        if not self._is_running:
            return {"status": "error", "message": "No active session. Start session first."}

        if self._command_lock is None:
            self._command_lock = asyncio.Lock()

        if self._command_lock.locked():
            return {"status": "busy", "message": "Another command is currently running."}

        async with self._command_lock:
            self._current_goal = goal
            self._step_history = []
            logger.info(f"Processing command: {goal}")

            step_count = 0
            successful = 0
            failed = 0
            actions_executed = []
            self._memory = MemoryStore(goal, self._max_steps)

            try:
                # ── Dynamic Agentic Loop ─────────────────────────────
                logger.info(f"Executing dynamic loop (max {self._max_steps} steps)")

                while step_count < self._max_steps:
                    try:
                        step_count += 1
                        
                        # 1. Extract observation and build World Model
                        page = await self._browser.get_current_page()
                        obs = await self._extractor.extract(page)
                        self._browser.set_observation(obs)
                        
                        if callback:
                            callback("observe", f"Step {step_count}: Extracted {len(obs.elements)} real DOM elements")
                            
                        world_model = WorldModelBuilder.build(obs)
                        
                        if callback:
                            callback("world_model", 
                                f"Page: {world_model.page_state.value} | "
                                f"Items: {len(world_model.products)} | "
                                f"Actions: {len(world_model.actions)}")

                        # 2. Build Prompt and Decide Action
                        prompt = build_action_prompt(world_model, goal, self._step_history)
                        
                        if callback:
                            callback("plan", "Thinking...")
                            
                        action = await self._reasoner.decide_action_from_prompt(
                            prompt,
                            is_near_limit=(self._max_steps - step_count) <= 3
                        )
                        
                        if callback:
                            callback("step", f"Action: {action.action_type.value} | target: {action.selector} | key: {action.key}")

                        # 3. Handle DONE
                        if action.action_type == ActionType.DONE:
                            logger.info("Task marked as complete by LLM")
                            successful += 1
                            actions_executed.append({
                                "step": step_count,
                                "action": "done",
                                "success": True,
                                "message": "Task complete",
                            })
                            break

                        # 4. Resolve World Model references to real CSS
                        if action.action_type in (ActionType.CLICK, ActionType.TYPE):
                            resolved = self._resolve_via_world_model(
                                world_model, action, callback
                            )
                            
                            if resolved:
                                action.element_index = resolved.index
                                action.selector = resolved.css_selector
                                logger.info(
                                    f"RESOLVED: '{action.selector}' -> "
                                    f"element [{resolved.index}] '{resolved.text[:50]}' "
                                )
                                if callback:
                                    callback("resolve", f"Selected: [{resolved.index}] {resolved.text[:40]}")
                            else:
                                # Fallback: Try scroll and retry
                                resolved = await self._scroll_and_resolve(
                                    page, action, callback
                                )
                                if resolved:
                                    action.element_index = resolved.index
                                    action.selector = resolved.css_selector
                                    if callback:
                                        callback("resolve", f"Selected (after scroll): [{resolved.index}] {resolved.text[:40]}")
                                else:
                                    logger.warning(f"Could not resolve target: {action.selector}")
                                    if callback:
                                        callback("error", f"Could not find element for: {action.selector}")
                                    failed += 1
                                    continue

                        # 5. Execute Action via Playwright
                        result = await self._browser.execute_action(action)

                        if result.success:
                            successful += 1
                            status_icon = "OK"
                            desc = f"{action.action_type.value} {action.selector or action.key or action.value or ''}"
                            self._step_history.append(desc.strip() + f" -> {action.reasoning}")
                        else:
                            failed += 1
                            status_icon = "FAIL"
                            desc = f"{action.action_type.value} {action.selector or action.key or action.value or ''}"
                            self._step_history.append(desc.strip() + f" -> FAILED: {result.message[:50]}")

                        if callback:
                            callback("execute", f"{status_icon} {result.message[:60]}")

                        actions_executed.append({
                            "step": step_count,
                            "action": action.action_type.value,
                            "target": action.selector,
                            "success": result.success,
                            "message": result.message[:100],
                        })

                        # 6. Wait for navigation / rendering
                        if action.action_type in (
                            ActionType.GOTO, ActionType.CLICK, ActionType.PRESS_KEY
                        ):
                            try:
                                page = await self._browser.get_current_page()
                                await page.wait_for_load_state(
                                    "domcontentloaded", timeout=5000
                                )
                            except Exception:
                                pass

                        # Human-like delay
                        await asyncio.sleep(random.uniform(0.8, 1.5))

                    except Exception as e:
                        logger.error(f"Step {step_count} failed: {e}")
                        failed += 1
                        if callback:
                            callback("error", f"Step failed: {str(e)[:50]}")
                        
                        # Stop if we severely crash
                        break

                # ── Build result ──────────────────────────────────────
                is_completed = (
                    len(actions_executed) > 0
                    and actions_executed[-1].get("action") == "done"
                    and failed == 0
                )

                command_result = {
                    "goal": goal,
                    "status": "completed" if is_completed else "partial" if successful > 0 else "failed",
                    "steps": step_count,
                    "successful": successful,
                    "failed": failed,
                    "actions": actions_executed,
                }

                self._command_history.append(command_result)
                logger.info(f"Command completed: {successful}/{step_count} successful")
                return command_result

            except Exception as e:
                logger.error(f"Command execution failed: {e}")
                return {
                    "goal": goal,
                    "status": "error",
                    "message": str(e),
                    "steps": step_count,
                    "successful": successful,
                    "failed": failed,
                    "actions": actions_executed,
                }

    # ══════════════════════════════════════════════════════════════════════
    # World Model Resolution
    # ══════════════════════════════════════════════════════════════════════

    def _resolve_via_world_model(self, world_model, action, callback):
        """
        Resolve an action's logical selector to a real PageElement using the WorldModel.
        
        Mapping:
        - "search_input" → world_model.search
        - "first_product" / "second_product" → world_model.products[ordinal]
        - "add_to_cart_button" → world_model.actions (first match)
        """
        selector = (action.selector or "").lower()
        reasoning = (action.reasoning or "").lower()
        combined = f"{selector} {reasoning}"

        logger.info(f"  [RESOLVE] selector='{selector}' | page_state={world_model.page_state.value}")

        # ── Search Input Resolution ──────────────────────────────────
        if "search" in selector and action.action_type == ActionType.TYPE:
            if world_model.search and world_model.search.found:
                elem = world_model.resolve_element(world_model.search.element_index)
                if elem:
                    logger.info(f"  [RESOLVE] Search input found: [{elem.index}] css={elem.css_selector[:50]}")
                    return elem

        # ── Product/Item Click Resolution ────────────────────────────
        if any(kw in combined for kw in ["product", "item", "result", "listing"]):
            ordinal = parse_ordinal(combined)
            if ordinal is not None and world_model.products:
                # ordinal is 0-based from parse_ordinal
                product = world_model.get_product_by_ordinal(ordinal + 1)
                if product:
                    elem = world_model.resolve_element(product.element_index)
                    if elem:
                        logger.info(f"  [RESOLVE] Product #{ordinal+1}: '{product.title[:40]}' -> [{elem.index}]")
                        return elem
            # If no ordinal but products exist, pick first
            elif world_model.products:
                product = world_model.products[0]
                elem = world_model.resolve_element(product.element_index)
                if elem:
                    logger.info(f"  [RESOLVE] First product: '{product.title[:40]}' -> [{elem.index}]")
                    return elem

        # ── Action Button Resolution (Add to Cart, Buy Now) ─────────
        if any(kw in combined for kw in ["cart", "buy", "add", "checkout", "purchase"]):
            if world_model.actions:
                # Try exact-ish match first
                for act in world_model.actions:
                    act_lower = act.label.lower()
                    if any(kw in act_lower for kw in ["cart", "buy", "add", "checkout"]):
                        elem = world_model.resolve_element(act.element_index)
                        if elem:
                            logger.info(f"  [RESOLVE] Action: '{act.label}' -> [{elem.index}]")
                            return elem
                # Fallback to first action
                elem = world_model.resolve_element(world_model.actions[0].element_index)
                if elem:
                    return elem

        # ── Filter/Sort Resolution ───────────────────────────────────
        if any(kw in combined for kw in ["sort", "filter", "price", "low to high"]):
            if world_model.filters:
                for flt in world_model.filters:
                    flt_lower = flt.label.lower()
                    # Try to match the specific filter
                    if any(kw in flt_lower for kw in combined.split()):
                        elem = world_model.resolve_element(flt.element_index)
                        if elem:
                            logger.info(f"  [RESOLVE] Filter: '{flt.label}' -> [{elem.index}]")
                            return elem
                # Fallback to first filter
                elem = world_model.resolve_element(world_model.filters[0].element_index)
                if elem:
                    return elem

        # ── Generic fallback: nothing matched ────────────────────────
        logger.warning(f"  [RESOLVE] No world model match for: '{selector}'")
        return None

    # ══════════════════════════════════════════════════════════════════════
    # Scroll & Retry
    # ══════════════════════════════════════════════════════════════════════

    async def _scroll_and_resolve(self, page, action, callback, max_retries=3):
        """Scroll down and retry world model resolution."""
        for attempt in range(max_retries):
            if callback:
                callback("scroll", f"Scrolling for more elements (attempt {attempt + 1})")

            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(random.uniform(1.0, 2.0))

            obs = await self._extractor.extract(page)
            self._browser.set_observation(obs)
            
            world_model = WorldModelBuilder.build(obs)
            resolved = self._resolve_via_world_model(world_model, action, callback)
            
            if resolved:
                return resolved

        return None

    # ══════════════════════════════════════════════════════════════════════
    # Mock plan for testing
    # ══════════════════════════════════════════════════════════════════════

    def _create_mock_plan(self, goal: str) -> list[dict]:
        """Create a simple mock plan for testing without LLM."""
        try:
            from core.intent_parser import IntentParser
            from core.navigation_router import NavigationOptimizer

            intent = IntentParser.parse(goal)

            if "add to cart" in goal.lower():
                return NavigationOptimizer.build_product_search_plan(
                    intent.query, intent.site, add_to_cart=True
                )
            else:
                return NavigationOptimizer.build_direct_search_plan(
                    intent.query, intent.site
                )
        except Exception as e:
            logger.debug(f"Smart mock plan failed: {e}")

            goal_lower = goal.lower()
            if "daraz" in goal_lower:
                return [
                    {"action": "goto", "value": "https://www.daraz.pk"},
                    {"action": "type", "selector": "search_input", "value": goal_lower.split("search")[-1].strip() or "products"},
                    {"action": "press_key", "key": "Enter"},
                    {"action": "done", "reasoning": "Task complete"},
                ]

            # No domain known. Do NOT auto-redirect to a search engine —
            # return a no-op plan so the caller can ask the user which site to use.
            return [
                {"action": "done", "reasoning": "No target site specified; awaiting user clarification"},
            ]

    async def get_current_page_info(self) -> dict:
        if not self._is_running or not self._browser:
            return {"url": "", "title": "No active session"}
        try:
            page = await self._browser.get_current_page()
            return {"url": page.url, "title": await page.title()}
        except Exception as e:
            return {"url": "", "title": f"Error: {e}"}

    async def end_session(self) -> dict:
        if not self._is_running:
            return {"status": "not_running", "message": "No active session"}
        try:
            if self._browser:
                await self._browser.stop()
            self._is_running = False
            logger.info("Browser session ended")
            return {"status": "ended", "message": "Session ended successfully"}
        except Exception as e:
            logger.error(f"Error ending session: {e}")
            return {"status": "error", "message": str(e)}