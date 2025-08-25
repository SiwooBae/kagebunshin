"""
Agent configuration management for the simplified Agent API.
Handles parameter validation, defaults, and merging with settings.py.
"""

from typing import Any, Optional, Dict
from dataclasses import dataclass, field
import os

from .settings import (
    LLM_MODEL,
    LLM_PROVIDER, 
    LLM_REASONING_EFFORT,
    LLM_TEMPERATURE,
    SUMMARIZER_MODEL,
    SUMMARIZER_PROVIDER,
    SUMMARIZER_REASONING_EFFORT,
    ENABLE_SUMMARIZATION,
    BROWSER_EXECUTABLE_PATH,
    USER_DATA_DIR,
    ACTUAL_VIEWPORT_WIDTH,
    ACTUAL_VIEWPORT_HEIGHT,
    RECURSION_LIMIT,
    MAX_ITERATIONS,
    TIMEOUT,
    GROUPCHAT_ROOM
)


@dataclass
class AgentConfig:
    """
    Configuration container for Agent with validation and defaults.
    
    This class handles all configuration parameters for the simplified Agent API,
    providing type safety, validation, and sensible defaults.
    """
    
    # Task (required)
    task: str
    
    # LLM Configuration
    llm: Optional[Any] = None
    llm_model: str = LLM_MODEL
    llm_provider: str = LLM_PROVIDER
    llm_reasoning_effort: str = LLM_REASONING_EFFORT
    llm_temperature: float = LLM_TEMPERATURE
    
    # Summarizer Configuration
    summarizer_model: str = SUMMARIZER_MODEL
    summarizer_provider: str = SUMMARIZER_PROVIDER
    summarizer_reasoning_effort: str = SUMMARIZER_REASONING_EFFORT
    enable_summarization: bool = ENABLE_SUMMARIZATION
    
    # Browser Configuration
    headless: bool = False
    browser_executable_path: Optional[str] = BROWSER_EXECUTABLE_PATH
    user_data_dir: Optional[str] = USER_DATA_DIR
    viewport_width: int = ACTUAL_VIEWPORT_WIDTH
    viewport_height: int = ACTUAL_VIEWPORT_HEIGHT
    
    # Workflow Configuration
    recursion_limit: int = RECURSION_LIMIT
    max_iterations: int = MAX_ITERATIONS
    timeout: int = TIMEOUT
    
    # Multi-agent Configuration
    group_room: Optional[str] = GROUPCHAT_ROOM
    username: Optional[str] = None
    
    def __post_init__(self):
        """Validate configuration parameters after initialization."""
        self._validate_task()
        self._validate_llm_config()
        self._validate_browser_config()
        self._validate_workflow_config()
    
    def _validate_task(self):
        """Validate task parameter."""
        if not self.task or not isinstance(self.task, str):
            raise ValueError("Task must be a non-empty string")
        if len(self.task.strip()) == 0:
            raise ValueError("Task cannot be empty or only whitespace")
    
    def _validate_llm_config(self):
        """Validate LLM configuration parameters."""
        valid_providers = ["openai", "anthropic"]
        valid_reasoning_efforts = ["minimal", "low", "medium", "high"]
        
        if self.llm_provider not in valid_providers:
            raise ValueError(f"llm_provider must be one of {valid_providers}")
        
        if self.llm_reasoning_effort not in valid_reasoning_efforts:
            raise ValueError(f"llm_reasoning_effort must be one of {valid_reasoning_efforts}")
        
        if self.summarizer_provider not in valid_providers:
            raise ValueError(f"summarizer_provider must be one of {valid_providers}")
            
        if self.summarizer_reasoning_effort not in valid_reasoning_efforts:
            raise ValueError(f"summarizer_reasoning_effort must be one of {valid_reasoning_efforts}")
        
        if not isinstance(self.llm_temperature, (int, float)) or self.llm_temperature < 0:
            raise ValueError("llm_temperature must be a non-negative number")
    
    def _validate_browser_config(self):
        """Validate browser configuration parameters."""
        if not isinstance(self.headless, bool):
            raise ValueError("headless must be a boolean")
        
        if not isinstance(self.viewport_width, int) or self.viewport_width <= 0:
            raise ValueError("viewport_width must be a positive integer")
            
        if not isinstance(self.viewport_height, int) or self.viewport_height <= 0:
            raise ValueError("viewport_height must be a positive integer")
        
        if self.browser_executable_path is not None and not isinstance(self.browser_executable_path, str):
            raise ValueError("browser_executable_path must be None or a string")
            
        if self.user_data_dir is not None and not isinstance(self.user_data_dir, str):
            raise ValueError("user_data_dir must be None or a string")
    
    def _validate_workflow_config(self):
        """Validate workflow configuration parameters."""
        if not isinstance(self.recursion_limit, int) or self.recursion_limit <= 0:
            raise ValueError("recursion_limit must be a positive integer")
            
        if not isinstance(self.max_iterations, int) or self.max_iterations <= 0:
            raise ValueError("max_iterations must be a positive integer")
            
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            raise ValueError("timeout must be a positive integer")
    
    def to_kagebunshin_kwargs(self) -> Dict[str, Any]:
        """
        Convert config to kwargs dict for KageBunshinAgent.create().
        
        Returns:
            Dict of parameters that can be passed to KageBunshinAgent.create()
        """
        return {
            "enable_summarization": self.enable_summarization,
            "group_room": self.group_room,
            "username": self.username,
            "llm": self.llm,
            "llm_model": self.llm_model,
            "llm_provider": self.llm_provider,
            "llm_reasoning_effort": self.llm_reasoning_effort,
            "llm_temperature": self.llm_temperature,
            "summarizer_model": self.summarizer_model,
            "summarizer_provider": self.summarizer_provider,
            "summarizer_reasoning_effort": self.summarizer_reasoning_effort,
            "recursion_limit": self.recursion_limit,
        }
    
    def get_browser_launch_options(self) -> Dict[str, Any]:
        """
        Get browser launch options from config.
        
        Returns:
            Dict of browser launch options for Playwright
        """
        from ..automation.fingerprinting import get_stealth_browser_args
        
        launch_options = {
            "headless": self.headless,
            "args": get_stealth_browser_args(),
            "ignore_default_args": ["--enable-automation"],
        }
        
        if self.browser_executable_path:
            launch_options["executable_path"] = self.browser_executable_path
        else:
            launch_options["channel"] = "chrome"
        
        return launch_options
    
    def get_browser_context_options(self) -> Dict[str, Any]:
        """
        Get browser context options from config.
        
        Returns:
            Dict of browser context options for Playwright
        """
        from ..config.settings import DEFAULT_PERMISSIONS
        
        return {
            "permissions": DEFAULT_PERMISSIONS,
            "viewport": {
                "width": self.viewport_width,
                "height": self.viewport_height
            }
        }

    @classmethod
    def from_kwargs(cls, **kwargs) -> 'AgentConfig':
        """
        Create AgentConfig from keyword arguments, filtering out unknown parameters.
        
        Args:
            **kwargs: Configuration parameters
            
        Returns:
            AgentConfig instance with valid parameters
            
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        # Get field names from the dataclass
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        
        # Filter kwargs to only include valid field names
        valid_kwargs = {k: v for k, v in kwargs.items() if k in field_names}
        
        # Ensure task is provided
        if 'task' not in valid_kwargs:
            raise ValueError("task parameter is required")
        
        return cls(**valid_kwargs)