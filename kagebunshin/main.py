import asyncio
import dotenv
import os
from datetime import datetime
from typing import Optional
import logging

from playwright.async_api import async_playwright

from .config import BROWSER_EXECUTABLE_PATH, USER_DATA_DIR, DEFAULT_PERMISSIONS
from .webvoyager_v2 import WebVoyagerV2
from .additional_tools import get_additional_tools
from .config import GROUPCHAT_ROOM
from .utils import generate_agent_name
from .fingerprint_evasion import get_stealth_browser_args, apply_fingerprint_profile_to_context

# enable logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class WebVoyagerRunner:
    """Simplified WebVoyager runner using the stateless orchestrator pattern"""

    def __init__(self):
        self.orchestrator: Optional[WebVoyagerV2] = None
        self.step_count = 0

    def _get_timestamp(self) -> str:
        """Get current timestamp for logging"""
        return datetime.now().strftime("%H:%M:%S")

    def _print_banner(self, text: str, color: str = Colors.HEADER) -> None:
        """Print a banner with decorative border"""
        border = "=" * (len(text) + 4)
        print(f"\n{color}{border}")
        print(f"  {text}")
        print(f"{border}{Colors.ENDC}")

    def _print_step(self, step_type: str, content: str, color: str = Colors.OKBLUE) -> None:
        """Print a formatted step with timestamp and emoji"""
        timestamp = self._get_timestamp()
        self.step_count += 1
        emoji_map = {
            "INIT": "🚀",
            "TOOL": "🔧",
            "MESSAGE": "💬",
            "ANSWER": "✅",
            "ERROR": "❌",
            "PHASE": "📋",
            "OBSERVATION": "👀",
            "DIALOG": "📢",
            "SUCCESS": "🎯",
        }
        emoji = emoji_map.get(step_type, "📝")
        print(f"{color}[{timestamp}] {emoji} Step {self.step_count}: {step_type}{Colors.ENDC}")
        for line in content.splitlines():
            if line.strip():
                print(f"    {line}")
        print()

    def _print_final_answer(self, answer: str) -> None:
        """Print the final answer with special formatting"""
        self._print_banner("🎯 FINAL ANSWER", Colors.OKGREEN)
        print(f"{Colors.OKGREEN}{Colors.BOLD}")
        import textwrap
        for line in textwrap.wrap(answer.strip(), width=70):
            print(f"  {line}")
        print(f"{Colors.ENDC}")
        self._print_banner("🏁 MISSION COMPLETED", Colors.OKGREEN)

    async def run(self, user_query: str, thread_id: Optional[str] = None):
        """Run WebVoyager using the simplified stateless orchestrator approach"""
        self._print_banner("🌐 WebVoyager V2 (Stateless Orchestrator)", Colors.HEADER)
        print(f"{Colors.OKCYAN}Query: {Colors.BOLD}{user_query}{Colors.ENDC}\n")

        async with async_playwright() as p:
            self._print_step("INIT", "Launching browser...", Colors.WARNING)
            launch_options = {
                "headless": False,
                "args": get_stealth_browser_args(),
                # Mask playwright defaults like --enable-automation
                "ignore_default_args": ["--enable-automation"],
            }
            if BROWSER_EXECUTABLE_PATH:
                self._print_step("INIT", f"Using executable: {BROWSER_EXECUTABLE_PATH}", Colors.WARNING)
                launch_options["executable_path"] = BROWSER_EXECUTABLE_PATH
            else:
                self._print_step("INIT", "Using channel: chrome", Colors.WARNING)
                launch_options["channel"] = "chrome"

            if USER_DATA_DIR:
                self._print_step("INIT", f"Using persistent context from: {USER_DATA_DIR}", Colors.WARNING)
                ctx_dir = os.path.expanduser(USER_DATA_DIR)
                context = await p.chromium.launch_persistent_context(
                    ctx_dir,
                    **launch_options,
                    permissions=DEFAULT_PERMISSIONS,
                )
            else:
                browser = await p.chromium.launch(**launch_options)
                context = await browser.new_context(permissions=DEFAULT_PERMISSIONS)

            # Apply context-level fingerprinting overrides early
            profile = await apply_fingerprint_profile_to_context(context)
            # Align UA/locale/timezone in context options when feasible
            try:
                await context.add_init_script(f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{profile['user_agent']}' }});")
            except Exception:
                pass

            # Initialize orchestrator with additional tools (including delegate) and group chat identity
            agent_name = generate_agent_name()
            extra_tools = get_additional_tools(context, username=agent_name, group_room=GROUPCHAT_ROOM)
            self.orchestrator = await WebVoyagerV2.create(
                context,
                additional_tools=extra_tools,
                group_room=GROUPCHAT_ROOM,
                username=agent_name,
                enable_summarization=False,
            )
            self._print_step("INIT", "Stateless WebVoyager Orchestrator created successfully!", Colors.OKGREEN)
            self._print_step("INIT", "Starting web automation with stateless ReAct agent...", Colors.OKCYAN)

            try:
                self._print_step("PHASE", "Starting streaming automation...", Colors.OKCYAN)
                last_agent_message = ""

                async for chunk in self.orchestrator.astream(user_query):
                    # Agent outputs
                    if 'agent' in chunk:
                        for msg in chunk['agent'].get('messages', []):
                            if hasattr(msg, 'content') and msg.content:
                                content = str(msg.content)
                                last_agent_message = content
                                self._print_step('MESSAGE', f"Agent: {content}", Colors.OKBLUE)
                            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                for call in msg.tool_calls:
                                    name = call.get('name', 'unknown')
                                    args = call.get('args', {})
                                    self._print_step('TOOL', f"{name}({args})", Colors.WARNING)
                    # Summarizer messages
                    if 'summarizer' in chunk:
                        for msg in chunk['summarizer'].get('messages', []):
                            if hasattr(msg, 'content') and msg.content:
                                self._print_step('MESSAGE', str(msg.content), Colors.OKBLUE)

                # Final output
                if last_agent_message:
                    self._print_final_answer(last_agent_message)
                    # Print stats
                    current_url = await self.orchestrator.get_current_url()
                    current_title = await self.orchestrator.get_current_title()
                    action_count = self.orchestrator.get_action_count()
                    self._print_step('SUCCESS', f"Final URL: {current_url}", Colors.OKGREEN)
                    self._print_step('SUCCESS', f"Final Page: {current_title}", Colors.OKGREEN)
                    self._print_step('SUCCESS', f"Actions Performed: {action_count}", Colors.OKGREEN)
                else:
                    # Fallback: try to extract from final state
                    try:
                        extracted = self.orchestrator._extract_final_answer()  # type: ignore[attr-defined]
                        if extracted:
                            self._print_final_answer(extracted)
                        else:
                            self._print_step('ERROR', "No final answer was provided.", Colors.FAIL)
                    except Exception:
                        self._print_step('ERROR', "No final answer was provided.", Colors.FAIL)

            except Exception as e:
                self._print_step('ERROR', f"An error occurred: {e}", Colors.FAIL)
                import traceback
                traceback.print_exc()

    async def run_loop(self, first_query: Optional[str] = None, thread_id: str = "session") -> None:
        """Interactive loop with colored streaming and persistent memory.

        Keeps a single Playwright context and orchestrator alive, passing a stable
        thread_id so the LangGraph MemorySaver preserves message history across turns.
        Type an empty line or /exit to quit.
        """
        self._print_banner("🌐 WebVoyager V2 (Stateful Session)", Colors.HEADER)
        if first_query:
            print(f"{Colors.OKCYAN}First Query: {Colors.BOLD}{first_query}{Colors.ENDC}\n")

        async with async_playwright() as p:
            self._print_step("INIT", "Launching browser...", Colors.WARNING)
            launch_options = {
                "headless": False,
                "args": get_stealth_browser_args(),
                "ignore_default_args": ["--enable-automation"],
            }
            if BROWSER_EXECUTABLE_PATH:
                self._print_step("INIT", f"Using executable: {BROWSER_EXECUTABLE_PATH}", Colors.WARNING)
                launch_options["executable_path"] = BROWSER_EXECUTABLE_PATH
            else:
                self._print_step("INIT", "Using channel: chrome", Colors.WARNING)
                launch_options["channel"] = "chrome"

            if USER_DATA_DIR:
                self._print_step("INIT", f"Using persistent context from: {USER_DATA_DIR}", Colors.WARNING)
                ctx_dir = os.path.expanduser(USER_DATA_DIR)
                context = await p.chromium.launch_persistent_context(
                    ctx_dir,
                    **launch_options,
                    permissions=DEFAULT_PERMISSIONS,
                )
            else:
                browser = await p.chromium.launch(**launch_options)
                context = await browser.new_context(permissions=DEFAULT_PERMISSIONS)

            # Apply context-level fingerprinting overrides early
            profile = await apply_fingerprint_profile_to_context(context)
            try:
                await context.add_init_script(
                    f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{profile['user_agent']}' }});")
            except Exception:
                pass

            # Initialize orchestrator once for the session (preserves MemorySaver) with group chat identity
            agent_name = generate_agent_name()
            extra_tools = get_additional_tools(context, username=agent_name, group_room=GROUPCHAT_ROOM)
            self.orchestrator = await WebVoyagerV2.create(
                context,
                additional_tools=extra_tools,
                group_room=GROUPCHAT_ROOM,
                username=agent_name,
            )
            self._print_step("INIT", "Stateful WebVoyager Orchestrator created successfully!", Colors.OKGREEN)
            self._print_step("INIT", f"Session thread: {thread_id}", Colors.OKCYAN)

            try:
                # Inner function to process a single turn
                async def process_turn(prompt_text: str) -> None:
                    self._print_step("PHASE", "Starting streaming automation...", Colors.OKCYAN)
                    last_agent_message = ""
                    async for chunk in self.orchestrator.astream(prompt_text):
                        if 'agent' in chunk:
                            for msg in chunk['agent'].get('messages', []):
                                if hasattr(msg, 'content') and msg.content:
                                    content = str(msg.content)
                                    last_agent_message = content
                                    self._print_step('MESSAGE', f"Agent: {content}", Colors.OKBLUE)
                                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                    for call in msg.tool_calls:
                                        name = call.get('name', 'unknown')
                                        args = call.get('args', {})
                                        self._print_step('TOOL', f"{name}({args})", Colors.WARNING)
                        if 'summarizer' in chunk:
                            for msg in chunk['summarizer'].get('messages', []):
                                if hasattr(msg, 'content') and msg.content:
                                    self._print_step('MESSAGE', str(msg.content), Colors.OKBLUE)

                    if last_agent_message:
                        self._print_final_answer(last_agent_message)
                        current_url = await self.orchestrator.get_current_url()
                        current_title = await self.orchestrator.get_current_title()
                        action_count = self.orchestrator.get_action_count()
                        self._print_step('SUCCESS', f"Final URL: {current_url}", Colors.OKGREEN)
                        self._print_step('SUCCESS', f"Final Page: {current_title}", Colors.OKGREEN)
                        self._print_step('SUCCESS', f"Actions Performed: {action_count}", Colors.OKGREEN)
                    else:
                        try:
                            extracted = self.orchestrator._extract_final_answer()  # type: ignore[attr-defined]
                            if extracted:
                                self._print_final_answer(extracted)
                            else:
                                self._print_step('ERROR', "No final answer was provided.", Colors.FAIL)
                        except Exception:
                            self._print_step('ERROR', "No final answer was provided.", Colors.FAIL)

                # Run first turn if provided
                if first_query:
                    await process_turn(first_query)

                # REPL for subsequent turns with preserved memory
                while True:
                    # Non-blocking input in async context
                    loop = asyncio.get_running_loop()
                    next_prompt = await loop.run_in_executor(None, lambda: input("You> ").strip())
                    if not next_prompt or next_prompt.lower() in {"/exit", "quit", "q"}:
                        break
                    await process_turn(next_prompt)

            except Exception as e:
                self._print_step('ERROR', f"An error occurred: {e}", Colors.FAIL)
                import traceback
                traceback.print_exc()

async def main():
    """Main function"""
    runner = WebVoyagerRunner()
    
    today = datetime.now().strftime("%Y-%m-%d")
    url_list = [
        # "https://www.airrosti.com/schedule-appointment/",
        # "https://www.riveroakspt.com",
        "https://www.elationpt.com",
        "https://www.twofrontteethdds.com", # success
        "https://www.troothandsmiles.com/?utm_source=google&utm_medium=organic&utm_campaign=gbp-listing", # failure
        "https://dentistryofnashville.com",
        "https://www.fwdentalarts.com",
        "https://www.lyonprimarycare.com/?utm_source=gmb_auth",
        "https://www.familymedicinenyc.com/?utm_source=gmb_auth",
        "https://citycarefamilypractice.com"
    ]
    
    # for url in url_list:
#     query = f"""You are now a seasoned tech journalist. Here's what you need to do:
# 1. Literature Review Phase: Check what has been covered in the latest tech industry. This involves checking out the latest news on Google News, The Verge, TechCrunch, etc. This is for you to understand what is covered and what isn't yet.
# 2. Novelty Mining Phase: You will need to find something that has not been covered yet. You want to be on the cutting edge of it. Do anything necessary to achieve this goal.
# 3. Once you think you have enough information, write a blog post in markdown format and end the process.
# """

    query = f"""Use FairHealthConsumer to find whether getting billed $2000 for a colonoscopy in Manhattan, NY is normal.
"""

    await runner.run(query)


if __name__ == "__main__":
    asyncio.run(main())