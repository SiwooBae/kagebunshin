"""
Additional tools for Kagebunshin.

Includes a "delegate" tool that spawns shadow-clone sub-agents to handle
focused subtasks. Each clone runs in a fresh, isolated Playwright BrowserContext
and returns its final answer to the caller.
"""

from typing import Any, List, Optional, Annotated
import logging
import asyncio
import json

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage, AIMessage, ToolMessage
from langchain.chat_models.base import init_chat_model
from langgraph.prebuilt import InjectedState
from playwright.async_api import BrowserContext

from ..core.agent import KageBunshinAgent
from ..core.state import KageBunshinState
from ..automation.fingerprinting import apply_fingerprint_profile_to_context
from ..config.settings import (
    DEFAULT_PERMISSIONS, 
    GROUPCHAT_ROOM, 
    MAX_KAGEBUNSHIN_INSTANCES,
    SUMMARIZER_MODEL,
    SUMMARIZER_PROVIDER, 
    SUMMARIZER_REASONING_EFFORT,
    LLM_TEMPERATURE
)
from ..communication.group_chat import GroupChatClient
from ..utils import generate_agent_name, normalize_chat_content


logger = logging.getLogger(__name__)


async def _summarize_conversation_history(messages: List[BaseMessage], parent_name: str) -> str:
    """Summarize parent's conversation history for clone context."""
    if not messages:
        return "No prior conversation history."

    def _shorten(text: str, max_len: int = 400) -> str:
        try:
            s = str(text).strip()
        except Exception:
            s = ""
        if len(s) <= max_len:
            return s
        return s[: max_len - 3] + "..."

    # Condense conversation: skip system boilerplate, capture user intents, tool calls and results
    condensed_lines: List[str] = []

    # Keep the very first user request if present for goal context
    first_user = next((m for m in messages if isinstance(m, HumanMessage) and getattr(m, "content", None)), None)
    if first_user and getattr(first_user, "content", None):
        condensed_lines.append(f"Initial request: {normalize_chat_content(first_user.content)}")

    for msg in messages[-200:]:  # limit history for token efficiency
        try:
            if isinstance(msg, SystemMessage):
                continue  # avoid long system prompts
            if isinstance(msg, AIMessage):
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    calls_formatted = []
                    for tc in tool_calls:
                        name = tc.get("name", "tool") if isinstance(tc, dict) else getattr(tc, "name", "tool")
                        args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                        try:
                            args_str = json.dumps(args, ensure_ascii=False) if isinstance(args, (dict, list)) else str(args)
                        except Exception:
                            args_str = str(args)
                        calls_formatted.append(f"{name}({_shorten(args_str, 120)})")
                    condensed_lines.append(f"AI called: {', '.join(calls_formatted)}")
                elif getattr(msg, "content", None):
                    condensed_lines.append(f"AI: {_shorten(normalize_chat_content(msg.content), 400)}")
                continue
            if isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", None) or getattr(msg, "tool_name", "tool")
                condensed_lines.append(
                    f"Tool[{tool_name}] → {_shorten(normalize_chat_content(getattr(msg, 'content', '')), 400)}"
                )
                continue
            if isinstance(msg, HumanMessage):
                condensed_lines.append(f"User: {_shorten(getattr(msg, 'content', ''), 400)}")
                continue
            # Fallback for any other message types
            content = getattr(msg, "content", None)
            if content:
                condensed_lines.append(_shorten(normalize_chat_content(content), 400))
        except Exception:
            # Never let a single bad message break summarization
            continue

    if not condensed_lines:
        return "No meaningful conversation history to summarize."

    # Further trim to recent context while preserving the initial request if present
    initial_line = condensed_lines[0] if condensed_lines and condensed_lines[0].startswith("Initial request:") else None
    tail_lines = condensed_lines
    if initial_line and tail_lines[0] != initial_line:
        condensed_for_llm = "\n".join([initial_line] + tail_lines)
    else:
        condensed_for_llm = "\n".join(tail_lines)

    try:
        # Initialize summarizer LLM
        summarizer = init_chat_model(
            model=SUMMARIZER_MODEL,
            model_provider=SUMMARIZER_PROVIDER,
            temperature=LLM_TEMPERATURE,
            reasoning={"effort": SUMMARIZER_REASONING_EFFORT} if "gpt-5" in SUMMARIZER_MODEL else None
        )

        system_prompt = (
            "You are an expert assistant preparing a crisp handoff summary for a clone agent. "
            "Write 2-4 concise sentences that clearly state: (1) the main objective, "
            "(2) key actions/important tool results so far, and (3) current status and blockers/next focus. "
            "Be concrete and actionable, avoid boilerplate and internal prompts."
        )
        human_prompt = (
            "Conversation history (chronological, trimmed):\n" + condensed_for_llm + "\n\n" +
            "Produce the handoff summary now."
        )

        response = await summarizer.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])
        
        return normalize_chat_content(response.content)

    except Exception as e:
        logger.warning(f"Failed to summarize conversation history: {e}")
        return f"Parent agent {parent_name} was working on tasks (summary unavailable)."


