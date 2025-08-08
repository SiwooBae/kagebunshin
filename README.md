### Kagebunshin

Kagebunshin is an AI web automation agent derived from the experimental `webvoyager_v2`. It uses Playwright for browsing and LangGraph + LangChain for tool-augmented reasoning, with stealth/fingerprint mitigations and human-like interaction patterns.

### Features
- Multimodal page context (screenshot + structured DOM context)
- Tool-augmented agent loop via LangGraph
- Human-like delays, typing, scrolling
- Browser fingerprint and stealth adjustments
- Tab management and PDF handling

### Quickstart
1) Install dependencies (Python 3.13+ recommended):
```
cd Kagebunshin
pip install -r requirements.txt
python -m playwright install chromium
```

2) Run the agent (module run without installing):
```
python -m kagebunshin
```

Alternatively, install the package and use the console script globally:
```
pip install -e .
kagebunshin "Open google.com and summarize the page"
```

Set `OPENAI_API_KEY` in your environment to use the default LLM provider.

### Configuration
Edit `kagebunshin/config.py` for:
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

### Notes
- `mark_page.js` is injected to annotate interactive elements and capture metadata.
- For headless environments, adjust `headless` in `kagebunshin/cli.py` and ensure proper sandboxing flags.

