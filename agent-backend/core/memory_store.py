"""
MemoryStore: Maintains action history and task context for LLM reasoning.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    from schemas import Action, ActionResult
    from core.observation_extractor import Observation
    from utils import get_logger
except ImportError:
    from ..schemas import Action, ActionResult
    from .observation_extractor import Observation
    from ..utils import get_logger


logger = get_logger(__name__)


@dataclass
class MemoryEntry:
    """Single entry in the action memory."""
    step: int
    action: Action
    result: ActionResult
    observation_summary: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step": self.step,
            "action": self.action.to_dict(),
            "result": self.result.to_dict(),
            "observation_summary": self.observation_summary,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def to_prompt_text(self) -> str:
        """Format for LLM prompt."""
        status = "✓" if self.result.success else "✗"
        return (
            f"Step {self.step} [{status}]: {self.action.action_type.value.upper()}"
            f" | {self.result.message}"
        )


@dataclass
class Context:
    """Context window for LLM reasoning."""
    goal: str
    current_observation: Observation
    history: list[MemoryEntry]
    step_count: int
    max_steps: int
    plan: dict = None  # {'goal': str, 'subgoals': list[str], 'current_subgoal_idx': int, 'completed': bool}

    def to_prompt_text(self) -> str:
        """
        Format context for LLM prompt, including plan/subgoals if present.
        """
        lines = [
            "=" * 50,
            "TASK GOAL:",
            self.goal,
            "=" * 50,
            "",
            f"Progress: Step {self.step_count}/{self.max_steps}",
            "",
        ]
        # Plan/subgoals
        if self.plan:
            lines.append("PLAN:")
            lines.append(f"  Goal: {self.plan.get('goal','')}")
            subgoals = self.plan.get('subgoals', [])
            idx = self.plan.get('current_subgoal_idx', 0)
            for i, sg in enumerate(subgoals):
                prefix = '→' if i == idx else ' '
                lines.append(f"  {prefix} Subgoal {i+1}: {sg}")
            lines.append(f"  Completed: {self.plan.get('completed', False)}")
            lines.append("")
        # Action history
        if self.history:
            lines.append("ACTION HISTORY:")
            for entry in self.history:
                lines.append(f"  {entry.to_prompt_text()}")
            lines.append("")
        # Current observation
        lines.append("CURRENT PAGE STATE:")
        lines.append(self.current_observation.to_prompt_text())
        return "\n".join(lines)


class MemoryStore:
    """
    Stores action history and provides context for LLM reasoning.
    
    Maintains a sliding window of recent actions with their results
    and observations to inform the agent's next decision.
    """
    
    def __init__(self, goal: str, max_steps: int, plan: dict = None) -> None:
        """
        Initialize the memory store.
        
        Args:
            goal: The user's task goal
            max_steps: Maximum steps allowed for the task
        """
        self._goal = goal
        self._max_steps = max_steps
        self._history: list[MemoryEntry] = []
        self._step_count = 0
        self._plan = plan or None
        logger.info(f"MemoryStore initialized with goal: {goal[:50]}...")
    
    @property
    def goal(self) -> str:
        """Get the task goal."""
        return self._goal
    
    @property
    def step_count(self) -> int:
        """Get current step count."""
        return self._step_count
    
    @property
    def max_steps(self) -> int:
        """Get maximum steps."""
        return self._max_steps
    
    def add_entry(
        self,
        action: Action,
        result: ActionResult,
        observation: Observation
    ) -> None:
        """
        Add a new action entry to memory.
        
        Args:
            action: The action that was executed
            result: The result of the action
            observation: The page observation after the action
        """
        self._step_count += 1
        
        entry = MemoryEntry(
            step=self._step_count,
            action=action,
            result=result,
            observation_summary=f"{observation.url} - {observation.title}",
        )
        
        self._history.append(entry)
        logger.debug(f"Added memory entry for step {self._step_count}")
    
    def get_context(
        self,
        current_observation: Observation,
        history_limit: int = 10
    ) -> Context:
        """
        Get context for LLM reasoning, including plan/subgoals if present.
        """
        # Get recent history (sliding window)
        recent_history = self._history[-history_limit:]
        return Context(
            goal=self._goal,
            current_observation=current_observation,
            history=recent_history,
            step_count=self._step_count,
            max_steps=self._max_steps,
            plan=self._plan,
        )

    @property
    def plan(self):
        return self._plan

    @plan.setter
    def plan(self, value):
        self._plan = value
    
    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of the task execution.
        
        Returns:
            Dictionary with task summary information
        """
        successful_steps = sum(1 for e in self._history if e.result.success)
        failed_steps = len(self._history) - successful_steps
        
        # Determine final status
        if self._history:
            last_action = self._history[-1].action
            if last_action.action_type.value == "done":
                status = "completed"
            elif failed_steps > successful_steps:
                status = "failed"
            else:
                status = "incomplete"
        else:
            status = "not_started"
        
        return {
            "goal": self._goal,
            "status": status,
            "total_steps": self._step_count,
            "max_steps": self._max_steps,
            "successful_actions": successful_steps,
            "failed_actions": failed_steps,
            "action_sequence": [
                {
                    "step": e.step,
                    "action": e.action.action_type.value,
                    "success": e.result.success,
                    "message": e.result.message,
                }
                for e in self._history
            ],
        }
    
    def clear(self) -> None:
        """Clear all memory entries."""
        self._history.clear()
        self._step_count = 0
        logger.info("Memory cleared")
    
    def is_at_limit(self) -> bool:
        """Check if step limit has been reached."""
        return self._step_count >= self._max_steps
