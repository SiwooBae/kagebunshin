import asyncio
import dotenv
import os
from datetime import datetime
from typing import Optional
import logging
import argparse
from playwright.async_api import async_playwright

from ..config.settings import BROWSER_EXECUTABLE_PATH, USER_DATA_DIR, DEFAULT_PERMISSIONS, ACTUAL_VIEWPORT_WIDTH, ACTUAL_VIEWPORT_HEIGHT, ENABLE_SUMMARIZATION
from ..core.agent import KageBunshinAgent
from ..tools.delegation import get_additional_tools
from ..config.settings import GROUPCHAT_ROOM
from ..utils import generate_agent_name, normalize_chat_content
from ..automation.fingerprinting import get_stealth_browser_args, apply_fingerprint_profile_to_context

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


class KageBunshinRunner:
    """Simplified KageBunshin runner using the stateless orchestrator pattern"""

    def __init__(self):
        self.orchestrator: Optional[KageBunshinAgent] = None
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
        """Print the final answer with special formatting, supporting structured status indicators"""
        import textwrap
        import re
        
        # Check if answer has structured format [STATUS] or [STATUS] (confidence: XX%)
        status_pattern = r'^\[([A-Z]+)\](?:\s*\(confidence:\s*(\d+%)\))?\s*(.*)$'
        match = re.match(status_pattern, answer.strip(), re.DOTALL)
        
        if match:
            status, confidence, result = match.groups()
            
            # Status-specific formatting
            status_config = {
                "SUCCESS": ("🎯 TASK COMPLETED", Colors.OKGREEN, "🏁 MISSION ACCOMPLISHED"),
                "PARTIAL": ("⚠️  TASK PARTIALLY COMPLETED", Colors.WARNING, "📋 PARTIAL COMPLETION"),
                "FAILURE": ("❌ TASK FAILED", Colors.FAIL, "💥 EXECUTION FAILED"),
                "BLOCKED": ("🚫 TASK BLOCKED", Colors.FAIL, "🔒 ACCESS BLOCKED")
            }
            
            banner_text, color, completion_banner = status_config.get(
                status, ("🎯 TASK RESULT", Colors.OKGREEN, "🏁 TASK FINISHED")
            )
            
            self._print_banner(banner_text, color)
            
            # Print confidence if available
            if confidence:
                print(f"{color}{Colors.BOLD}Confidence: {confidence}{Colors.ENDC}")
                print()
            
            # Print result
            print(f"{color}{Colors.BOLD}")
            if result.strip():
                for line in textwrap.wrap(result.strip(), width=70):
                    print(f"  {line}")
            else:
                print("  No additional details provided.")
            print(f"{Colors.ENDC}")
            
            self._print_banner(completion_banner, color)
        else:
            # Legacy format - no structured status
            self._print_banner("🎯 FINAL ANSWER", Colors.OKGREEN)
            print(f"{Colors.OKGREEN}{Colors.BOLD}")
            for line in textwrap.wrap(answer.strip(), width=70):
                print(f"  {line}")
            print(f"{Colors.ENDC}")
            self._print_banner("🏁 MISSION COMPLETED", Colors.OKGREEN)

    async def run(self, user_query: str):
        """Run KageBunshin using the simplified stateless orchestrator approach"""
        self._print_banner("🌐 KageBunshin (Stateless Orchestrator)", Colors.HEADER)
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
                context = await browser.new_context(
                    permissions=DEFAULT_PERMISSIONS,
                    viewport={'width': ACTUAL_VIEWPORT_WIDTH, 'height': ACTUAL_VIEWPORT_HEIGHT}
                )

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
            self.orchestrator = await KageBunshinAgent.create(
                context,
                additional_tools=extra_tools,
                group_room=GROUPCHAT_ROOM,
                username=agent_name,
                enable_summarization=ENABLE_SUMMARIZATION,
            )
            self._print_step("INIT", "Stateless KageBunshin Orchestrator created successfully!", Colors.OKGREEN)
            self._print_step("INIT", "Starting web automation with stateless ReAct agent...", Colors.OKCYAN)

            try:
                self._print_step("PHASE", "Starting streaming automation...", Colors.OKCYAN)
                last_agent_message = ""

                async for chunk in self.orchestrator.astream(user_query):
                    # Agent outputs
                    if 'agent' in chunk:
                        for msg in chunk['agent'].get('messages', []):
                            if hasattr(msg, 'content') and msg.content:
                                content = normalize_chat_content(msg.content)
                                last_agent_message = content
                                self._print_step('MESSAGE', f"Agent: {content}", Colors.OKBLUE)
                            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                for call in msg.tool_calls:
                                    name = call.get('name', 'unknown')
                                    args = call.get('args', {})
                                    self._print_step('TOOL', f"{name}({args})", Colors.WARNING)
                    # Tool results (normalized)
                    if 'tools' in chunk:
                        for evt in chunk['tools']:
                            name = evt.get('name', 'tool')
                            args = evt.get('args')
                            result = evt.get('result', '')
                            args_str = f"{args}" if args is not None else "{}"
                            self._print_step('OBSERVATION', f"{name}{args_str} -> {result}", Colors.OKCYAN)
                    # Summarizer messages
                    if 'summarizer' in chunk:
                        for msg in chunk['summarizer'].get('messages', []):
                            if hasattr(msg, 'content') and msg.content:
                                self._print_step('MESSAGE', normalize_chat_content(msg.content), Colors.OKBLUE)

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
        self._print_banner("🌐 KageBunshin (Stateful Session)", Colors.HEADER)
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
                context = await browser.new_context(
                    permissions=DEFAULT_PERMISSIONS,
                    viewport={'width': ACTUAL_VIEWPORT_WIDTH, 'height': ACTUAL_VIEWPORT_HEIGHT}
                )

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
            self.orchestrator = await KageBunshinAgent.create(
                context,
                additional_tools=extra_tools,
                group_room=GROUPCHAT_ROOM,
                username=agent_name,
            )
            self._print_step("INIT", "Stateful KageBunshin Orchestrator created successfully!", Colors.OKGREEN)
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
                                    content = normalize_chat_content(msg.content)
                                    last_agent_message = content
                                    self._print_step('MESSAGE', f"Agent: {content}", Colors.OKBLUE)
                                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                    for call in msg.tool_calls:
                                        name = call.get('name', 'unknown')
                                        args = call.get('args', {})
                                        self._print_step('TOOL', f"{name}({args})", Colors.WARNING)
                        # Tool results (normalized)
                        if 'tools' in chunk:
                            for evt in chunk['tools']:
                                name = evt.get('name', 'tool')
                                args = evt.get('args')
                                result = evt.get('result', '')
                                args_str = f"{args}" if args is not None else "{}"
                                self._print_step('OBSERVATION', f"{name}{args_str} -> {result}", Colors.OKCYAN)
                        if 'summarizer' in chunk:
                            for msg in chunk['summarizer'].get('messages', []):
                                if hasattr(msg, 'content') and msg.content:
                                    self._print_step('MESSAGE', normalize_chat_content(msg.content), Colors.OKBLUE)

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


