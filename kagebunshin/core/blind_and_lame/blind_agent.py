"""
The Blind Agent - High-level reasoning without direct page access.

This agent can reason and plan but cannot see web pages directly.
It relies on the Lame Agent for all browser interactions through natural language commands.
Implemented using LangGraph's prebuilt ReAct agent, which iteratively calls tools
and terminates automatically when no further tool calls are made.
"""

import logging
from pathlib import Path
from typing import Any, List, Optional, Dict

from langchain_core.messages import HumanMessage, BaseMessage, AIMessage
from langchain.chat_models.base import init_chat_model
from langgraph.prebuilt import create_react_agent

from .lame_agent import LameAgent
from ...utils import normalize_chat_content

logger = logging.getLogger(__name__)


class BlindAgent:
    """
    The Blind Agent - high-level reasoning without direct browser access.
    
    This agent:
    - Uses GPT-5 with reasoning effort for strategic planning
    - Has access only to act() tool from Lame agent
    - Follows text-based reasoning patterns like ALFWORLD
    - Maintains conversation history and task context
    """
    
    def __init__(self, lame_agent: LameAgent, additional_tools: Optional[List[Any]] = None):
        self.lame_agent = lame_agent
        
        # Load system prompt from file
        self.prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        self._load_system_prompt()
        
        # Import configuration here to avoid circular imports
        from ...config.settings import (
            BLIND_MODEL, 
            BLIND_PROVIDER, 
            BLIND_REASONING_EFFORT, 
            BLIND_TEMPERATURE
        )
        
        # Initialize LLM with reasoning capabilities
        self.llm = init_chat_model(
            model=BLIND_MODEL,
            model_provider=BLIND_PROVIDER,
            temperature=BLIND_TEMPERATURE,
            reasoning={"effort": BLIND_REASONING_EFFORT} if "gpt-5" in BLIND_MODEL else None
        )
        
        # Get act tool from Lame agent
        self.act_tool = self.lame_agent.get_act_tool_for_blind()

        # Create a prebuilt ReAct agent that stops when no tool call is made
        tools = [self.act_tool] + (additional_tools or [])
        self.agent = create_react_agent(
            self.llm,
            tools=tools,
            messages_modifier=self.system_prompt,
        )

        logger.info(f"BlindAgent initialized with {BLIND_MODEL} via ReAct agent and act() tool")
    
    def _load_system_prompt(self):
        """Load system prompt from file."""
        try:
            with open(self.prompts_dir / "blind_agent_system_prompt.md", "r") as f:
                self.system_prompt = f.read()
        except FileNotFoundError as e:
            logger.error(f"Could not load blind agent system prompt: {e}")
            # Fallback prompt
            self.system_prompt = """You are the Blind Agent. You cannot see web pages directly but can issue commands through the act() tool.
            Think step-by-step and use natural language commands to complete tasks."""
    
    # ReAct agent handles planning/execution; no custom workflow graph required
    
    async def ainvoke(self, user_query: str) -> str:
        """
        Main entry point for processing user queries.
        
        Args:
            user_query: The task or question from the user
            
        Returns:
            Final response after task completion
        """
        logger.info(f"BlindAgent processing query: {user_query}")
        
        try:
            # Run the prebuilt ReAct agent; it terminates when no tool call is made
            final_state = await self.agent.ainvoke({
                "messages": [HumanMessage(content=user_query)]
            })
            
            # Extract final answer
            return self._extract_final_answer(final_state)
            
        except Exception as e:
            logger.error(f"Error in BlindAgent workflow: {e}")
            return f"Error processing request: {str(e)}"
    
    async def astream(self, user_query: str):
        """
        Stream the agent's reasoning and actions.
        
        Args:
            user_query: The task or question from the user
            
        Yields:
            Dict: Streaming updates from the workflow
        """
        try:
            async for chunk in self.agent.astream(
                {"messages": [HumanMessage(content=user_query)]},
                stream_mode="updates",
            ):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error in BlindAgent streaming: {e}")
            yield {"error": f"Streaming error: {str(e)}"}
    
    def _extract_final_answer(self, final_state: Dict[str, Any]) -> str:
        """Extract the final answer from the conversation."""
        try:
            messages = final_state["messages"]
        except Exception:
            return "Task completed, but no specific answer was provided."
        
        # Look for the most recent substantial AI response
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and getattr(msg, "content", None):
                content_text = normalize_chat_content(msg.content).strip()
                if content_text and not content_text.startswith("I need to"):
                    return content_text
        
        return "Task completed."
    
    def dispose(self):
        """Clean up resources."""
        if self.lame_agent:
            self.lame_agent.dispose()