"""
Action schemas with strict validation.
Defines the atomic actions the agent can execute.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class ActionType(Enum):
    """Enumeration of valid browser actions."""
    GOTO = "goto"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    BACK = "back"
    FORWARD = "forward"
    RELOAD = "reload"
    CREATE_TAB = "create_tab"         # open a blank (or given-URL) tab
    NEW_TAB = "new_tab"
    CLOSE_TAB = "close_tab"
    PRESS_KEY = "press_key"           # For pressing keyboard keys like Enter
    # Shell-level actions — drive the browser chrome (URL/search bar),
    # not the webview DOM. Behaves like a human typing into the address bar.
    BROWSER_SEARCH = "browser_search"     # type verbatim into address bar + submit
    BROWSER_NAVIGATE = "browser_navigate" # direct URL load via shell (address bar)
    IDLE = "idle"                     # no-op; signals the agent has nothing to do
    DONE = "done"



@dataclass
class Action:
    """
    Represents a single atomic browser action.
    
    Attributes:
        action_type: The type of action to perform
        selector: CSS selector or text for element targeting (for click/type)
        value: Input value (for type action) or URL (for goto)
        direction: Scroll direction ('up' or 'down')
        reasoning: LLM's reasoning for choosing this action
    """
    action_type: ActionType
    selector: Optional[str] = None
    value: Optional[str] = None
    direction: Optional[str] = None
    key: Optional[str] = None  # For press_key action (e.g., "Enter", "Escape")
    element_index: Optional[int] = None  # 1-based index into observation element list
    reasoning: str = ""

    
    def __post_init__(self) -> None:
        """Validate action parameters after initialization."""
        self._validate()
    
    def _validate(self) -> None:
        """
        Validate action parameters based on action type.
        
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        if self.action_type == ActionType.GOTO:
            if not self.value:
                raise ValueError("GOTO action requires 'value' (URL)")
            if not self.value.startswith(("http://", "https://")):
                self.value = f"https://{self.value}"
                
        elif self.action_type == ActionType.CLICK:
            if not self.selector and self.element_index is None:
                raise ValueError("CLICK action requires 'selector' or 'element_index'")
                
        elif self.action_type == ActionType.TYPE:
            if not self.selector and self.element_index is None:
                raise ValueError("TYPE action requires 'selector' or 'element_index'")
            if self.value is None:
                raise ValueError("TYPE action requires 'value'")
                
        elif self.action_type == ActionType.SCROLL:
            if self.direction not in ("up", "down"):
                raise ValueError("SCROLL action requires 'direction' ('up' or 'down')")
        
        elif self.action_type == ActionType.PRESS_KEY:
            if not self.key:
                self.key = "Enter"  # Default to Enter key

    
    def to_dict(self) -> dict[str, Any]:
        """Convert action to dictionary representation."""
        return {
            "action_type": self.action_type.value,
            "selector": self.selector,
            "value": self.value,
            "direction": self.direction,
            "key": self.key,
            "element_index": self.element_index,
            "reasoning": self.reasoning,
        }

    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        """
        Create an Action from a dictionary.
        
        Args:
            data: Dictionary containing action parameters
            
        Returns:
            Validated Action instance
            
        Raises:
            ValueError: If action_type is invalid or parameters are missing
        """
        action_type_str = data.get("action_type", data.get("action", "")).lower()
        
        # New World Model prompt uses wait instead of done when elements aren't found
        if action_type_str == "wait":
            action_type_str = "done"

        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            valid_types = [t.value for t in ActionType]
            raise ValueError(
                f"Invalid action_type '{action_type_str}'. "
                f"Valid types: {valid_types}"
            )
        
        # Parse element_index — accept int or string
        raw_idx = data.get("element_index")
        element_index = None
        if raw_idx is not None:
            try:
                element_index = int(raw_idx)
            except (ValueError, TypeError):
                element_index = None

        return cls(
            action_type=action_type,
            selector=data.get("selector", data.get("target")),
            value=data.get("value"),
            direction=data.get("direction"),
            key=data.get("key"),
            element_index=element_index,
            reasoning=data.get("reasoning", ""),
        )



@dataclass
class ActionResult:
    """
    Result of executing an action.
    
    Attributes:
        success: Whether the action completed successfully
        message: Descriptive result or error message
        data: Optional additional data from the action
    """
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
        }
