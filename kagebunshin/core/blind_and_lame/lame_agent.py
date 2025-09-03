"""
The Lame Agent - Has eyes and legs but limited reasoning.

This agent can see the web page and interact with it using browser tools,
but relies on the Blind Agent for high-level planning and strategy.
"""

import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Dict

from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage, ToolMessage
from langchain.chat_models.base import init_chat_model
from langgraph.prebuilt import ToolNode, create_react_agent
from playwright.async_api import BrowserContext

from ..state_manager import KageBunshinStateManager
from ..state import Annotation
from ...utils import (
    build_page_context,
    normalize_chat_content
)

logger = logging.getLogger(__name__)


class LameAgent:
    """
    The Lame Agent - can see and interact with web pages but has limited reasoning.
    
    This agent:
    - Owns the KageBunshinStateManager for browser control
    - Uses tool binding to execute browser actions via LLM
    - Provides act() tool interface for the Blind Agent
    - Describes outcomes in natural language
    """
    
    def __init__(self, context: BrowserContext):
        self.context = context
        
        # Load prompts from files
        self.prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        
        with open(self.prompts_dir / "lame_agent_system_prompt.md", "r") as f:
            self.system_prompt = f.read()
        
        # This will be set in async create() method
        self.state_manager: Optional[KageBunshinStateManager] = None
        self.browser_tools: List[Any] = []
        self.llm = None
        self.llm_with_tools = None
        self.tool_node: Optional[ToolNode] = None
        
    @classmethod
    async def create(cls, context: BrowserContext) -> "LameAgent":
        """Async factory method to create a fully initialized LameAgent."""
        instance = cls(context)
        
        # Initialize state manager
        instance.state_manager = await KageBunshinStateManager.create(context)
        
        # Get browser tools from state manager
        instance.browser_tools = instance.state_manager.get_tools_for_llm()
        
        # Import configuration here to avoid circular imports
        from ...config.settings import LAME_MODEL, LAME_PROVIDER, LAME_TEMPERATURE
        
        # Initialize LLM
        instance.llm = init_chat_model(
            model=LAME_MODEL,
            model_provider=LAME_PROVIDER,
            temperature=LAME_TEMPERATURE,
            reasoning=(
                    {"effort": "minimal"} if "gpt-5" in LAME_MODEL else None
                ),
        )
        
        # Bind tools to LLM
        instance.llm_with_tools = instance.llm.bind_tools(instance.browser_tools, tool_choice="required")
        
        # Create tool node for execution
        instance.tool_node = ToolNode(instance.browser_tools)
        
        logger.info(f"LameAgent initialized with {len(instance.browser_tools)} browser tools")
        return instance
    
    async def execute_command(self, command: str) -> str:
        """
        Execute a natural language command in two passes.

        Pass 1: [system prompt, command, current state] -> tool call
        Pass 2: [system prompt, command, current state, tool call, tool result, changed state]
                -> ALFWORLD-like natural language description

        Args:
            command: Natural language command to execute (e.g., "Click the search button")

        Returns:
            Natural language description of what happened and current state.
        """
        if not self.state_manager or not self.llm_with_tools:
            return "Error: LameAgent not properly initialized. Use LameAgent.create() method."

        try:
            # ----- PASS 1: Propose tool call given current state -----
            before_page_data = await self.state_manager.get_current_page_data()

            # Build messages using existing context builder patterns
            before_context_messages = await self._build_page_context(before_page_data, HumanMessage)
            messages: List[BaseMessage] = [SystemMessage(content=self.system_prompt)]
            messages.extend(before_context_messages)
            messages.append(HumanMessage(content=f"Command: {command}"))

            # LLM proposes tool call(s)
            response = await self.llm_with_tools.ainvoke(messages)

            # If no tool calls were proposed, return the AI's explanation
            if not getattr(response, "tool_calls", None):
                return normalize_chat_content(response.content) if getattr(response, "content", None) else "No action taken."

            # ----- Execute tools -----
            tool_state = {"messages": messages + [response]}
            tool_exec_result = await self.tool_node.ainvoke(tool_state)

            # Collect ToolMessages and normalize outputs
            tool_messages = tool_exec_result.get("messages", [])
            tool_outputs: List[str] = []
            for msg in tool_messages:
                if isinstance(msg, ToolMessage):
                    tool_outputs.append(normalize_chat_content(msg.content))

            # ----- PASS 2: Summarize using before/after contexts and tool results -----
            after_page_data = await self.state_manager.get_current_page_data()
            after_context_messages = await self._build_page_context(after_page_data, HumanMessage)

            # Load the detailed explainer prompt for rich, actionable narration
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "config",
                "prompts",
                "lame_explainer.md",
            )
            with open(prompt_path, "r") as f:
                prompt_content = f.read()

            # Build summarization prompt messages mirroring the summarizer's approach
            summary_prompt_messages: List[BaseMessage] = [
                SystemMessage(content=prompt_content),
                HumanMessage(content=f"User command (as given to the Lame Agent):\n{command}"),
                HumanMessage(content="Here is the state of the page before the action:"),
            ]
            summary_prompt_messages.extend(before_context_messages)

            # Compose action + result strings from the proposed tool calls and tool outputs
            try:
                tool_calls_str = ", ".join(
                    [
                        f"{tc['name']}({tc.get('args', {})})"
                        if isinstance(tc, dict)
                        else f"{getattr(tc, 'name', 'tool')}({getattr(tc, 'args', {})})"
                        for tc in getattr(response, "tool_calls", []) or []
                    ]
                )
            except Exception:
                tool_calls_str = ""

            tool_results_str = ", ".join(tool_outputs) if tool_outputs else ""

            action_text = (
                f"The action taken was: {tool_calls_str}\n\n"
                f"The result of the action was: {tool_results_str}\n\n"
                "Here is the state of the page after the action: "
            )
            summary_prompt_messages.append(HumanMessage(content=action_text))
            summary_prompt_messages.extend(after_context_messages)

        
            # Use base LLM (no tools) to produce ALFWORLD-like outcome description
            summary_response = await self.llm.ainvoke(summary_prompt_messages)
            return normalize_chat_content(getattr(summary_response, "content", "")).strip() or (
                tool_outputs[0] if tool_outputs else "Action executed.")

        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}")
            return f"Error executing command: {str(e)}"
    
    def get_act_tool_for_blind(self):
        """
        Returns the act() tool that the Blind Agent will use.
        Similar pattern to state_manager.get_tools_for_llm()
        """
        @tool
        async def act(command: str) -> str:
            """
            Execute a natural language browser command through the Lame agent.
            
            This is the primary interface for the Blind agent to control the browser.
            The Lame agent will interpret the command, execute appropriate browser actions,
            and return a description of what happened.
            
            Args:
                command (str): Natural language command to execute
                
            Examples:
                - "Navigate to https://example.com"
                - "Click the blue search button"  
                - "Type 'machine learning' in the search field"
                - "Scroll down to see more results"
                - "Click the first search result"
                - "Extract the main content from this page"
                
            Returns:
                str: Natural language description of what happened and current state
            """
            return await self.execute_command(command)
        
        return act
    
    async def _build_page_context(
        self,
        page_data: Annotation,
        message_type: type = SystemMessage
    ) -> List[BaseMessage]:
        """Delegate to shared page context builder."""
        tabs = await self.state_manager.get_tabs()
        current_tab_index = await self.state_manager.get_current_tab_index()
        current_url = await self.get_current_url()
        return build_page_context(
            page_data=page_data,
            message_type=message_type,
            current_url=current_url,
            tabs=tabs,
            current_tab_index=current_tab_index,
        )

    async def get_current_url(self) -> str:
        """Get the current page URL."""
        page = self.state_manager.get_current_page()
        return page.url if page else "No pages available"

    def dispose(self):
        """Clean up resources."""
        # State manager cleanup is handled by the browser context
        pass