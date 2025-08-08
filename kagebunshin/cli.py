import os
import sys
import argparse
import asyncio
import logging
from typing import Optional, AsyncGenerator
from datetime import datetime

from playwright.async_api import async_playwright
import dotenv

from .config import BROWSER_EXECUTABLE_PATH, USER_DATA_DIR, DEFAULT_PERMISSIONS
from .webvoyager_v2 import WebVoyagerV2
from .additional_tools import get_additional_tools
from .fingerprint_evasion import get_stealth_browser_args, apply_fingerprint_profile_to_context
from .main import WebVoyagerRunner


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _create_orchestrator():
    """Create Playwright context and orchestrator once for reuse in chat mode."""
    async_playwright_ctx = await async_playwright().start()
    launch_options = {
        "headless": False,
        "args": get_stealth_browser_args(),
        "ignore_default_args": ["--enable-automation"],
    }
    if BROWSER_EXECUTABLE_PATH:
        launch_options["executable_path"] = BROWSER_EXECUTABLE_PATH
    else:
        launch_options["channel"] = "chrome"

    if USER_DATA_DIR:
        ctx_dir = os.path.expanduser(USER_DATA_DIR)
        context = await async_playwright_ctx.chromium.launch_persistent_context(
            ctx_dir,
            **launch_options,
            permissions=DEFAULT_PERMISSIONS,
        )
    else:
        browser = await async_playwright_ctx.chromium.launch(**launch_options)
        context = await browser.new_context(permissions=DEFAULT_PERMISSIONS)

    profile = await apply_fingerprint_profile_to_context(context)
    try:
        await context.add_init_script(
            f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{profile['user_agent']}' }});"
        )
    except Exception:
        pass

    # Provide additional tools (including delegate) to the orchestrator
    extra_tools = get_additional_tools(context)
    orchestrator = await WebVoyagerV2.create(context, additional_tools=extra_tools)
    return async_playwright_ctx, orchestrator


async def main(user_query: Optional[str] = None, chat: bool = False) -> None:
    dotenv.load_dotenv()
    # One-shot mode (classic colored stream)
    if not user_query:
        user_query = "Open google.com and summarize the page"
    runner = WebVoyagerRunner()
    await runner.run(user_query)


def run() -> None:
    """Synchronous entry point for console_scripts."""
    parser = argparse.ArgumentParser(prog="kagebunshin", description="AI web automation agent")
    parser.add_argument("query", nargs="?", help="User task for the agent to execute")
    parser.add_argument("--chat", action="store_true", help="Launch interactive chat UI")
    parser.add_argument("--repl", action="store_true", help="Run classic colored stream with persistent memory (REPL)")
    args = parser.parse_args()
    if args.repl:
        # Classic colored stream with persistent memory
        asyncio.run(WebVoyagerRunner().run_loop(args.query or None, thread_id="cli-session"))
    else:
        asyncio.run(main(args.query, chat=args.chat))

