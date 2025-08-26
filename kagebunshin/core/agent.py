"""
Kagebunshin Agent - The main brain that coordinates web automation tasks.
This module is responsible for processing user queries and updating Kagebunshin's state
by coordinating with the stateless state manager.
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage, ToolMessage
from langchain.chat_models.base import init_chat_model
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from playwright.async_api import BrowserContext

from .state import KageBunshinState, Annotation, TabInfo
from .state_manager import KageBunshinStateManager
from ..config.settings import (
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_REASONING_EFFORT,
    LLM_TEMPERATURE,
    SUMMARIZER_MODEL,
    SUMMARIZER_PROVIDER,
    SUMMARIZER_REASONING_EFFORT,
    SYSTEM_TEMPLATE,
    GROUPCHAT_ROOM,
    MAX_KAGEBUNSHIN_INSTANCES,
    ENABLE_SUMMARIZATION,
    RECURSION_LIMIT,
)
from ..utils import format_img_context, format_bbox_context, format_text_context, format_tab_context, format_unified_context, generate_agent_name, normalize_chat_content
from ..communication.group_chat import GroupChatClient

logger = logging.getLogger(__name__)


class KageBunshinAgent:
    """The main orchestrator for KageBunshin's AI-driven web automation."""
    # Global instance tracking to enforce a hard cap per-process
    _INSTANCE_COUNT: int = 0
    
    def __init__(self, 
                 context: BrowserContext,
                 state_manager: KageBunshinStateManager,
                 additional_tools: List[Any] = None, 
                 system_prompt: str = SYSTEM_TEMPLATE,
                 enable_summarization: bool = ENABLE_SUMMARIZATION,
                 group_room: Optional[str] = None,
                 username: Optional[str] = None,
                 clone_depth: int = 0,
                 # Optional LLM configuration
                 llm: Optional[Any] = None,
                 llm_model: str = LLM_MODEL,
                 llm_provider: str = LLM_PROVIDER,
                 llm_reasoning_effort: str = LLM_REASONING_EFFORT,
                 llm_temperature: float = LLM_TEMPERATURE,
                 # Optional summarizer configuration
                 summarizer_llm: Optional[Any] = None,
                 summarizer_model: str = SUMMARIZER_MODEL,
                 summarizer_provider: str = SUMMARIZER_PROVIDER,
                 summarizer_reasoning_effort: str = SUMMARIZER_REASONING_EFFORT,
                 # Optional workflow configuration
                 recursion_limit: int = RECURSION_LIMIT):
        """Initializes the orchestrator with browser context and state manager."""
        
        self.initial_context = context
        self.state_manager = state_manager
        self.system_prompt = system_prompt
        self.enable_summarization = enable_summarization
        self.clone_depth = clone_depth
        self.recursion_limit = recursion_limit
        # Simple in-process memory of message history across turns
        self.persistent_messages: List[BaseMessage] = []

        # Use provided LLM or create from configuration
        if llm is not None:
            self.llm = llm
        else:
            self.llm = init_chat_model(
                model=llm_model,
                model_provider=llm_provider,
                temperature=llm_temperature,
                reasoning={"effort": llm_reasoning_effort} if "gpt-5" in llm_model else None
            )
        
        # Use provided summarizer LLM or create from configuration
        if summarizer_llm is not None:
            self.summarizer_llm = summarizer_llm
        else:
            self.summarizer_llm = init_chat_model(
                model=summarizer_model, 
                model_provider=summarizer_provider,
                temperature=llm_temperature,
                reasoning={"effort": summarizer_reasoning_effort} if "gpt-5" in summarizer_model else None
            )
        
        self.last_page_annotation: Optional[Annotation] = None
        self.last_page_tabs: Optional[List[TabInfo]] = None
        self.main_llm_img_message_type = HumanMessage if "gemini" in llm_model or llm_reasoning_effort is not None else SystemMessage
        self.summarizer_llm_img_message_type = HumanMessage if "gemini" in summarizer_model or summarizer_reasoning_effort is not None else SystemMessage
        web_browsing_tools = self.state_manager.get_tools_for_llm()
        self.all_tools = web_browsing_tools + (additional_tools or [])

        # Group chat setup
        self.group_room = group_room or GROUPCHAT_ROOM
        self.username = username or generate_agent_name()
        self.group_client = GroupChatClient()
        
        # Bind tools to the LLM so it knows what functions it can call
        self.llm_with_tools = self.llm.bind_tools(self.all_tools)
        
        # Define the graph
        workflow = StateGraph(KageBunshinState)

        workflow.add_node("agent", self.call_agent)
        workflow.add_node("action", ToolNode(self.all_tools))
        if self.enable_summarization:
            workflow.add_node("summarizer", self.summarize_tool_results)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "continue": "action",
                "end": END,
            },
        )
        if self.enable_summarization:
            workflow.add_edge("action", "summarizer")
            workflow.add_edge("summarizer", "agent")
        else:
            workflow.add_edge("action", "agent")
        
        # Compile without external checkpointer (BrowserContext is not serializable)
        self.agent = workflow.compile()

        # Post intro message asynchronously (do not block init)
        # asyncio.create_task(self._post_intro_message())

    def dispose(self) -> None:
        """Release this orchestrator's slot in the global instance counter."""
        try:
            if KageBunshinAgent._INSTANCE_COUNT > 0:
                KageBunshinAgent._INSTANCE_COUNT -= 1
        except Exception:
            pass

    @classmethod
    async def create(cls, 
                     context: BrowserContext,
                     additional_tools: List[Any] = None, 
                     system_prompt: str = SYSTEM_TEMPLATE,
                     enable_summarization: bool = ENABLE_SUMMARIZATION,
                     group_room: Optional[str] = None,
                     username: Optional[str] = None,
                     clone_depth: int = 0,
                     # Optional LLM configuration
                     llm: Optional[Any] = None,
                     llm_model: str = LLM_MODEL,
                     llm_provider: str = LLM_PROVIDER,
                     llm_reasoning_effort: str = LLM_REASONING_EFFORT,
                     llm_temperature: float = LLM_TEMPERATURE,
                     # Optional summarizer configuration
                     summarizer_llm: Optional[Any] = None,
                     summarizer_model: str = SUMMARIZER_MODEL,
                     summarizer_provider: str = SUMMARIZER_PROVIDER,
                     summarizer_reasoning_effort: str = SUMMARIZER_REASONING_EFFORT,
                     # Optional workflow configuration
                     recursion_limit: int = RECURSION_LIMIT,
                     **kwargs):  # Allow additional kwargs for future extensibility
        """Factory method to create a KageBunshinAgent with async initialization."""
        # Enforce a maximum number of instances per-process
        if cls._INSTANCE_COUNT >= MAX_KAGEBUNSHIN_INSTANCES:
            raise RuntimeError(
                f"Instance limit reached: at most {MAX_KAGEBUNSHIN_INSTANCES} KageBunshinAgent instances are allowed."
            )
        state_manager = await KageBunshinStateManager.create(context)
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
            recursion_limit=recursion_limit
        )
        cls._INSTANCE_COUNT += 1
        return instance

    async def call_agent(self, state: KageBunshinState) -> Dict[str, List[BaseMessage]]:
        """
        Calls the LLM with the current state to decide the next action.
        
        This node is the "brain" of the agent. It takes the current state from the graph,
        builds a context with the latest page snapshot, and asks the LLM for the next move.
        """
        messages = await self._build_agent_messages(state)
        response = await self.llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(self, state: KageBunshinState) -> str:
        """
        Determines whether the agent should continue or end the process.
        
        If the last message from the agent has tool calls, we continue to the action node.
        Otherwise, we end the execution.
        """
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "continue"
        return "end"

    async def ainvoke(self, user_query: str) -> str:
        """
        Main entry point for processing user queries.
        Orchestrates loading, reasoning, and web automation by running the graph.
        """
        logger.info(f"Processing query: {user_query}")
        # Announce task to group chat
        try:
            await self.group_client.connect()
            await self._post_intro_message()
            # await self.group_client.post(self.group_room, self.username, f"Starting task: {user_query}")
        except Exception:
            pass
        
        initial_state = KageBunshinState(
            input=user_query,
            messages=[*self.persistent_messages, HumanMessage(content=user_query)],
            context=self.initial_context,
            clone_depth=self.clone_depth,
        )
        
        # The graph will execute until it hits an END state
        final_state = await self.agent.ainvoke(initial_state, config={"recursion_limit": self.recursion_limit})
        
        # Update the state manager with the final state before extracting the answer
        self.state_manager.set_state(final_state)
        # Persist messages for subsequent turns
        try:
            self.persistent_messages = final_state["messages"]
        except Exception:
            pass
        
        return self._extract_final_answer()
        
    async def astream(self, user_query: str) -> AsyncGenerator[Dict, None]:
        """
        Stream the intermediate steps of the agent's execution.
        
        This method is useful for observing the agent's thought process and actions
        in real-time. It yields the output of each node in the graph as it executes.
        """
        # Announce task to group chat (streaming entry)
        try:
            await self.group_client.connect()
            # await self.group_client.post(self.group_room, self.username, f"Starting task (stream): {user_query}")
        except Exception:
            pass

        initial_messages = [*self.persistent_messages, HumanMessage(content=user_query)]
        initial_state = KageBunshinState(
            input=user_query,
            messages=initial_messages,
            context=self.initial_context,
            clone_depth=self.clone_depth,
        )

        # Accumulate the full conversation history during streaming updates
        accumulated_messages: List[BaseMessage] = list(initial_messages)

        async for chunk in self.agent.astream(initial_state, stream_mode="updates", config={"recursion_limit": self.recursion_limit}):
            # Yield upstream for observers/CLI
            yield chunk

            # Merge any new messages from nodes into our accumulated history
            try:
                for node_key in ("agent", "action", "summarizer"):
                    node_update = chunk.get(node_key) or {}
                    new_msgs = node_update.get("messages", [])
                    if new_msgs:
                        # Ensure type correctness; they are BaseMessage instances in updates
                        accumulated_messages.extend(new_msgs)  # type: ignore[arg-type]
            except Exception:
                # Never let streaming observers break accumulation
                pass

        # After stream completes, persist final messages and update state
        try:
            final_state: KageBunshinState = KageBunshinState(
                input=user_query,
                messages=accumulated_messages,
                context=self.initial_context,
                clone_depth=self.clone_depth,
            )
            self.state_manager.set_state(final_state)
            self.persistent_messages = accumulated_messages
        except Exception:
            # If anything goes wrong, keep prior behavior (best-effort)
            try:
                if self.state_manager.current_state:
                    self.persistent_messages = self.state_manager.current_state["messages"]
            except Exception:
                pass
            
    async def _build_agent_messages(self, state: KageBunshinState) -> List[BaseMessage]:
        """
        Builds the list of messages to be sent to the LLM.
        
        This method constructs the context for the LLM, including the system prompt,
        the conversation history, and a snapshot of the current web page state.
        This is called before every LLM invocation to ensure the agent has the
        most up-to-date information.
        """
        # Set the state manager to the current state from the graph
        self.state_manager.set_state(state)
        
        messages = [SystemMessage(content=self.system_prompt)]
        messages.extend(state["messages"])
        
        # Create page context and store it for the summarizer
        page_data = await self.state_manager.get_current_page_data()
        page_context = await self._build_page_context(page_data, self.main_llm_img_message_type)
        self.last_page_annotation = page_data
        self.last_page_tabs = await self.state_manager.get_tabs()
        
        # Add navigation state verification to prevent hallucination
