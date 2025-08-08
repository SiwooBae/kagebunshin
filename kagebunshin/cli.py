import os
import sys
import argparse
import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright
import dotenv

from .config import BROWSER_EXECUTABLE_PATH, USER_DATA_DIR, DEFAULT_PERMISSIONS
from .webvoyager_v2 import WebVoyagerV2
from .fingerprint_evasion import get_stealth_browser_args, apply_fingerprint_profile_to_context


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main(user_query: Optional[str] = None) -> None:
    dotenv.load_dotenv()
    if not user_query:
        # default minimal query
        user_query = "Open google.com and summarize the page"

    async with async_playwright() as p:
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
            context = await p.chromium.launch_persistent_context(
                ctx_dir,
                **launch_options,
                permissions=DEFAULT_PERMISSIONS,
            )
        else:
            browser = await p.chromium.launch(**launch_options)
            context = await browser.new_context(permissions=DEFAULT_PERMISSIONS)

        profile = await apply_fingerprint_profile_to_context(context)
        try:
            await context.add_init_script(
                f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{profile['user_agent']}' }});"
            )
        except Exception:
            pass

        orchestrator = await WebVoyagerV2.create(context)

        async for chunk in orchestrator.astream(user_query):
            if 'agent' in chunk:
                for msg in chunk['agent'].get('messages', []):
                    if getattr(msg, 'content', None):
                        print(str(msg.content))


def run() -> None:
    """Synchronous entry point for console_scripts."""
    parser = argparse.ArgumentParser(prog="kagebunshin", description="AI web automation agent")
    parser.add_argument("query", nargs="?", help="User task for the agent to execute")
    args = parser.parse_args()
    asyncio.run(main(args.query))

