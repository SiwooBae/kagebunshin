### Kagebunshin

Kagebunshin is an AI web automation agent derived from the experimental `webvoyager_v2`. It uses Playwright for browsing and LangGraph + LangChain for tool-augmented reasoning, with stealth/fingerprint mitigations and human-like interaction patterns.

### Features
- Multimodal page context (screenshot + structured DOM context)
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

