"""
Additional tools for Kagebunshin.

Includes a "delegate" tool that spawns a shadow-clone sub-agent to handle
focused subtasks. The clone runs on the same Playwright BrowserContext,
optionally in a new tab, and returns its final answer to the caller.
"""

from typing import Any, List, Optional
import logging

from langchain_core.tools import tool
from playwright.async_api import BrowserContext

from .webvoyager_v2 import WebVoyagerV2
from .fingerprint_evasion import apply_fingerprint_profile, apply_fingerprint_profile_to_context
from .config import DEFAULT_PERMISSIONS


logger = logging.getLogger(__name__)


def get_additional_tools(context: BrowserContext) -> List[Any]:
    """
    Construct additional tools bound to a specific BrowserContext.

    The returned tools can be passed into `WebVoyagerV2.create(..., additional_tools=...)`.
    """

    @tool
    async def delegate(
        task: str,
        url: Optional[str] = None,
        spawn: str = "context",
        close_on_finish: bool = False,
    ) -> str:
        """Spawn a shadow-clone sub-agent to execute a focused subtask and return its result.

        Args:
            task: The subtask to execute (e.g., "open example.com and extract the support email").
            url: Optional URL to open for the clone before starting the subtask.
            spawn: Where to run the clone. "context" creates a brand new BrowserContext (preferred). "tab" opens a new tab in the current context.
            close_on_finish: Whether to close the created context/tab after the clone completes.

        Behavior:
            - "context": Creates a fresh incognito BrowserContext via the current Browser (best isolation).
            - "tab": Opens a new tab in the current context (shares storage/session).
            - Runs a fresh orchestrator instance to handle `task` and returns its final answer string.
        """
        created_context = None
        new_page = None
        try:
            if spawn == "context":
                # Try to obtain the Browser and create a new context from it
                browser = getattr(context, "browser", None)
                if browser is None:
                    # Fallback: cannot create a new context without a Browser handle
                    # Use a new tab instead
                    spawn = "tab"
                else:
                    created_context = await browser.new_context(permissions=DEFAULT_PERMISSIONS)
                    # Apply fingerprint profile and align UA/overrides
                    try:
                        await apply_fingerprint_profile_to_context(created_context)
                    except Exception:
                        pass
                    # Optionally navigate to a starting URL
                    if url:
                        new_page = await created_context.new_page()
                        if not url.startswith(("http://", "https://")):
                            url = "https://" + url
                        await new_page.goto(url)
            
            if spawn == "tab":
                new_page = await context.new_page()
                try:
                    await apply_fingerprint_profile(new_page)
                except Exception:
                    pass
                if url:
                    if not url.startswith(("http://", "https://")):
                        url = "https://" + url
                    await new_page.goto(url)
                try:
                    await new_page.bring_to_front()
                except Exception:
                    pass

            # Choose which context to give to the clone
            target_context = created_context if created_context else context
            # Give the clone the same additional toolset so it can delegate further if needed
            clone_tools = get_additional_tools(target_context)
            clone = await WebVoyagerV2.create(target_context, additional_tools=clone_tools)
            result = await clone.ainvoke(task)

            return f"[DELEGATE RESULT]\n{result}"
        except Exception as e:
            logger.error(f"Delegate tool failed: {e}")
            return f"Error during delegation: {str(e)}"
        finally:
            if new_page and close_on_finish:
                try:
                    await new_page.close()
                except Exception:
                    pass
            if created_context and close_on_finish:
                try:
                    await created_context.close()
                except Exception:
                    pass

    return [delegate]

