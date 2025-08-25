"""
Simplified Agent API for KageBunshin, similar to browser-use.
Provides a clean, user-friendly interface that handles browser lifecycle management.
"""

import os
from typing import Any, Optional
import logging
from playwright.async_api import async_playwright

from .core.agent import KageBunshinAgent
from .tools.delegation import get_additional_tools
from .config.settings import (
    BROWSER_EXECUTABLE_PATH,
    USER_DATA_DIR,
    DEFAULT_PERMISSIONS,
    ACTUAL_VIEWPORT_WIDTH,
    ACTUAL_VIEWPORT_HEIGHT,
    GROUPCHAT_ROOM
)
from .automation.fingerprinting import get_stealth_browser_args, apply_fingerprint_profile_to_context
from .utils import generate_agent_name

logger = logging.getLogger(__name__)


class Agent:
    """
    Simplified agent interface for KageBunshin web automation.
    
    Provides an easy-to-use API similar to browser-use, handling all browser lifecycle
    management automatically.
    
    Example:
        from kagebunshin import Agent
        from langchain.chat_models import ChatOpenAI
        
        async def main():
            agent = Agent(
                task="Find the number of stars of the browser-use repo",
                llm=ChatOpenAI(model="gpt-4o-mini"),
            )
            result = await agent.run()
            print(result)
    """
    
    def __init__(
        self,
        task: str,
        llm: Any,
        headless: bool = False,
        enable_summarization: bool = False,
        group_room: Optional[str] = None,
        username: Optional[str] = None,
        browser_executable_path: Optional[str] = None,
        user_data_dir: Optional[str] = None
    ):
        """
        Initialize the simplified Agent.
        
        Args:
            task: The task description for the agent to perform
            llm: The language model to use (from langchain)
            headless: Whether to run browser in headless mode
            enable_summarization: Whether to enable action summarization
            group_room: Optional group chat room name for multi-agent coordination
            username: Optional agent name (auto-generated if not provided)
            browser_executable_path: Optional path to browser executable
            user_data_dir: Optional browser user data directory
        """
        self.task = task
        self.llm = llm
        self.headless = headless
        self.enable_summarization = enable_summarization
        self.group_room = group_room or GROUPCHAT_ROOM
        self.username = username or generate_agent_name()
        self.browser_executable_path = browser_executable_path or BROWSER_EXECUTABLE_PATH
        self.user_data_dir = user_data_dir or USER_DATA_DIR
    
    async def run(self) -> str:
        """
        Run the agent to complete the specified task.
        
        This method handles all browser lifecycle management, including:
        - Launching the browser with stealth settings
        - Creating browser context with fingerprint protection
        - Initializing the KageBunshinAgent
        - Running the task
        - Cleaning up resources
        
        Returns:
            The result of the task execution
        """
        logger.info(f"Starting agent with task: {self.task}")
        
        async with async_playwright() as p:
            # Configure browser launch options
            launch_options = {
                "headless": self.headless,
                "args": get_stealth_browser_args(),
                "ignore_default_args": ["--enable-automation"],
            }
            
            if self.browser_executable_path:
                launch_options["executable_path"] = self.browser_executable_path
            else:
                launch_options["channel"] = "chrome"
            
            # Launch browser with or without persistent context
            if self.user_data_dir:
                logger.info(f"Using persistent context from: {self.user_data_dir}")
                ctx_dir = os.path.expanduser(self.user_data_dir)
                context = await p.chromium.launch_persistent_context(
                    ctx_dir,
                    **launch_options,
                    permissions=DEFAULT_PERMISSIONS,
                )
                browser = None  # No browser object when using persistent context
            else:
                browser = await p.chromium.launch(**launch_options)
                context = await browser.new_context(
                    permissions=DEFAULT_PERMISSIONS,
                    viewport={'width': ACTUAL_VIEWPORT_WIDTH, 'height': ACTUAL_VIEWPORT_HEIGHT}
                )
            
            try:
                # Apply fingerprint protection
                profile = await apply_fingerprint_profile_to_context(context)
                try:
                    await context.add_init_script(
                        f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{profile['user_agent']}' }});"
                    )
                except Exception:
                    pass
                
                # Get delegation tools for agent coordination
                extra_tools = get_additional_tools(context, username=self.username, group_room=self.group_room)
                
                # Create KageBunshin agent
                agent = await KageBunshinAgent.create(
                    context,
                    additional_tools=extra_tools,
                    group_room=self.group_room,
                    username=self.username,
                    enable_summarization=self.enable_summarization,
                )
                
                logger.info("KageBunshin agent created successfully")
                
                # Execute the task
                result = await agent.ainvoke(self.task)
                return result
                
            finally:
                # Clean up resources
                if browser:
                    await browser.close()
                else:
                    # For persistent context, close the context
                    await context.close()