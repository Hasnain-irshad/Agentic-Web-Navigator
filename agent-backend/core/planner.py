"""
Planner: Intelligent LLM-based plan generator with smart routing.
Converts user natural language commands into structured multi-step action plans.

Features:
1. Robust intent parsing (LLM + regex) to extract search query and actions
2. Smart navigation routing (Google-independent)
3. Fallback to LLM for complex planning
4. Structured multi-step plans with properly extracted queries
"""

import json
from typing import Optional
from groq import Groq

try:
    from config import Config
    from utils import get_logger
    from schemas import Action, ActionType
    from core.robust_intent_parser import RobustIntentParser, parse_intent, ParsedIntent, ActionType as IntentActionType
    from core.navigation_router import NavigationRouter, NavigationOptimizer
except ImportError:
    from ..config import Config
    from ..utils import get_logger
    from ..schemas import Action, ActionType
    from .robust_intent_parser import RobustIntentParser, parse_intent, ParsedIntent, ActionType as IntentActionType
    from .navigation_router import NavigationRouter, NavigationOptimizer


logger = get_logger(__name__)


PLANNER_SYSTEM_PROMPT = """You are a web automation planner. Convert user requests into a sequence of browser actions.

KEY PRINCIPLE: Avoid Google. If site is known, go directly. If unknown, use DuckDuckGo.

OUTPUT FORMAT: Return ONLY a valid JSON array of action objects. No explanation text.

Action Schema:
{
  "action": "goto" | "type" | "click" | "press_key" | "scroll" | "back" | "done",
  "selector": "<intent_description>",  // for click, type — describe WHAT to interact with
  "value": "<input_or_url>",           // for type, goto
  "key": "<key_name>",                 // for press_key
  "reasoning": "<brief_explanation>"
}

SELECTOR RULES (CRITICAL):
- Selectors are INTENT DESCRIPTIONS, not CSS selectors or element names.
- They describe WHAT you want to interact with so the system can find the real DOM element.
- Examples:
  - "search_input" — the search box on the page
  - "first_product" — the 1st product in the listing
  - "second_product" — the 2nd product in the listing  
  - "add_to_cart_button" — the Add to Cart / Buy Now button
  - "close_popup" — a close/dismiss button
- The execution system will find the REAL element matching this description.
- NEVER use CSS selectors like ".btn" or "#search".

NAVIGATION RULES:
- Daraz → https://www.daraz.pk
- Amazon → https://www.amazon.com  
- YouTube → https://www.youtube.com
- eBay → https://www.ebay.com
- Unknown → DuckDuckGo (https://duckduckgo.com)
- AVOID Google unless explicitly asked

EXAMPLES:

User: "Search for watches on Daraz"
[
  {"action": "goto", "value": "https://www.daraz.pk", "reasoning": "Navigate to Daraz"},
  {"action": "type", "selector": "search_input", "value": "watches", "reasoning": "Type search query"},
  {"action": "press_key", "key": "Enter", "reasoning": "Submit search"},
  {"action": "done", "reasoning": "Search completed"}
]

User: "Search boys watches on daraz and add 2nd item to cart"
[
  {"action": "goto", "value": "https://www.daraz.pk", "reasoning": "Navigate to Daraz"},
  {"action": "type", "selector": "search_input", "value": "boys watches", "reasoning": "Type search query"},
  {"action": "press_key", "key": "Enter", "reasoning": "Submit search"},
  {"action": "click", "selector": "second_product", "reasoning": "Click the 2nd product in results"},
  {"action": "click", "selector": "add_to_cart_button", "reasoning": "Click Add to Cart button"},
  {"action": "done", "reasoning": "Added 2nd item to cart"}
]

Return ONLY valid JSON array.
"""



