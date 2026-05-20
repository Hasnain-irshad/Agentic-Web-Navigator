"""
AgentReasoner: LLM-based decision engine using Groq.
Decides next action based on goal, observation, and memory.

Now uses REAL DOM element indices instead of hallucinated selectors.
The LLM sees a numbered list of real elements and picks by [index].
"""

import json
import re
from typing import Optional

from groq import Groq

try:
    from schemas import Action, ActionType
    from config import Config
    from utils import get_logger
    from core.memory_store import Context
    from core.llm_prompt_builder import get_system_prompt
except ImportError:
    from ..schemas import Action, ActionType
    from ..config import Config
    from ..utils import get_logger
    from .memory_store import Context
    from .llm_prompt_builder import get_system_prompt


logger = get_logger(__name__)


# System prompt is now managed dynamically by llm_prompt_builder

class AgentReasoner:
    """
    LLM-based reasoning engine for action selection.
    
    Uses Groq API with Llama models to decide the next action.
    Operates on the structured WorldModel representation.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ) -> None:
        """
        Initialize the reasoner with Groq API.
        
        Args:
            api_key: Groq API key. Defaults to Config.GROQ_API_KEY.
            model: Model to use. Defaults to Config.LLM_MODEL.
            
        Raises:
            ValueError: If API key is not provided
        """
        self._api_key = api_key or Config.GROQ_API_KEY
        self._model = model or Config.LLM_MODEL
        
        if not self._api_key:
            raise ValueError(
                "Groq API key is required. Set GROQ_API_KEY in .env file."
            )
        
        self._client = Groq(api_key=self._api_key)
        logger.info(f"AgentReasoner initialized with model: {self._model}")
    
    async def decide_action_from_prompt(self, prompt: str, is_near_limit: bool = False) -> Action:
        """
        Decide the next action based on a fully formatted World Model prompt.
        """
        if is_near_limit:
            prompt += "\n\n⚠️ WARNING: Step limit approaching! Prioritize completing the goal."
            
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = self._call_llm(prompt)
                action = self._parse_response(response)
                
                logger.info(
                    f"Decided action: {action.action_type.value} "
                    f"(target='{action.selector}', attempt {attempt + 1})"
                )
                return action
                
            except Exception as e:
                last_error = e
                logger.warning(f"Reasoning attempt {attempt + 1} failed: {e}")
                prompt += f"\n\nPrevious response was invalid: {e}\nPlease output ONLY valid JSON using the format provided."
        
        logger.error(f"All reasoning attempts failed. Last error: {last_error}")
        return Action(
            action_type=ActionType.DONE,
            reasoning=f"Reasoning failed after {max_retries} attempts: {last_error}"
        )

    # Legacy method for Context integration (will be phased out)
    async def decide_action(self, context: Context) -> Action:
        prompt = context.to_prompt_text()
        remaining = context.max_steps - context.step_count
        return await self.decide_action_from_prompt(prompt, remaining <= 3)
    
    def _call_llm(self, prompt: str) -> str:
        """
        Call the Groq LLM API.
        
        Args:
            prompt: User prompt with context
            
        Returns:
            LLM response text
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=Config.LLM_TEMPERATURE,
                max_tokens=Config.LLM_MAX_TOKENS,
            )
            
            content = response.choices[0].message.content
            logger.debug(f"LLM response: {content[:200]}...")
            return content
            
        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            raise RuntimeError(f"LLM API error: {e}") from e
    
    def _parse_response(self, response: str) -> Action:
        """
        Parse LLM response into an Action.
        Extracts element_index for grounded actions.
        
        Args:
            response: Raw LLM response text
            
        Returns:
            Parsed and validated Action
            
        Raises:
            ValueError: If response cannot be parsed
        """
        response = response.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group()
        else:
            json_str = response
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {e}")

        if "action_type" not in data and "action" not in data:
            raise ValueError("Missing 'action' or 'action_type' in LLM response JSON")

        # Accept both "selector" referencing a number and "element_index"
        # Some LLMs may still output selector as a number — handle that
        if "element_index" not in data and "selector" in data:
            sel = data["selector"]
            if isinstance(sel, int):
                data["element_index"] = sel
                del data["selector"]
            elif isinstance(sel, str) and sel.isdigit():
                data["element_index"] = int(sel)
                del data["selector"]

        # Clean to allowed keys only
        allowed = {"action", "target", "action_type", "selector", "value", "direction", "key", "element_index", "reasoning", "stop_decision", "updated_state"}
        clean = {k: v for k, v in data.items() if k in allowed}

        if str(clean.get("stop_decision", "NO")).strip().upper() == "YES":
            clean["action"] = "done"

        return Action.from_dict(clean)

    def _is_goal_satisfied(self, context: Context) -> bool:
        """
        Heuristic check whether the current page likely satisfies the user's goal.
        """
        try:
            obs = context.current_observation
            txt = (obs.page_text or "").lower()
            product_keywords = ["add to cart", "buy now", "price", "product", "items found", "results for"]
            admissions_keywords = ["admission", "apply", "portal", "masters", "graduate", "undergraduate"]

            for e in getattr(obs, "elements", []) or []:
                etype = (e.element_type or "").lower()
                if etype == "product":
                    return True
                href = (e.attributes.get("href") or "").lower()
                if etype == "link" and ("product" in href or "/product/" in href):
                    return True

            if any(k in txt for k in product_keywords + admissions_keywords):
                return True

            url = (obs.url or "").lower()
            if any(p in url for p in ["/search", "?q=", "/catalog"]) and any(k in txt for k in ["product", "results", "admission", "apply"]):
                return True

            return False
        except Exception:
            return False


class MockReasoner:
    """
    Mock reasoner for testing without API calls.
    """
    
    def __init__(self) -> None:
        """Initialize mock reasoner."""
        self._step = 0
        logger.info("MockReasoner initialized (no API calls)")
    
    async def decide_action(self, context: Context) -> Action:
        """Return predefined actions for testing."""
        self._step += 1
        
        if self._step == 1:
            return Action(
                action_type=ActionType.GOTO,
                value="https://www.google.com",
                reasoning="Mock: navigating to Google"
            )
        elif self._step == 2:
            return Action(
                action_type=ActionType.TYPE,
                element_index=1,  # Use element index instead of selector
                value="test query",
                reasoning="Mock: typing search query"
            )
        elif self._step >= 3:
            return Action(
                action_type=ActionType.DONE,
                reasoning="Mock: completing task"
            )
        
        return Action(
            action_type=ActionType.DONE,
            reasoning="Mock: fallback completion"
        )