#         current_url = await self.get_current_url()
#         if not current_url or current_url in ("about:blank", "data:,") or "google.com" in current_url.lower():
#             # Agent hasn't navigated to substantive content yet
#             verification_reminder = SystemMessage(content="""⚠️ NAVIGATION STATUS: You haven't navigated to any specific content sources yet. 
            
# If the user's query requires factual information, you MUST:
# 1. Start by searching Google or navigating to relevant websites
# 2. Observe actual page content before making any claims
# 3. Base your response only on what you directly observe

# DO NOT make factual claims based on assumed knowledge.""")
#             messages.append(verification_reminder)
        
        # Inject group chat history as context
        try:
            await self.group_client.connect()
            history = await self.group_client.history(self.group_room, limit=50)
            chat_block = self.group_client.format_history(history)
            
            messages.append(SystemMessage(content=f"Your name is {self.username}.\n\nHere is the group chat history:\n\n{chat_block}"))
        except Exception:
            pass

        messages.extend(page_context)
        return messages

    async def _post_intro_message(self) -> None:
        try:
            await self.group_client.connect()
            intro = f"Hello, I am {self.username}. I will collaborate here while working on tasks."
            await self.group_client.post(self.group_room, self.username, intro)
        except Exception:
            pass
    
    async def summarize_tool_results(self, state: KageBunshinState) -> Dict[str, List[BaseMessage]]:
        """
        Analyzes the state before and after a tool call and adds a natural
        language summary to the message history.
        """
        if not self.enable_summarization:
            return state
        
        # Find the last AIMessage and subsequent ToolMessages
        tool_messages = []
        ai_message = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage):
                tool_messages.insert(0, msg)
            if isinstance(msg, AIMessage) and msg.tool_calls:
                ai_message = msg
                break
        
        if not ai_message or not tool_messages:
            # Nothing to summarize
            return state

        # Get "Before" context
        before_context_messages = await self._build_page_context(self.last_page_annotation,
                                                                 self.summarizer_llm_img_message_type,
                                                                 self.last_page_tabs)
        
        # Get "After" context
        after_context = await self.state_manager.get_current_page_data()
        after_context_messages = await self._build_page_context(after_context, self.summarizer_llm_img_message_type)
        
        # Load prompt from file
        try:
            import os
            prompt_path = os.path.join(os.path.dirname(__file__), "..", "config", "prompts", "diff_summarizer.md")
            with open(prompt_path, "r") as f:
                prompt_content = f.read()
        except Exception:
            # Fallback to inline prompt if file not found
            prompt_content = "You are an expert web automation assistant. Your task is to summarize the changes on a webpage after a tool was executed. Based on the page state before and after the action, and the action itself, provide a concise, natural language summary of what happened. Focus on what a user would perceive as the change. Start your summary with 'After executing the tool, ...'"
        
        # Build prompt for summarizer
        summary_prompt_messages = [
            SystemMessage(content=prompt_content),
            HumanMessage(content="Here is the state of the page before the action:"),
        ]
        if self.last_page_annotation:
            summary_prompt_messages.extend(before_context_messages)
        
        tool_calls_str = ", ".join([f"{tc['name']}({tc['args']})" for tc in ai_message.tool_calls])
        tool_results_str = ", ".join([normalize_chat_content(getattr(msg, "content", "")) for msg in tool_messages])
        action_text = (
            f"The action taken was: {tool_calls_str}\n\n"
            f"The result of the action was: {tool_results_str}\n\n"
            "Here is the state of the page after the action: "
        )
        summary_prompt_messages.append(HumanMessage(content=action_text))
        summary_prompt_messages.extend(after_context_messages)

        try:
            summary_response = await self.summarizer_llm.ainvoke(summary_prompt_messages)
            summary_text = normalize_chat_content(getattr(summary_response, "content", ""))
            summary_message = SystemMessage(content=f"Summary of last action: {summary_text}")
            
            return {"messages": [summary_message]}
        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            # Continue without summary if it fails
            return state

    async def _build_page_context(self,
                                  page_data: Annotation,
                                  message_type: type = SystemMessage,
                                  tab_info_override: Optional[List[TabInfo]] = None) -> List[BaseMessage]:
        """Add current page state to the context as a single consolidated SystemMessage."""
        
        # Collect all text content parts
        context_parts = []
        
        # Tab information
        tabs = tab_info_override or await self.state_manager.get_tabs()
        if len(tabs) > 1:
            current_tab_index = await self.state_manager.get_current_tab_index()
            tab_context = format_tab_context(tabs, current_tab_index)
            context_parts.append(tab_context)
        
        # Page state information
        if page_data.img and page_data.bboxes:
            context_parts.append("Current state of the page:\n\n")
        
        # current url
        current_url = await self.get_current_url()
        context_parts.append(f"Current URL: {current_url}")

        # Unified page context (combines interactive elements and content structure)
        if page_data.bboxes:
            unified_context = format_unified_context(page_data.bboxes, detail_level="full_hierarchy")
            context_parts.append(unified_context)
        
        # Additional page content if available (fallback for cases without bboxes)
        elif page_data.markdown:
            text_context = format_text_context(page_data.markdown)
            context_parts.append(text_context)
        
        # Build consolidated content
        if context_parts or page_data.img:
            consolidated_content = []
            
            # Add all text content as one block
            if context_parts:
                consolidated_content.append({
                    "type": "text",
                    "text": "\n\n".join(context_parts)
                })
        
            # Return single SystemMessage with mixed content if we have an image, otherwise just text
            if page_data.img:
                img_content = format_img_context(page_data.img)
                consolidated_content.append(img_content)
                consolidated_content.append({
                    "type": "text",
                    "text": "\n\nBased on the current state of the page and the context, take the best action to fulfill the user's request."
                })
                return [message_type(content=consolidated_content)]
            else:
                return [message_type(content="\n\n".join(context_parts))]
        
        return []
    
    def _extract_final_answer(self) -> str:
        """Extract the final answer from the conversation."""
        try:
            messages = self.state_manager.current_state["messages"]
        except Exception:
            return "Task completed, but no specific answer was provided."

        # 1) Prefer explicit final markers produced by the agent (AI messages only)
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and getattr(msg, "content", None):
                content_text = normalize_chat_content(msg.content)
                if "[FINAL ANSWER]" in content_text:
                    return content_text.replace("[FINAL ANSWER]", "").strip()

        # 2) Otherwise, pick the most recent AI message with substantive content
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and getattr(msg, "content", None):
                content_text = normalize_chat_content(msg.content).strip()
                return content_text

        # 3) If nothing suitable is found, return a safe default
        return "Task completed, but no specific answer was provided."
    
    async def get_current_url(self) -> str:
        """Get the current page URL."""
        if self.state_manager.current_state:
            current_page_index = await self.state_manager.get_current_tab_index()
            return self.state_manager.current_state["context"].pages[current_page_index].url
        return "No pages available"
    
    async def get_current_title(self) -> str:
        """Get the current page title."""
        if self.state_manager.current_state:
            current_page_index = await self.state_manager.get_current_tab_index()
            return await self.state_manager.current_state["context"].pages[current_page_index].title()
        return "No pages available"
    
    def get_action_count(self) -> int:
        """Get the number of actions performed."""
        return self.state_manager.num_actions_done