class Planner:
    """
    Intelligent planner that generates action sequences from user commands.
    
    Strategy:
    1. Parse intent (understand what user wants)
    2. Try smart routing (direct navigation, simple searches)
    3. Fallback to LLM for complex reasoning
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize the planner.
        
        Args:
            api_key: Groq API key (defaults to Config.GROQ_API_KEY)
            model: LLM model name (defaults to Config.LLM_MODEL)
        """
        self.api_key = api_key or Config.GROQ_API_KEY
        self.model = model or Config.LLM_MODEL
        self.client = Groq(api_key=self.api_key)
        self.intent_parser = RobustIntentParser()  # Use robust parser
        self.navigation_router = NavigationRouter()
        
    async def generate_plan(
        self,
        user_command: str,
        page_context: Optional[str] = None,
    ) -> list[dict]:
        """
        Generate a multi-step action plan from user command.
        
        Strategy:
        1. Robustly parse intent (extract clean query and actions)
        2. Try smart routing for common patterns
        3. Fallback to LLM for complex cases
        
        Args:
            user_command: Natural language user request
            page_context: Optional current page state/context for refinement
            
        Returns:
            List of action dictionaries in execution order
            
        Raises:
            ValueError: If plan generation fails
            Exception: If API call fails
        """
        logger.info(f"Planning: {user_command}")
        
        # Step 1: Robustly parse intent (LLM + regex hybrid)
        parsed_intent = self.intent_parser.parse(user_command)
        logger.debug(f"Parsed intent: {parsed_intent}")
        
        # Step 2: Build plan with cleaned query
        # This is the KEY FIX: use parsed_intent.search_query (not full command)
        plan = self._build_plan_from_parsed_intent(parsed_intent)
        
        # Step 3: If actions were extracted, append them
        if parsed_intent.actions:
            logger.debug(f"Appending {len(parsed_intent.actions)} extracted actions")
            plan.extend(self._convert_actions_to_plan(parsed_intent.actions))
        
        # Mark task as done
        plan.append({
            "action": "done",
            "reasoning": "Task completed",
        })
        
        logger.info(f"Generated plan with {len(plan)} steps")
        return plan
    
    def _build_plan_from_parsed_intent(self, intent: ParsedIntent) -> list[dict]:
        """
        Build plan from parsed intent with CLEAN query.
        
        Args:
            intent: ParsedIntent with clean search_query
            
        Returns:
            Action plan
        """
        plan = []
        
        # Determine where to navigate
        site = intent.site
        
        if site == intent.site.__class__.DARAZ:
            plan.append({
                "action": "goto",
                "value": "https://www.daraz.pk",
                "reasoning": "Navigate to Daraz",
            })
        elif site == intent.site.__class__.AMAZON:
            plan.append({
                "action": "goto",
                "value": "https://www.amazon.com",
                "reasoning": "Navigate to Amazon",
            })
        elif site == intent.site.__class__.EBAY:
            plan.append({
                "action": "goto",
                "value": "https://www.ebay.com",
                "reasoning": "Navigate to eBay",
            })
        elif site == intent.site.__class__.YOUTUBE:
            plan.append({
                "action": "goto",
                "value": "https://www.youtube.com",
                "reasoning": "Navigate to YouTube",
            })
        elif site == intent.site.__class__.ALIEXPRESS:
            plan.append({
                "action": "goto",
                "value": "https://www.aliexpress.com",
                "reasoning": "Navigate to AliExpress",
            })
        else:
            # Unknown site - use DuckDuckGo
            plan.append({
                "action": "goto",
                "value": "https://duckduckgo.com",
                "reasoning": "Use DuckDuckGo for search",
            })
        
        # Add search step WITH CLEAN QUERY (THIS IS THE FIX!)
        logger.info(f"Using clean search query: '{intent.search_query}'")
        plan.append({
            "action": "type",
            "selector": "search_input",
            "value": intent.search_query,  # ✅ CLEAN QUERY
            "reasoning": f"Type search query: {intent.search_query}",
        })
        
        plan.append({
            "action": "press_key",
            "key": "Enter",
            "reasoning": "Submit search",
        })
        
        return plan
    
    def _convert_actions_to_plan(self, actions: list) -> list[dict]:
        """
        Convert ParsedIntent actions to plan steps.
        
        Args:
            actions: List of Action objects
            
        Returns:
            List of action dicts
        """
        plan = []
        
        for action in actions:
            action_type_str = action.action_type.value
            
            if action_type_str == "open_item":
                if action.index:
                    ordinal_map = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
                    ordinal_name = ordinal_map.get(action.index, f"{action.index}th")
                    plan.append({
                        "action": "click",
                        "selector": f"{ordinal_name}_product",
                        "reasoning": f"Click the {ordinal_name} product in results",
                    })
            
            elif action_type_str == "add_to_cart":
                plan.append({
                    "action": "click",
                    "selector": "add_to_cart_button",
                    "reasoning": "Click the Add to Cart / Buy Now button",
                })
        
        return plan
    
    async def _generate_plan_with_llm_fallback(
        self,
        user_command: str,
        page_context: Optional[str] = None,
    ) -> list[dict]:
        """
        Generate plan using LLM (fallback for complex cases).
        
        Note: With robust intent parsing, this is rarely needed.
        
        Args:
            user_command: Natural language user request
            page_context: Optional current page context
            
        Returns:
            List of action dictionaries
        """
        # Build context-aware prompt
        user_prompt = f"User request: {user_command}"
        if page_context:
            user_prompt += f"\nCurrent page context:\n{page_context}"
        user_prompt += "\n\nGenerate action plan as JSON array only. IMPORTANT: NEVER use Google for searches - use DuckDuckGo or go directly to site."
        
        try:
            logger.info(f"Generating LLM plan for complex case: {user_command}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=Config.LLM_TEMPERATURE,
                max_tokens=Config.LLM_MAX_TOKENS,
            )
            
            # Extract response text
            response_text = response.choices[0].message.content.strip()
            
            # Parse JSON - handle potential markdown wrapping
            if response_text.startswith("```"):
                # Remove markdown code block if present
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            # Parse JSON array
            plan = json.loads(response_text)
            
            if not isinstance(plan, list):
                raise ValueError("Plan must be a JSON array")
            
            logger.info(f"Generated LLM plan with {len(plan)} steps")
            
            # Validate each action in plan
            for i, action_dict in enumerate(plan):
                if not isinstance(action_dict, dict):
                    raise ValueError(f"Step {i} is not a dict: {action_dict}")
                if "action" not in action_dict:
                    raise ValueError(f"Step {i} missing 'action' field")
                
                action_type = action_dict.get("action", "").lower()
                if action_type not in [t.value for t in ActionType]:
                    raise ValueError(f"Step {i} has invalid action: {action_type}")
            
            return plan
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan JSON: {e}")
            logger.error(f"Response was: {response_text if 'response_text' in locals() else 'N/A'}")
            raise ValueError(f"Invalid JSON from planner: {e}")
        
        except Exception as e:
            logger.error(f"LLM plan generation failed: {e}")
            raise
    
        
        return plan
    
    # Note: Old _generate_plan_with_llm is now _generate_plan_with_llm_fallback
    # This alias is kept for backward compatibility
    async def _generate_plan_with_llm(self, *args, **kwargs):
        """Deprecated: Use _generate_plan_with_llm_fallback instead."""
        return await self._generate_plan_with_llm_fallback(*args, **kwargs)
    
    def convert_plan_to_actions(self, plan: list[dict]) -> list[Action]:
        """
        Convert raw plan dictionaries to Action objects.
        
        Args:
            plan: List of action dictionaries from planner
            
        Returns:
            List of validated Action objects
            
        Raises:
            ValueError: If action data is invalid
        """
        actions = []
        
        for step in plan:
            try:
                # Map planner action names to ActionType enum (keep lowercase)
                action_type_str = step.get("action", "").lower()
                action_type = ActionType(action_type_str)
                
                # Create Action with validated parameters
                action = Action(
                    action_type=action_type,
                    selector=step.get("selector"),
                    value=step.get("value"),
                    direction=step.get("direction"),
                    key=step.get("key"),
                    reasoning=step.get("reasoning", ""),
                )
                
                actions.append(action)
                
            except (ValueError, KeyError) as e:
                logger.error(f"Failed to convert action: {step}, error: {e}")
                raise
        
        return actions
