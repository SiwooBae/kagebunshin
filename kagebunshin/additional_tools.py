"""
Additional tools for Kagebunshin.

Includes a "delegate" tool that spawns shadow-clone sub-agents to handle
focused subtasks. Each clone runs in a fresh, isolated Playwright BrowserContext
and returns its final answer to the caller.
"""

from typing import Any, List, Optional
import logging
import asyncio
import json

from langchain_core.tools import tool
from playwright.async_api import BrowserContext

from .kagebunshin_agent import KageBunshinAgent
from .fingerprint_evasion import apply_fingerprint_profile_to_context
from .config import DEFAULT_PERMISSIONS, GROUPCHAT_ROOM, MAX_KageBunshin_INSTANCES
from .group_chat import GroupChatClient
from .utils import generate_agent_name


logger = logging.getLogger(__name__)


def get_additional_tools(context: BrowserContext, username: Optional[str] = None, group_room: Optional[str] = None) -> List[Any]:
    """
    Construct additional tools bound to a specific BrowserContext.

    The returned tools can be passed into `KageBunshinV2.create(..., additional_tools=...)`.
    """

    chat_client = GroupChatClient()

    @tool
    async def delegate(tasks: List[str]) -> str:
        """Spawn shadow-clone sub-agents in parallel to execute multiple focused subtasks.

        Args:
            tasks: List of subtasks to execute. One clone is spawned per task.

        Behavior:
            - Always creates a fresh incognito BrowserContext per task (best isolation).
            - No initial URL is opened automatically.
            - Returns a JSON array of {"task", "status", "result"|"error"} as a string.
            - Resources are closed automatically after each clone finishes.
        """

        if not tasks or not isinstance(tasks, list):
            return json.dumps({"error": "'tasks' must be a non-empty list of strings"})

        async def run_single_task(task_str: str) -> dict:
            created_context = None
            clone: Optional[KageBunshinAgent] = None
            try:
                # Capacity check (best-effort; create() also enforces)
                if KageBunshinAgent._INSTANCE_COUNT >= MAX_KageBunshin_INSTANCES:
                    return {
                        "task": task_str,
                        "status": "denied",
                        "error": f"Delegation denied: max agents reached ({MAX_KageBunshin_INSTANCES}).",
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
                    )
                except RuntimeError as e:
                    return {"task": task_str, "status": "denied", "error": f"Delegation denied: {e}"}

                result = await clone.ainvoke(task_str)
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

