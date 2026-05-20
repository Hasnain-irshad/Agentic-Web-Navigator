"""
Configuration settings for the Agentic Web Navigator.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration class."""
    
    # Groq LLM Settings
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    
    # Browser Settings
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    BROWSER_TIMEOUT: int = int(os.getenv("BROWSER_TIMEOUT", "30000"))  # milliseconds
    
    # Agent Settings
    MAX_STEPS: int = int(os.getenv("MAX_STEPS", "20"))
    OBSERVATION_MAX_ELEMENTS: int = int(os.getenv("OBSERVATION_MAX_ELEMENTS", "200"))
    
    # Humanization / anti-bot settings
    HUMANIZE_ENABLED: bool = os.getenv("HUMANIZE_ENABLED", "true").lower() == "true"
    HUMAN_MIN_DELAY_MS: int = int(os.getenv("HUMAN_MIN_DELAY_MS", "100"))
    HUMAN_MAX_DELAY_MS: int = int(os.getenv("HUMAN_MAX_DELAY_MS", "700"))
    TYPING_DELAY_MIN_MS: int = int(os.getenv("TYPING_DELAY_MIN_MS", "50"))
    TYPING_DELAY_MAX_MS: int = int(os.getenv("TYPING_DELAY_MAX_MS", "200"))
    TYPING_ERROR_RATE: float = float(os.getenv("TYPING_ERROR_RATE", "0.02"))  # probability of a typo per char
    MOUSE_MOVE_ENABLED: bool = os.getenv("MOUSE_MOVE_ENABLED", "true").lower() == "true"
    CLICK_JITTER_PX: int = int(os.getenv("CLICK_JITTER_PX", "3"))
    # Optional proxy rotation (comma-separated list of proxy servers)
    PROXY_SERVERS: list[str] = [p.strip() for p in os.getenv("PROXY_SERVERS", "").split(",") if p.strip()]
    # Slow down actions globally (milliseconds) to make behavior slower and more human-like
    SLOW_MO_MS: int = int(os.getenv("SLOW_MO_MS", "0"))
    # If enabled, force headful mode when HUMANIZE_ENABLED to reduce detection
    FORCE_HEADFUL_ON_HUMANIZE: bool = os.getenv("FORCE_HEADFUL_ON_HUMANIZE", "true").lower() == "true"

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY environment variable is required. "
                "Set it in .env file or export it."
            )
