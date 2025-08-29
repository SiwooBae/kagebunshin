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
from pathlib import Path

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage, AIMessage, ToolMessage
from langchain.chat_models.base import init_chat_model
from langgraph.prebuilt import InjectedState
from playwright.async_api import BrowserContext

# Avoid circular import - import KageBunshinAgent inside function where needed
from ..core.state import KageBunshinState
from ..automation.fingerprinting import apply_fingerprint_profile_to_context
from ..config.settings import (
    DEFAULT_PERMISSIONS, 
    GROUPCHAT_ROOM, 
    MAX_KAGEBUNSHIN_INSTANCES,
    SUMMARIZER_MODEL,
    SUMMARIZER_PROVIDER, 
    SUMMARIZER_REASONING_EFFORT,
    ACTUAL_VIEWPORT_WIDTH,
    ACTUAL_VIEWPORT_HEIGHT,
    LLM_TEMPERATURE,
    ENABLE_SUMMARIZATION,
    # Filesystem configuration for cloned agents
    FILESYSTEM_ENABLED,
    FILESYSTEM_SANDBOX_BASE,
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
        """Spawn shadow-clone sub-agents in parallel to execute multiple focused subtasks, enabling swarm intelligence.

        This is Kagebunshin's core delegation mechanism that creates parallel clone agents to divide and conquer
        complex tasks. Each clone operates independently with its own browser context while inheriting the
        parent's conversation history for context continuity.

        ## Purpose & Use Cases

        **Strategic Delegation Scenarios:**
        - Research tasks requiring multiple sources (delegate parallel fact-checking)
        - Multi-step workflows where subtasks can run concurrently
        - Data collection from multiple websites simultaneously  
        - Comparative analysis requiring parallel evaluation
        - Complex automation where different components need independent browser sessions
        - Data processing tasks where clones can read/write separate datasets
        - Report generation where clones create different sections simultaneously
        - File organization and analysis across multiple data sources

        **Swarm Intelligence Benefits:**
        - Parallel execution dramatically reduces total task completion time
        - Independent browser contexts prevent interference between subtasks
        - Each clone can further delegate, creating recursive swarm behavior
        - Automatic resource cleanup prevents memory leaks
        - Built-in capacity management prevents system overload

        ## Arguments

        **tasks** (List[str], required):
        - List of clear, focused subtask descriptions
        - Each task spawns exactly one clone agent
        - Tasks should be independent and parallelizable
        - Avoid overly broad or interdependent tasks
        - Example: ["Research Python frameworks", "Check pricing on Site A", "Extract contact info from Site B"]

        ## Returns

        **JSON string** containing array of results:
        ```json
        [
            {"task": "subtask description", "status": "ok", "result": "detailed findings..."},
            {"task": "another subtask", "status": "error", "error": "specific error message"},
            {"task": "third task", "status": "denied", "error": "capacity limit reached"}
        ]
        ```

        **Status Values:**
        - `"ok"`: Task completed successfully, see "result" field
        - `"error"`: Task failed due to technical issue, see "error" field  
        - `"denied"`: Task rejected due to capacity limits or recursion depth

        ## Behavior Details

        **Clone Creation Process:**
        1. Creates fresh incognito BrowserContext for each task (complete isolation)
        2. Generates unique agent name for each clone
        3. Sets up isolated filesystem sandbox (if filesystem enabled)
        4. Summarizes parent's conversation history using lightweight LLM
        5. Injects context briefing with parent summary and specific mission
        6. Spawns clone with full tool access including delegation and filesystem capabilities

        **Resource Management:**
        - Automatic cleanup: contexts closed and agents disposed after completion
        - Capacity enforcement: respects MAX_KAGEBUNSHIN_INSTANCES limit
        - Depth limiting: prevents infinite recursion (max depth: 3 levels)
        - Concurrent execution: all tasks run in parallel

        **Context Inheritance:**
        - Clones receive summarized conversation history from parent
        - Summary includes initial user request, key actions, and current status
        - Clone depth tracking prevents excessive nesting
        - Each clone can access group chat for coordination
        
        **Filesystem Sandbox Isolation:**
        - Each clone gets its own isolated filesystem sandbox directory
        - Sandbox structure: `main_sandbox/agent_parent/clones/agent_clone_name/`
        - Complete isolation prevents clones from accessing each other's files
        - Full filesystem capabilities: read, write, create, delete, list operations
        - Security restrictions apply: file size limits, extension filtering, path validation
        - Clones can create, organize, and manage their own file hierarchies

        ## Important Notes

        **Performance Considerations:**
        - Each clone uses significant resources (browser context + agent)
        - Monitor system resources when delegating many tasks
        - Consider task complexity vs. delegation overhead

        **Task Design Best Practices:**
        - Make tasks specific and actionable ("Research X" vs "Find information")
        - Ensure tasks are truly independent (no shared state requirements)
        - Include success criteria in task descriptions
        - Avoid tasks that require real-time coordination

        **Error Handling:**
        - Individual task failures don't affect other parallel tasks
        - Resource cleanup occurs even if tasks fail
        - Capacity limits enforced at both global and per-delegation level
        - Clone creation failures return structured error information

        ## Troubleshooting

        **"Delegation denied: max agents reached":**
        - System capacity limit hit, wait for other agents to complete
        - Reduce number of parallel tasks in delegation call
        - Consider sequential execution for some subtasks

        **"Maximum clone depth reached":**
        - Clone tried to create too many recursive sub-clones
        - Redesign task hierarchy to be shallower
        - Use direct tool calls instead of further delegation

        **Empty or malformed results:**
        - Check that tasks are specific and actionable
        - Verify URLs and target sites are accessible
        - Review task descriptions for clarity and feasibility

        ## Integration with Group Chat

        Clones automatically have access to post_groupchat tool for coordination:
        - Share progress updates between parallel tasks
        - Coordinate to avoid duplicate work
        - Alert parent agent of important findings
        - Request help from other agents in the swarm

        ## Advanced Patterns

        **Hierarchical Delegation:**
        - Parent delegates high-level tasks to clones
        - Each clone can further delegate specialized subtasks
        - Creates tree-like execution hierarchy
        - Automatic depth limiting prevents runaway recursion

        **Dynamic Task Adjustment:**
        - Monitor clone results and delegate additional tasks based on findings
        - Use group chat to coordinate dynamic task assignment
        - Implement feedback loops between parent and clones
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
            # Import here to avoid circular import
            from ..core.agent import KageBunshinAgent
            
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

                created_context = await browser.new_context(
                    permissions=DEFAULT_PERMISSIONS,
                    viewport={'width': ACTUAL_VIEWPORT_WIDTH, 'height': ACTUAL_VIEWPORT_HEIGHT}
                )
                try:
                    await apply_fingerprint_profile_to_context(created_context)
                except Exception:
                    pass

                child_name = generate_agent_name()
                clone_tools = get_additional_tools(created_context, username=child_name, group_room=group_room)
                
                # Create isolated filesystem sandbox for this clone
                # Each clone gets its own subdirectory to prevent interference
                clone_filesystem_enabled = FILESYSTEM_ENABLED
                clone_sandbox_base = None
                
                if FILESYSTEM_ENABLED:
                    try:
                        # Create clone-specific sandbox path: parent_sandbox/clones/clone_name
                        parent_sandbox = Path(FILESYSTEM_SANDBOX_BASE)
                        
                        # Get the parent agent's name from state for sandbox isolation
                        # This ensures each clone family has its own space
                        parent_agent_name = parent_name or "unknown_parent"
                        
                        # Create hierarchical sandbox structure: 
                        # main_sandbox/agent_parent/clones/clone_child_name
                        clone_sandbox_path = parent_sandbox / f"agent_{parent_agent_name}" / "clones" / f"agent_{child_name}"
                        clone_sandbox_base = str(clone_sandbox_path)
                        
                        logger.info(f"Clone {child_name} will use filesystem sandbox: {clone_sandbox_path}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to setup clone filesystem sandbox: {e}")
                        # Disable filesystem for this clone if setup fails
                        clone_filesystem_enabled = False
                
                try:
                    clone = await KageBunshinAgent.create(
                        created_context,
                        additional_tools=clone_tools,
                        group_room=group_room,
                        username=child_name,
                        enable_summarization=ENABLE_SUMMARIZATION,
                        clone_depth=current_depth + 1,
                        # Pass filesystem configuration to clone
                        filesystem_enabled=clone_filesystem_enabled,
                        filesystem_sandbox_base=clone_sandbox_base,
                    )
                except RuntimeError as e:
                    return {"task": task_str, "status": "denied", "error": f"Delegation denied: {e}"}

                # Create context-aware task message for the clone
                filesystem_status = "ENABLED" if clone_filesystem_enabled else "DISABLED"
                filesystem_info = ""
                if clone_filesystem_enabled and clone_sandbox_base:
                    filesystem_info = f"\n🗂️  FILESYSTEM: You have access to a private filesystem sandbox for reading, writing, and organizing files. All file operations are isolated to your sandbox for security."
                
                clone_context_message = f"""🧬 CLONE BRIEFING: You are a shadow clone of {parent_name} (Depth: {current_depth + 1})!

PARENT CONTEXT: {conversation_summary}

YOUR MISSION: {task_str}

🛠️  CAPABILITIES:
• DELEGATION: You have FULL delegation capabilities! Create your own clones if parallelization would help
• GROUP CHAT: Use post_groupchat tool to coordinate with parent and sibling agents
• WEB AUTOMATION: Full browser control for navigation, interaction, and data extraction{filesystem_info}

IMPORTANT: You are NOT limited by being a clone - the swarm intelligence philosophy applies at every level. Think strategically about when to parallelize vs. work sequentially.

Coordination Strategy: Share progress updates, coordinate to avoid duplicate work, and leverage collective intelligence through the group chat system."""

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
        """Post a message to the shared Agent Group Chat for multi-agent coordination and collaboration.

        This tool enables real-time communication between all Kagebunshin agents in the same group room,
        fostering emergent swarm intelligence behavior. Messages can be accessed by all agents for coordination, progress sharing, and collaborative problem-solving.

        ## Purpose & Use Cases

        **Coordination Scenarios:**
        - Share progress updates with parent agent and sibling clones
        - Alert other agents about important discoveries or findings
        - Request assistance with specific subtasks from available agents
        - Announce task completion or readiness for next phase
        - Coordinate to avoid duplicate work across parallel agents

        **Collaboration Benefits:**
        - Prevents redundant work when multiple agents have similar tasks
        - Enables knowledge sharing and collective intelligence
        - Allows dynamic task redistribution based on agent capabilities
        - Creates emergent coordination patterns without central control
        - Supports both reactive and proactive agent communication

        ## Arguments

        **message** (str, required):
        - The message content to broadcast to all agents in the group room
        - Should be concise but informative (other agents have limited context)
        - Include relevant context like URLs, findings, or specific needs
        - Use clear, actionable language that other agents can understand
        - Avoid overly long messages that clutter the group chat history

        ## Returns

        **Success response**: `"Posted to group chat ({room_name})"`
        **Error response**: `"Error posting to group chat: {error_details}"`

        Return value indicates whether the message was successfully posted to the group chat system.
        Failed posts don't interrupt agent execution but may affect coordination effectiveness.

        ## Behavior Details

        **Message Broadcasting:**
        - Messages are instantly available to all agents monitoring the same group room
        - Timestamp and sender information automatically attached to each message
        - Message history limited to recent entries to prevent memory bloat

        **Group Room Management:**
        - All agents in same session typically share the same group room
        - Room name configurable via environment variables or agent initialization
        - Default room is "lobby" unless specified otherwise
        - Cross-room communication not supported (agents isolated by room)

        ## Important Notes

        **Message Best Practices:**
        - Be specific about findings: "Found 15 relevant results on Site A" vs "Making progress"
        - Include actionable information: "Need help with CAPTCHA on login page"
        - Use consistent formatting for easier parsing by other agents
        - Mention specific URLs or resources when relevant

        ## Integration with Delegation

        **Parent-Clone Communication:**
        - Parent agents can broadcast task assignments or updates
        - Clone agents can report back completion status or issues
        - Enables dynamic task reallocation based on agent performance

        **Swarm Coordination:**
        - Multiple parallel clones can coordinate to avoid overlap
        - Emergent load balancing through voluntary task claiming
        - Collective intelligence through shared observations and findings

        ## Troubleshooting

        **"Error posting to group chat: connection failed":**
        - Redis server may be unavailable or misconfigured  
        - Check Redis connection settings in environment variables
        - Agent will continue functioning with in-memory fallback

        **Messages not appearing to other agents:**
        - Verify all agents are using the same group room name
        - Check Redis configuration consistency across agents
        - Ensure proper network connectivity between agents and Redis

        **Group chat history missing:**
        - Redis may have been restarted, clearing message history
        - In-memory fallback doesn't persist across agent restarts
        - Message history automatically trimmed to prevent memory issues

        ## Advanced Patterns

        **Conditional Broadcasting:**
        - Post updates only for significant findings or milestones
        - Use message priority levels for different types of communication
        - Implement message filtering based on agent roles or capabilities

        **Structured Communication:**
        - Use consistent message formats for easier automated processing
        - Implement message tagging for categorization
        - Create communication protocols for specific coordination scenarios
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

