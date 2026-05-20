"""
Agentic Web Navigator - Main entry point.
Orchestrates the observe → reason → execute loop.
"""

import argparse
import asyncio
import json
from typing import Optional

from core import (
    BrowserController,
    ObservationExtractor,
    MemoryStore,
    AgentReasoner,
)
from core.agent_reasoner import MockReasoner
from core.stop_conditions import should_stop, CompletionDetector, RepetitionDetector
from schemas import ActionType
from config import Config
from utils import get_logger


logger = get_logger(__name__)


class WebNavigatorAgent:
    """
    Main agent orchestrator.
    
    Coordinates the browser, observation extractor, memory, and reasoner
    to complete web tasks autonomously.
    """
    
    def __init__(
        self,
        goal: str,
        max_steps: Optional[int] = None,
        headless: Optional[bool] = None,
        use_mock: bool = False,
    ) -> None:
        """
        Initialize the web navigator agent.
        
        Args:
            goal: Natural language description of the task
            max_steps: Maximum steps to attempt. Defaults to Config.MAX_STEPS.
            headless: Browser mode. Defaults to Config.HEADLESS.
            use_mock: If True, use mock reasoner instead of LLM.
        """
        self._goal = goal
        self._max_steps = max_steps or Config.MAX_STEPS
        self._headless = headless if headless is not None else Config.HEADLESS
        self._use_mock = use_mock
        
        self._browser: Optional[BrowserController] = None
        self._extractor = ObservationExtractor()
        self._memory: Optional[MemoryStore] = None
        self._reasoner = None
        
    async def run(self) -> dict:
        """
        Execute the agent loop.
        
        Returns:
            Task summary dictionary with results
        """
        logger.info(f"Starting agent with goal: {self._goal}")
        logger.info(f"Max steps: {self._max_steps}, Headless: {self._headless}")
        
        # Initialize components
        self._memory = MemoryStore(self._goal, self._max_steps)
        
        if self._use_mock:
            self._reasoner = MockReasoner()
        else:
            try:
                Config.validate()
                self._reasoner = AgentReasoner()
            except ValueError as e:
                logger.error(f"Configuration error: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "goal": self._goal,
                }
        
        try:
            async with BrowserController(headless=self._headless) as browser:
                self._browser = browser
                return await self._execute_loop()
                
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "goal": self._goal,
                "steps_completed": self._memory.step_count if self._memory else 0,
            }
    
    async def _execute_loop(self) -> dict:
        """
        Main observe → reason → execute loop.
        
        Returns:
            Task summary dictionary
        """
        logger.info("=" * 50)
        logger.info("STARTING AGENT LOOP")
        logger.info("=" * 50)
        
        # Initialize generic stop condition detectors
        completion_detector = CompletionDetector()
        repetition_detector = RepetitionDetector()
        
        last_action = None
        last_result = None
        
        while not self._memory.is_at_limit():
            try:
                # 1. OBSERVE - Get current page state (REAL DOM elements)
                page = await self._browser.get_current_page()
                observation = await self._extractor.extract(page)
                
                # Cache observation on browser for element_index resolution
                self._browser.set_observation(observation)
                
                logger.info(f"Observed: {observation.url} - {observation.title} ({len(observation.elements)} elements)")
                
                # 2. REASON - Decide next action (LLM sees numbered elements)
                context = self._memory.get_context(observation)
                action = await self._reasoner.decide_action(context)
                
                logger.info(f"Reasoning: {action.reasoning[:100]}...")
                logger.info(f"Action: {action.action_type.value} (element_index={action.element_index})")
                
                # 3. EXECUTE - Perform the action (element_index → real CSS selector)
                result = await self._browser.execute_action(action)
                
                logger.info(f"Result: {'✓' if result.success else '✗'} {result.message}")
                
                # 4. STORE - Add to memory
                # Get observation after action for memory
                new_observation = await self._extractor.extract(
                    await self._browser.get_current_page()
                )
                self._memory.add_entry(action, result, new_observation)
                last_action = action
                last_result = result
                
                # 5. GENERIC STOP CONDITION DETECTION
                # Check for completion or repetition without relying solely on LLM
                is_stopping, stop_msg = should_stop(
                    goal=self._goal,
                    observation=new_observation,
                    memory=self._memory,
                    last_action=action,
                    last_result=result,
                    completion_detector=completion_detector,
                    repetition_detector=repetition_detector,
                )
                
                if is_stopping:
                    logger.info(f"Generic stop condition triggered: {stop_msg}")
                    break
                
                # 6. CHECK EXPLICIT TERMINATION
                # If LLM explicitly returns DONE, stop immediately
                if action.action_type == ActionType.DONE:
                    logger.info("=" * 50)
                    logger.info("TASK COMPLETED")
                    logger.info("=" * 50)
                    break
                
                # Human-like delay between actions (randomized 1-3 seconds)
                import random
                await asyncio.sleep(random.uniform(1.0, 3.0))
                
            except Exception as e:
                logger.error(f"Loop iteration error: {e}")
                # Continue to next iteration unless critical
                if "Browser" in str(e) or "playwright" in str(e).lower():
                    break
        
        # Generate and return summary
        summary = self._memory.get_summary()
        self._print_summary(summary)
        return summary
    
    def _print_summary(self, summary: dict) -> None:
        """Print task summary to console."""
        logger.info("")
        logger.info("=" * 50)
        logger.info("TASK SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Goal: {summary['goal']}")
        logger.info(f"Status: {summary['status'].upper()}")
        logger.info(f"Steps: {summary['total_steps']}/{summary['max_steps']}")
        logger.info(f"Successful: {summary['successful_actions']}")
        logger.info(f"Failed: {summary['failed_actions']}")
        logger.info("")
        logger.info("Action Sequence:")
        for step in summary['action_sequence']:
            status = "✓" if step['success'] else "✗"
            logger.info(f"  {step['step']}. [{status}] {step['action']}: {step['message'][:60]}")
        logger.info("=" * 50)


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Agentic Web Navigator - Autonomous web task execution"
    )
    parser.add_argument(
        "--goal",
        "-g",
        type=str,
        required=False,
        help="Natural language description of the web task"
    )
    parser.add_argument(
        "--max-steps",
        "-s",
        type=int,
        default=None,
        help=f"Maximum steps (default: {Config.MAX_STEPS})"
    )
    parser.add_argument(
        "--visible",
        "-v",
        action="store_true",
        help="Run browser in visible mode (not headless)"
    )
    parser.add_argument(
        "--mock",
        "-m",
        action="store_true",
        help="Use mock reasoner (no API calls, for testing)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file for JSON summary"
    )
    
    args = parser.parse_args()

    # Interactive mode if no goal provided
    if not args.goal:
        print("\n🤖 Agentic Web Navigator")
        print("========================")
        try:
            while not args.goal:
                args.goal = input("Enter the web task goal: ").strip()
                if not args.goal:
                    print("Goal cannot be empty.")
        except KeyboardInterrupt:
            print("\nExiting...")
            return

    
    # Determine headless mode
    headless = not args.visible
    
    # Create and run agent
    agent = WebNavigatorAgent(
        goal=args.goal,
        max_steps=args.max_steps,
        headless=headless,
        use_mock=args.mock,
    )
    
    summary = await agent.run()
    
    # Output to file if specified
    if args.output:
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Summary saved to: {args.output}")
    
    return summary


if __name__ == "__main__":
    asyncio.run(main())
