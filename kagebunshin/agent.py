"""
Simplified Agent API for KageBunshin.
Provides a comprehensive, user-friendly interface that handles all configuration and browser lifecycle management.
"""

import os
from typing import Any, Optional
import logging
from playwright.async_api import async_playwright

from .core.agent import KageBunshinAgent
from .tools.delegation import get_additional_tools
from .config.agent_config import AgentConfig
from .config.settings import GROUPCHAT_ROOM
from .automation.fingerprinting import apply_fingerprint_profile_to_context
from .utils import generate_agent_name

logger = logging.getLogger(__name__)


class Agent:
    """
    Simplified agent interface for KageBunshin web automation.
    
    Provides a comprehensive, easy-to-use API, with full control
    over all configuration parameters without needing to edit settings files.
    
    Example:
        # Simple usage
        agent = Agent(task="Find the repo stars of Kagebunshin")
        
        # With custom LLM
        from langchain.chat_models import ChatOpenAI
        agent = Agent(
            task="Find repo stars",
            llm=ChatOpenAI(model="gpt-4o-mini", temperature=0)
        )
        
        # Full customization
        agent = Agent(
            task="Complex research task",
            llm_model="gpt-5",
            llm_reasoning_effort="high",
            viewport_width=1920,
            viewport_height=1080,
            recursion_limit=200,
            enable_summarization=True,
            headless=True
        )
    """
    
    def __init__(
        self,
        task: str,
        llm: Optional[Any] = None,
        
        # LLM Configuration
        llm_model: str = "gpt-5-mini",
        llm_provider: str = "openai", 
        llm_reasoning_effort: str = "low",
        llm_temperature: float = 1.0,
        
        # Summarizer Configuration  
        summarizer_model: str = "gpt-5-nano",
        summarizer_provider: str = "openai",
        summarizer_reasoning_effort: str = "low",
        enable_summarization: bool = False,
        
        # Browser Configuration
        headless: bool = False,
        browser_executable_path: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        viewport_width: int = 1280,
        viewport_height: int = 1280,
        
        # Workflow Configuration
        recursion_limit: int = 150,
        max_iterations: int = 100,
        timeout: int = 60,
        
        # Multi-agent Configuration
        group_room: Optional[str] = GROUPCHAT_ROOM,
        username: Optional[str] = None,
    ):
        """
        Initialize the Agent with comprehensive configuration options.
        
        Args:
            task: The task description for the agent to perform
            llm: Pre-configured language model (optional, will auto-configure if not provided)
            
            # LLM Configuration
            llm_model: Model name (e.g., "gpt-5-mini", "gpt-4o-mini")
            llm_provider: Provider ("openai" or "anthropic")
            llm_reasoning_effort: Reasoning effort ("minimal", "low", "medium", "high")
            llm_temperature: LLM temperature (0.0-2.0)
            
            # Summarizer Configuration
            summarizer_model: Model for action summarization
            summarizer_provider: Provider for summarizer
            summarizer_reasoning_effort: Reasoning effort for summarizer
            enable_summarization: Enable action summarization
            
            # Browser Configuration
            headless: Run browser in headless mode
            browser_executable_path: Path to browser executable
            user_data_dir: Browser profile directory
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            
            # Workflow Configuration
            recursion_limit: Maximum recursion depth
            max_iterations: Maximum iterations per task
            timeout: Timeout per operation (seconds)
            
            # Multi-agent Configuration
            group_room: Group chat room for agent coordination
            username: Agent name (auto-generated if not provided)
        """
        # Create and validate configuration
        self.config = AgentConfig.from_kwargs(
            task=task,
            llm=llm,
            llm_model=llm_model,
            llm_provider=llm_provider,
            llm_reasoning_effort=llm_reasoning_effort,
            llm_temperature=llm_temperature,
            summarizer_model=summarizer_model,
            summarizer_provider=summarizer_provider,
            summarizer_reasoning_effort=summarizer_reasoning_effort,
            enable_summarization=enable_summarization,
            headless=headless,
            browser_executable_path=browser_executable_path,
            user_data_dir=user_data_dir,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            recursion_limit=recursion_limit,
            max_iterations=max_iterations,
            timeout=timeout,
            group_room=group_room,
            username=username
        )
    
    async def run(self) -> str:
        """
        Run the agent to complete the specified task.
        
        This method handles all browser lifecycle management, including:
        - Launching the browser with stealth settings based on config
        - Creating browser context with fingerprint protection
        - Initializing the KageBunshinAgent with all configuration
        - Running the task
        - Cleaning up resources
        
        Returns:
            The result of the task execution
        """
        logger.info(f"Starting agent with task: {self.config.task}")
        logger.info(f"Configuration: LLM={self.config.llm_model}, Provider={self.config.llm_provider}, Reasoning={self.config.llm_reasoning_effort}")
        
        async with async_playwright() as p:
            # Get browser launch options from config
            launch_options = self.config.get_browser_launch_options()
            
            # Launch browser with or without persistent context
            if self.config.user_data_dir:
                logger.info(f"Using persistent context from: {self.config.user_data_dir}")
                ctx_dir = os.path.expanduser(self.config.user_data_dir)
                
                # For persistent context, need to merge context options into launch options
                context_options = self.config.get_browser_context_options()
                launch_options.update(context_options)
                
                context = await p.chromium.launch_persistent_context(
                    ctx_dir,
                    **launch_options,
                )
                browser = None  # No browser object when using persistent context
            else:
                browser = await p.chromium.launch(**launch_options)
                context_options = self.config.get_browser_context_options()
                context = await browser.new_context(**context_options)
            
            try:
                # Apply fingerprint protection
                profile = await apply_fingerprint_profile_to_context(context)
                try:
                    await context.add_init_script(
                        f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{profile['user_agent']}' }});"
                    )
                except Exception:
                    pass
                
                # Auto-generate username if not provided
                username = self.config.username or generate_agent_name()
                
                # Get delegation tools for agent coordination
                extra_tools = get_additional_tools(context, username=username, group_room=self.config.group_room)
                
                # Create KageBunshin agent with full configuration
                kagebunshin_kwargs = self.config.to_kagebunshin_kwargs()
                kagebunshin_kwargs.update({
                    "additional_tools": extra_tools,
                    "username": username,
                })
                
                agent = await KageBunshinAgent.create(context, **kagebunshin_kwargs)
                
                logger.info(f"KageBunshin agent created successfully with username: {username}")
                
                # Execute the task
                result = await agent.ainvoke(self.config.task)
                return result
                
            finally:
                # Clean up resources
                if browser:
                    await browser.close()
                else:
                    # For persistent context, close the context
                    await context.close()