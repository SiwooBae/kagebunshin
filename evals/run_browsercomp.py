import os
import argparse
import asyncio
import importlib.util
from pathlib import Path
from datetime import datetime

# Load BrowseCompEval dynamically because filename has a hyphen
_BROWSECOMP_PATH = Path(__file__).with_name("browsercomp-eval.py")
_spec = importlib.util.spec_from_file_location("evals.browsercomp_eval", str(_BROWSECOMP_PATH))
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load BrowseComp module from {_BROWSECOMP_PATH}")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
BrowseCompEval = getattr(_mod, "BrowseCompEval")

from .common import make_report
from .types import SamplerBase, SamplerResponse, Message, MessageList

from kagebunshin.config import settings
from kagebunshin.core.agent import KageBunshinAgent
from kagebunshin.tools.delegation import get_additional_tools
from kagebunshin.utils import generate_agent_name
from kagebunshin.automation.fingerprinting import (
    get_stealth_browser_args,
    apply_fingerprint_profile_to_context,
)

from langchain.chat_models.base import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from playwright.async_api import async_playwright


class ChatModelSampler(SamplerBase):
    """Simple LLM-backed sampler (used for grading)."""

    def __init__(self, model: str, provider: str, temperature: float = 0.2):
        self.model = init_chat_model(
            model=model,
            model_provider=provider,
            temperature= 1 if "gpt-5" in model else temperature,
        )

    def _pack_message(self, content: str, role: str = "user") -> Message:
        return {"content": content, "role": role}

    def __call__(self, message_list: MessageList) -> SamplerResponse:
        lc_messages = []
        for m in message_list:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        response = self.model.invoke(lc_messages)
        text = getattr(response, "content", "")
        return SamplerResponse(
            response_text=str(text),
            actual_queried_message_list=message_list,
            response_metadata={"model": self.model},
        )


class KagebunshinSampler(SamplerBase):
    """Adapter that runs a Kagebunshin browsing agent to answer prompts."""

    def __init__(self, headless: bool = True, browser: str = "chrome"):
        self.headless = headless
        self.browser = browser  # "chromium" or "chrome"

    def _pack_message(self, content: str, role: str = "user") -> Message:
        return {"content": content, "role": role}

    def __call__(self, message_list: MessageList) -> SamplerResponse:
        # Use the last user message as the task
        user_msgs = [m for m in message_list if m.get("role") == "user"]
        prompt = user_msgs[-1]["content"] if user_msgs else message_list[-1]["content"]

        text = asyncio.run(self._run_once(prompt))
        return SamplerResponse(
            response_text=text,
            actual_queried_message_list=message_list,
            response_metadata={"headless": self.headless, "browser": self.browser},
        )

    async def _run_once(self, prompt: str) -> str:
        launch_options = {
            "headless": self.headless,
            "args": get_stealth_browser_args(),
            "ignore_default_args": ["--enable-automation"],
        }

        # Prefer explicit executable if configured
        if settings.BROWSER_EXECUTABLE_PATH:
            launch_options["executable_path"] = settings.BROWSER_EXECUTABLE_PATH

        async with async_playwright() as p:
            browser_launcher = p.chromium
            # Only use Chrome channel if explicitly requested and no custom executable
            if self.browser == "chrome" and not settings.BROWSER_EXECUTABLE_PATH:
                launch_options["channel"] = "chrome"

            browser = await browser_launcher.launch(**launch_options)
            context = await browser.new_context(permissions=settings.DEFAULT_PERMISSIONS,
                                                viewport={'width': settings.ACTUAL_VIEWPORT_WIDTH, 'height': settings.ACTUAL_VIEWPORT_HEIGHT})

            # Apply fingerprint hardening at the context level
            try:
                profile = await apply_fingerprint_profile_to_context(context)
                try:
                    await context.add_init_script(
                        f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{profile['user_agent']}' }});"
                    )
                except Exception:
                    pass
            except Exception:
                pass

            try:
                agent_name = generate_agent_name()
                extra_tools = get_additional_tools(context, username=agent_name, group_room=settings.GROUPCHAT_ROOM)
                orchestrator = await KageBunshinAgent.create(
                    context,
                    additional_tools=extra_tools,
                    group_room=settings.GROUPCHAT_ROOM,
                    username=agent_name,
                    enable_summarization=settings.ENABLE_SUMMARIZATION,
                )
                # Let the orchestrator browse and answer
                result_text = await orchestrator.ainvoke(prompt)
                return result_text
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass


def main():
    # Disable multithreading in the eval loop by default to avoid Playwright conflicts
    os.environ.setdefault("debug", "1")

    parser = argparse.ArgumentParser(description="Run BrowseComp on Kagebunshin")
    parser.add_argument("--num-examples", type=int, default=None, help="Sample N examples (defaults to all)")
    parser.add_argument("--n-repeats", type=int, default=1, help="Repeat each example N times")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--browser", choices=["chromium", "chrome"], default="chrome")
    parser.add_argument("--grader-model", type=str, default="gpt-5")
    parser.add_argument("--grader-provider", type=str, default="openai")
    parser.add_argument("--report", type=str, default=None, help="Path to save HTML report")
    args = parser.parse_args()

    # Build grader and sampler
    grader = ChatModelSampler(model=args.grader_model, provider=args.grader_provider)
    sampler = KagebunshinSampler(headless=args.headless, browser=args.browser)

    eval_runner = BrowseCompEval(grader_model=grader, num_examples=args.num_examples, n_repeats=args.n_repeats)
    result = eval_runner(sampler)

    # Print key metrics to stdout
    print("\n==== Final Metrics ====")
    if result.metrics:
        for k, v in result.metrics.items():
            print(f"{k}: {v}")
    if result.score is not None:
        print(f"score: {result.score}")

    # Optionally write an HTML report
    out_path = args.report
    if not out_path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = os.path.join(os.getcwd(), "runs")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"browsecomp-report-{ts}.html")
    else:
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    html = make_report(result)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()


