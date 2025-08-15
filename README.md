## Kagebunshin🍥

Introducing Kagebunshin: a web-browsing, research focused agent swarm. With the recent release of GPT-5, GPT-5-mini, GPT-5-nano, this system has finally become economically viable.

### Q&A

Q: What does it do?

It works very similar to how ChatGPT agent functions. On top of it, it comes with additional features:
- cloning itself and navigate multiple branches simultaneously
- ⁠communicating with each other with the group chat feature: agents can “post” what they are working on their internal group chat, so that there is no working on the same thing, and encourage emergent behaviors.

Q: Why now?

While everyone is focusing on GPT-5’s performance, I looked at GPT-5-nano’s. It matches or even outperforms previous gpt-4.1-mini, at the x5-10 less cost. This means we can use 5 parallel agents with nano with the same cost of running 1 agent with 4.1 mini. As far as I know, GPT agent runs on gpt-4.1-mini (now they must have updated it, right?). This implies, this can be extremely useful when you need quantity over quality, such as data collection, scraping, etc.

Q: Limitations?
1. it is a legion of “dumber” agents. While it can do dumb stuff like aggregating and collecting data, but coming up with novel conclusion must not be done by this guy. We can instead let smarter GPT to do the synthesis.
2. Scalability: On my laptop it works just as fine. However, we don’t know what kind of devils are hiding in the details if we want to scale this up. I have set up comprehensive bot detection evasion, but it might not be enough when it becomes a production level scale.

Please let me know if you have any questions or comments. Thank you!

### Features
- Self-cloning (Hence the name, lol) for parallelized execution
- "Agent Group Chat" for communication between clones, mitigating duplicated work & encouraging emergent behavior
- Tool-augmented agent loop via LangGraph
- Human-like delays, typing, scrolling
- Browser fingerprint and stealth adjustments
- Tab management and PDF handling


### Quickstart (uv)
Kagebunshin now uses `uv` for dependency and runtime management.

1) Create a virtual environment with Python 3.13 and install dependencies:
```
cd kagebunshin
uv python install 3.13
uv venv -p 3.13
source .venv/bin/activate
uv sync
uv run playwright install chromium
```

2) Run the agent:
```
uv run -m kagebunshin
```

2b) Launch the interactive chat UI (Textual):
```
uv run -m kagebunshin --chat
```

3) Run with a custom query (without adding an entry point):
```
uv run python -c 'import asyncio; from kagebunshin.cli import main; asyncio.run(main("Open google.com and summarize the page"))'
```

Set `OPENAI_API_KEY` in your environment to use the default LLM provider. If you switch the agent to Anthropic in `src/config.py`, also set `ANTHROPIC_API_KEY`.

### Configuration
Edit `src/config.py` for:
- LLM model/provider and temperature
- Browser executable or channel, user data dir, default permissions
- Stealth and fingerprint profiles
- Human behavior tuning

### Programmatic use
```
from kagebunshin import WebVoyagerV2
# Create a Playwright context, then:
# orchestrator = await WebVoyagerV2.create(context)
# async for chunk in orchestrator.astream("Your task"):
#     ...
```

### Chat UI
- The chat UI is built with Textual and supports back-and-forth messaging with streaming updates.
- Your previous few lines are prepended to each turn to provide lightweight context across turns.
- Exit with Ctrl-C or by closing the terminal window.

If you don't have browsers installed for Playwright, run:
```
uv run playwright install chromium
```

### Notes
- `mark_page.js` is injected to annotate interactive elements and capture metadata.
- For headless environments, adjust `headless` in `src/cli.py` and ensure proper sandboxing flags.
- To change the Chrome binary or user data dir, edit `BROWSER_EXECUTABLE_PATH` and `USER_DATA_DIR` in `src/config.py`.
- To update dependencies, use `uv add <package>` / `uv remove <package>` and commit `pyproject.toml` and `uv.lock`.

