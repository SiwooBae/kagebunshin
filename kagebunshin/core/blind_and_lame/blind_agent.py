"""
The Blind Agent - High-level reasoning without direct page access.

This agent can reason and plan but cannot see web pages directly.
It relies on the Lame Agent for all browser interactions through natural language commands.
Implemented using LangGraph's prebuilt ReAct agent, which iteratively calls tools
and terminates automatically when no further tool calls are made.
"""

import logging
from pathlib import Path
from typing import Any, List, Optional, Dict, AsyncGenerator

from langchain_core.messages import HumanMessage, BaseMessage, AIMessage
from langchain.chat_models.base import init_chat_model
from langgraph.prebuilt import create_react_agent
from playwright.async_api import BrowserContext

from .lame_agent import LameAgent
from ..state import KageBunshinState
from ..state_manager import KageBunshinStateManager
from ...utils import normalize_chat_content, generate_agent_name
from ...communication.group_chat import GroupChatClient
from ...tools.filesystem import get_filesystem_tools, FilesystemConfig, FilesystemSandbox, cleanup_workspace
from ...config.settings import (
    # Filesystem configuration
    FILESYSTEM_ENABLED,
    FILESYSTEM_SANDBOX_BASE,
    FILESYSTEM_MAX_FILE_SIZE,
    FILESYSTEM_ALLOWED_EXTENSIONS,
    FILESYSTEM_ALLOW_OVERWRITE,
    FILESYSTEM_CREATE_SANDBOX,
    FILESYSTEM_LOG_OPERATIONS,
    FILESYSTEM_MAX_CONCURRENT_OPERATIONS,
    FILESYSTEM_CLEANUP_ENABLED,
    FILESYSTEM_CLEANUP_MAX_AGE_DAYS,
    FILESYSTEM_CLEANUP_MAX_SIZE,
)
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
    
    # Global instance tracking to enforce a hard cap per-process
    _INSTANCE_COUNT: int = 0
    
    def __init__(
        self,
        context: BrowserContext,
        state_manager: KageBunshinStateManager,
        additional_tools: List[Any] = None,
        system_prompt: Optional[str] = None,  # Will load from file if None
        enable_summarization: bool = False,  # Not used in BlindAgent
        group_room: Optional[str] = None,
        username: Optional[str] = None,
        clone_depth: int = 0,
        # Optional LLM configuration
        llm: Optional[Any] = None,
        llm_model: Optional[str] = None,  # Will use BLIND_MODEL if None
        llm_provider: Optional[str] = None,  # Will use BLIND_PROVIDER if None
        llm_reasoning_effort: Optional[str] = None,  # Will use BLIND_REASONING_EFFORT if None
        llm_temperature: Optional[float] = None,  # Will use BLIND_TEMPERATURE if None
        # Optional summarizer configuration (ignored for BlindAgent)
        summarizer_llm: Optional[Any] = None,
        summarizer_model: Optional[str] = None,
        summarizer_provider: Optional[str] = None,
        summarizer_reasoning_effort: Optional[str] = None,
        # Optional workflow configuration
        recursion_limit: int = 150,  # Default for ReAct agent
        # Optional filesystem configuration (ignored for BlindAgent)
        filesystem_enabled: Optional[bool] = None,
        filesystem_sandbox_base: Optional[str] = None,
        # Legacy parameter support
        lame_agent: Optional[LameAgent] = None,
    ):
        """Initialize BlindAgent with KageBunshinAgent-compatible interface."""
        # Store KageBunshinAgent-compatible attributes
        self.initial_context = context
        self.state_manager = state_manager
        self.clone_depth = clone_depth
        self.recursion_limit = recursion_limit
        
        # Group chat setup
        from ...config.settings import GROUPCHAT_ROOM
        self.group_room = group_room or GROUPCHAT_ROOM
        self.username = username or generate_agent_name()
        self.group_client = GroupChatClient()
        
        # Persistent message history for conversation continuity
        self.persistent_messages: List[BaseMessage] = []
        
        # Create or use provided LameAgent
        if lame_agent is not None:
            # Legacy usage - direct LameAgent provided
            self.lame_agent = lame_agent
        else:
            # New usage - create LameAgent from context
            # This will be set in the create() method
            self.lame_agent: Optional[LameAgent] = None
        
        # Load system prompt from file or use provided
        self.prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        if system_prompt is not None:
            self.system_prompt = system_prompt
        else:
            self._load_system_prompt()
        
        # Import configuration here to avoid circular imports
        from ...config.settings import (
            BLIND_MODEL, 
            BLIND_PROVIDER, 
            BLIND_REASONING_EFFORT, 
            BLIND_TEMPERATURE
        )
        
        # Use provided LLM or create from configuration
        if llm is not None:
            self.llm = llm
        else:
            # Use provided parameters or fall back to defaults
            model = llm_model or BLIND_MODEL
            provider = llm_provider or BLIND_PROVIDER
            temperature = llm_temperature if llm_temperature is not None else BLIND_TEMPERATURE
            reasoning_effort = llm_reasoning_effort or BLIND_REASONING_EFFORT
            
            self.llm = init_chat_model(
                model=model,
                model_provider=provider,
                temperature=temperature,
                reasoning={"effort": reasoning_effort} if "gpt-5" in model else None
            )
        
        # Initialize act tool (will be set when LameAgent is available)
        self.act_tool = None
        self.agent = None

        # Store additional tools for later initialization
        self.additional_tools = additional_tools or []
        
        # Note: LLM model info will be logged after agent creation
        logger.info(f"BlindAgent constructor completed, awaiting async initialization")
    
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
    
    def _initialize_react_agent(self):
        """Initialize the ReAct agent after LameAgent is ready."""
        if self.lame_agent is None:
            raise RuntimeError("LameAgent must be initialized before creating ReAct agent")
            
                # Initialize filesystem tools if enabled
        filesystem_tools = []

        # Use provided filesystem configuration or fall back to global settings
        fs_enabled = FILESYSTEM_ENABLED
        fs_sandbox_base = FILESYSTEM_SANDBOX_BASE

        if fs_enabled:
            try:
                # Perform workspace cleanup before initializing agent
                if FILESYSTEM_CLEANUP_ENABLED:
                    try:
                        cleanup_result = cleanup_workspace(
                            workspace_base=fs_sandbox_base,
                            max_age_days=FILESYSTEM_CLEANUP_MAX_AGE_DAYS,
                            max_size_bytes=FILESYSTEM_CLEANUP_MAX_SIZE,
                            log_operations=FILESYSTEM_LOG_OPERATIONS,
                        )
                        if cleanup_result.get("directories_removed", 0) > 0:
                            logger.info(
                                f"Workspace cleanup: removed {cleanup_result['directories_removed']} "
                                f"old agent directories, freed {cleanup_result['space_freed']:,} bytes"
                            )
                    except Exception as cleanup_error:
                        # Log cleanup error but don't fail agent initialization
                        logger.warning(
                            f"Workspace cleanup failed but continuing: {cleanup_error}"
                        )

                # Create filesystem sandbox configuration for this agent
                # Each agent gets its own subdirectory within the main sandbox for isolation
                # This prevents agents from interfering with each other's files
                agent_sandbox_path = Path(fs_sandbox_base) / f"agent_{self.username}"

                filesystem_config = FilesystemConfig(
                    sandbox_base=str(agent_sandbox_path),
                    max_file_size=FILESYSTEM_MAX_FILE_SIZE,
                    allowed_extensions=FILESYSTEM_ALLOWED_EXTENSIONS.copy(),  # Copy to avoid shared reference
                    enabled=fs_enabled,
                    allow_overwrite=FILESYSTEM_ALLOW_OVERWRITE,
                    create_sandbox=FILESYSTEM_CREATE_SANDBOX,
                    log_operations=FILESYSTEM_LOG_OPERATIONS,
                )

                # Store filesystem references for context building
                self.filesystem_config = filesystem_config
                self.filesystem_sandbox = FilesystemSandbox(filesystem_config)
                
                filesystem_tools.extend(get_filesystem_tools(filesystem_config))
                logger.info(
                    f"Filesystem tools enabled for agent {self.username} with sandbox: {agent_sandbox_path}"
                )

            except Exception as e:
                # Log the error but don't fail agent initialization
                # The agent can still function without filesystem tools
                logger.error(
                    f"Failed to initialize filesystem tools for agent {self.username}: {e}"
                )
                filesystem_tools = []
        else:
            logger.info(f"Filesystem tools disabled for agent {self.username}")
        
        # Get act tool from Lame agent
        self.act_tool = self.lame_agent.get_act_tool_for_blind()
        # Create a prebuilt ReAct agent that stops when no tool call is made
        tools = [self.act_tool] + self.additional_tools + filesystem_tools
        self.agent = create_react_agent(
            self.llm,
            tools=tools,
            prompt=self.system_prompt,
        )
        
        logger.info(f"BlindAgent initialized with ReAct agent and act() tool")
    
    async def ainvoke(self, user_query: str) -> str:
        """
        Main entry point for processing user queries.
        
        Args:
            user_query: The task or question from the user
            
        Returns:
            Final response after task completion
        """
        logger.info(f"BlindAgent processing query: {user_query}")
        
        # Ensure agent is initialized
        if self.agent is None:
            raise RuntimeError("BlindAgent not properly initialized. Use BlindAgent.create() method.")
        
        try:
            # Prepare messages including persistent history
            messages = self.persistent_messages + [HumanMessage(content=user_query)]
            
            # Run the prebuilt ReAct agent; it terminates when no tool call is made
            final_state = await self.agent.ainvoke({
                "messages": messages
            })
            
            # Update persistent messages
            self.persistent_messages = final_state["messages"]
            
            # Extract final answer
            return self._extract_final_answer(final_state)
            
        except Exception as e:
            logger.error(f"Error in BlindAgent workflow: {e}")
            return f"Error processing request: {str(e)}"
    
    async def astream(self, user_query: str) -> AsyncGenerator[Dict, None]:
        """
        Stream the agent's reasoning and actions.
        
        Args:
            user_query: The task or question from the user
            
        Yields:
            Dict: Streaming updates from the workflow
        """
        # Ensure agent is initialized
        if self.agent is None:
            raise RuntimeError("BlindAgent not properly initialized. Use BlindAgent.create() method.")
            
        try:
            # Prepare messages including persistent history
            messages = self.persistent_messages + [HumanMessage(content=user_query)]
            
            accumulated_messages = list(messages)
            
            async for chunk in self.agent.astream(
                {"messages": messages},
                stream_mode="updates",
            ):
                # Track accumulated messages for persistence
                try:
                    for node_key in ("agent", "tools"):
                        node_update = chunk.get(node_key) or {}
                        new_msgs = node_update.get("messages", [])
                        if new_msgs:
                            accumulated_messages.extend(new_msgs)
                except Exception:
                    pass
                    
                yield chunk
                
            # Update persistent messages after streaming completes
            self.persistent_messages = accumulated_messages
                
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
        try:
            if BlindAgent._INSTANCE_COUNT > 0:
                BlindAgent._INSTANCE_COUNT -= 1
        except Exception:
            pass
            
        if self.lame_agent:
            self.lame_agent.dispose()

    @classmethod
    async def create(
        cls,
        context: BrowserContext,
        additional_tools: List[Any] = None,
        system_prompt: Optional[str] = None,
        enable_summarization: bool = False,
        group_room: Optional[str] = None,
        username: Optional[str] = None,
        clone_depth: int = 0,
        # Optional LLM configuration
        llm: Optional[Any] = None,
        llm_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_reasoning_effort: Optional[str] = None,
        llm_temperature: Optional[float] = None,
        # Optional summarizer configuration (ignored for BlindAgent)
        summarizer_llm: Optional[Any] = None,
        summarizer_model: Optional[str] = None,
        summarizer_provider: Optional[str] = None,
        summarizer_reasoning_effort: Optional[str] = None,
        # Optional workflow configuration
        recursion_limit: int = 150,
        # Optional filesystem configuration (ignored for BlindAgent)
        filesystem_enabled: Optional[bool] = None,
        filesystem_sandbox_base: Optional[str] = None,
        **kwargs,  # Allow additional kwargs for future extensibility
    ) -> "BlindAgent":
        """
        Factory method to create a BlindAgent with async initialization.
        
        This factory method creates a fully initialized BlindAgent that is compatible
        with KageBunshinAgent's interface but uses the blind-and-lame architecture.
        
        Args:
            context (BrowserContext): Playwright browser context for web automation
            additional_tools (List[Any], optional): Extra tools to add to the agent
            system_prompt (str, optional): System prompt for the agent (loads from file if None)
            enable_summarization (bool): Ignored for BlindAgent
            group_room (str, optional): Group chat room name
            username (str, optional): Agent username (auto-generated if None)
            clone_depth (int): Current delegation depth (0 for parent agents)
            llm (Any, optional): Pre-configured LLM instance
            llm_model (str, optional): LLM model name
            llm_provider (str, optional): LLM provider name
            llm_reasoning_effort (str, optional): LLM reasoning effort level
            llm_temperature (float, optional): LLM temperature setting
            summarizer_* (Any, optional): Summarizer config (ignored for BlindAgent)
            recursion_limit (int): Maximum workflow recursion depth
            filesystem_* (Any, optional): Filesystem config (ignored for BlindAgent)
            **kwargs: Additional configuration parameters
            
        Returns:
            BlindAgent: Fully initialized agent instance
            
        Raises:
            RuntimeError: If maximum agent instance limit is exceeded
        """
        # Enforce a maximum number of instances per-process
        from ...config.settings import MAX_KAGEBUNSHIN_INSTANCES
        if cls._INSTANCE_COUNT >= MAX_KAGEBUNSHIN_INSTANCES:
            raise RuntimeError(
                f"Instance limit reached: at most {MAX_KAGEBUNSHIN_INSTANCES} BlindAgent instances are allowed."
            )
            
        # Create state manager
        state_manager = await KageBunshinStateManager.create(context)
        
        # Create BlindAgent instance
        instance = cls(
            context=context,
            state_manager=state_manager,
            additional_tools=additional_tools,
            system_prompt=system_prompt,
            enable_summarization=enable_summarization,
            group_room=group_room,
            username=username,
            clone_depth=clone_depth,
            llm=llm,
            llm_model=llm_model,
            llm_provider=llm_provider,
            llm_reasoning_effort=llm_reasoning_effort,
            llm_temperature=llm_temperature,
            summarizer_llm=summarizer_llm,
            summarizer_model=summarizer_model,
            summarizer_provider=summarizer_provider,
            summarizer_reasoning_effort=summarizer_reasoning_effort,
            recursion_limit=recursion_limit,
            filesystem_enabled=filesystem_enabled,
            filesystem_sandbox_base=filesystem_sandbox_base,
        )
        
        # Create LameAgent
        instance.lame_agent = await LameAgent.create(context)
        
        # Append LameAgent tool names to the Blind agent's system prompt
        try:
            instance._append_lame_tools_to_prompt()
        except Exception:
            # Do not fail creation if augmentation fails
            pass

        # Initialize ReAct agent
        instance._initialize_react_agent()
        
        cls._INSTANCE_COUNT += 1
        return instance
    
    # KageBunshinAgent-compatible methods
    async def get_current_url(self) -> str:
        """Get the current page URL via LameAgent."""
        if self.lame_agent:
            return await self.lame_agent.get_current_url()
        return "No pages available"
    
    async def get_current_title(self) -> str:
        """Get the current page title."""
        if self.state_manager and self.state_manager.current_state:
            current_page_index = await self.state_manager.get_current_tab_index()
            try:
                page = self.state_manager.current_state["context"].pages[current_page_index]
                return await page.title()
            except (IndexError, AttributeError):
                pass
        return "No pages available"
    
    def get_action_count(self) -> int:
        """Get the number of actions performed."""
        if self.state_manager:
            return self.state_manager.num_actions_done
        return 0
    
    # Group chat support methods
    async def _post_intro_message(self) -> None:
        """Post introduction message to group chat."""
        try:
            await self.group_client.connect()
            intro = f"Hello, I am {self.username}. I will collaborate here while working on tasks."
            await self.group_client.post(self.group_room, self.username, intro)
        except Exception:
            pass
    
    # Filesystem compatibility methods (minimal implementation)
    def get_filesystem_context(self) -> str:
        """Get filesystem context (BlindAgent doesn't directly use filesystem)."""
        return "BlindAgent operates through LameAgent and doesn't directly access filesystem tools."
    
    def cleanup_filesystem(self) -> Dict[str, Any]:
        """Filesystem cleanup (no-op for BlindAgent)."""
        return {"status": "skipped", "reason": "BlindAgent doesn't directly manage filesystem resources"}

    def _append_lame_tools_to_prompt(self) -> None:
        """Append the available Lame assistant tool names to the system prompt."""
        if not getattr(self, "lame_agent", None):
            return
        tools = getattr(self.lame_agent, "browser_tools", None) or []
        tool_names: List[str] = []
        for t in tools:
            name = getattr(t, "name", None)
            if not name:
                # Fallbacks for unusual tool wrappers
                name = getattr(t, "__name__", None) or t.__class__.__name__
            if name and name not in tool_names:
                tool_names.append(name)

        if not tool_names:
            return

        section_header = "\n\n## available tools for Lame assistant:\n"
        names_block = "\n".join(f"- {n}" for n in tool_names)
        self.system_prompt = f"{self.system_prompt.rstrip()}{section_header}{names_block}\n"