def get_additional_tools(context: BrowserContext, username: Optional[str] = None, group_room: Optional[str] = None) -> List[Any]:
    """
    Construct additional tools bound to a specific BrowserContext.

    The returned tools can be passed into `KageBunshinV2.create(..., additional_tools=...)`.
    """

    chat_client = GroupChatClient()

    @tool
    async def delegate(tasks: List[str], state: Annotated[dict, InjectedState]) -> str:
        """Spawn shadow-clone sub-agents in parallel to execute multiple focused subtasks.

        Args:
            tasks: List of subtasks to execute. One clone is spawned per task.
            state: Current conversation state injected by LangGraph.

        Behavior:
            - Always creates a fresh incognito BrowserContext per task (best isolation).
            - Clones inherit summarized conversation history from parent for context.
            - Clones have full delegation capabilities and can create their own sub-clones.
            - No initial URL is opened automatically.
            - Returns a JSON array of {"task", "status", "result"|"error"} as a string.
            - Resources are closed automatically after each clone finishes.
        """

        if not tasks or not isinstance(tasks, list):
            return json.dumps({"error": "'tasks' must be a non-empty list of strings"})

        # Get current conversation history from injected state
        current_messages = state.get("messages", [])
        parent_name = username or "parent-agent"
        
        # Track clone depth to prevent infinite recursion
        current_depth = state.get("clone_depth", 0)
        if current_depth >= 3:  # Limit clone depth to 3 levels
            return json.dumps({"error": f"Maximum clone depth ({current_depth}) reached. Consider alternative approaches."})
        
        # Summarize conversation history for clone context
        try:
            conversation_summary = await _summarize_conversation_history(current_messages, parent_name)
        except Exception as e:
            logger.warning(f"Failed to summarize conversation: {e}")
            conversation_summary = f"Parent agent {parent_name} was working on tasks (summary unavailable)."

        async def run_single_task(task_str: str) -> dict:
            created_context: Optional[BrowserContext] = None
            clone: Optional[KageBunshinAgent] = None
            try:
                # Capacity check (best-effort; create() also enforces)
                if KageBunshinAgent._INSTANCE_COUNT >= MAX_KAGEBUNSHIN_INSTANCES:
                    return {
                        "task": task_str,
                        "status": "denied",
                        "error": f"Delegation denied: max agents reached ({MAX_KAGEBUNSHIN_INSTANCES}).",
                    }

                browser = getattr(context, "browser", None)
                if browser is None:
                    return {
                        "task": task_str,
                        "status": "error",
                        "error": "Cannot create new BrowserContext from the current context",
                    }

                created_context = await browser.new_context(permissions=DEFAULT_PERMISSIONS)
                try:
                    await apply_fingerprint_profile_to_context(created_context)
                except Exception:
                    pass

                child_name = generate_agent_name()
                clone_tools = get_additional_tools(created_context, username=child_name, group_room=group_room)
                try:
                    clone = await KageBunshinAgent.create(
                        created_context,
                        additional_tools=clone_tools,
                        group_room=group_room,
                        username=child_name,
                        enable_summarization=False,
                        clone_depth=current_depth + 1,
                    )
                except RuntimeError as e:
                    return {"task": task_str, "status": "denied", "error": f"Delegation denied: {e}"}

                # Create context-aware task message for the clone
                clone_context_message = f"""🧬 CLONE BRIEFING: You are a shadow clone of {parent_name} (Depth: {current_depth + 1})! 

PARENT CONTEXT: {conversation_summary}

YOUR MISSION: {task_str}

🚫 VERIFICATION CRITICAL: Remember to GROUND ALL RESPONSES in actual observations! Navigate first, conclude second. Never make claims without visiting relevant sources and observing actual content.

IMPORTANT: You have FULL delegation capabilities! If your task would benefit from parallelization, don't hesitate to create your own clones using the delegate tool. You are NOT limited by being a clone yourself - the swarm intelligence philosophy applies at every level.

Coordination: Use the group chat to coordinate with your parent and other agents. Think strategically about when to parallelize vs. when to work sequentially."""

                result = await clone.ainvoke(clone_context_message)
                return {"task": task_str, "status": "ok", "result": result}
            except Exception as e:
                logger.error(f"Delegate task failed: {e}")
                return {"task": task_str, "status": "error", "error": str(e)}
            finally:
                try:
                    if clone is not None:
                        clone.dispose()
                except Exception:
                    pass
                if created_context is not None:
                    try:
                        await created_context.close()
                    except Exception:
                        pass

        # Run all tasks concurrently, respecting any runtime caps in create()
        results = await asyncio.gather(*(run_single_task(t) for t in tasks), return_exceptions=False)
        # Return pure JSON per docstring for easy downstream parsing/consumption
        return json.dumps(results)

    @tool
    async def post_groupchat(message: str) -> str:
        """Post a short message to the shared Agent Group Chat for collaboration.

        Args:
            message: The message to broadcast to other agents.
        """
        try:
            await chat_client.connect()
            room = group_room or GROUPCHAT_ROOM
            name = username or "anonymous-agent"
            await chat_client.post(room=room, sender=name, message=message)
            return f"Posted to group chat ({room})"
        except Exception as e:
            logger.error(f"post_groupchat failed: {e}")
            return f"Error posting to group chat: {e}"

    return [delegate, post_groupchat]