# CLI entry point
async def main(user_query:str) -> None:
    dotenv.load_dotenv()
    # One-shot mode (classic colored stream)
    if not user_query:
        user_query = "Open google.com and summarize the page"
    runner = KageBunshinRunner()
    await runner.run(user_query)

def _resolve_query_from_file(file_ref: str) -> str:
    """Resolve a markdown file reference to its content.
    
    Args:
        file_ref: File reference like @kagebunshin/config/prompts/useful_query_templates/literature_review.md
    
    Returns:
        The content of the markdown file
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the reference format is invalid
    """
    if not file_ref.startswith('@'):
        raise ValueError("File reference must start with @")
    
    # Remove @ prefix and resolve path
    relative_path = file_ref[1:]
    
    # Get the current file's directory to resolve relative paths
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(current_dir, relative_path)
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if not file_path.endswith('.md'):
        raise ValueError("Referenced file must be a markdown file (.md)")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def run() -> None:
    """Synchronous entry point for console_scripts."""
    parser = argparse.ArgumentParser(prog="kagebunshin", description="AI web automation agent")
    parser.add_argument("query", nargs="?", help="User task for the agent to execute")
    parser.add_argument("-r", "--reference", help="Reference a markdown file using @path/to/file.md syntax")
    parser.add_argument("--repl", action="store_true", help="Run classic colored stream with persistent memory (REPL)")
    args = parser.parse_args()
    
    # Handle file reference
    query = args.query
    if args.reference:
        try:
            file_content = _resolve_query_from_file(args.reference)
            if query:
                # Combine query with file content
                query = f"{query}\n\nReferenced content from {args.reference}:\n\n{file_content}"
            else:
                # Use file content as the query
                query = file_content
        except (FileNotFoundError, ValueError) as e:
            print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")
            return
    
    if args.repl:
        # Classic colored stream with persistent memory
        asyncio.run(KageBunshinRunner().run_loop(query or None, thread_id="cli-session"))
    else:
        asyncio.run(main(query))