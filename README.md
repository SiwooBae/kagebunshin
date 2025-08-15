## Kagebunshin 🍥

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

**Kagebunshin** is a web-browsing, research-focused agent swarm with self-cloning capabilities. Built on the foundation of advanced language models, this system enables economically viable parallel web automation.

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


## Installation

### Using uv (Recommended)

Kagebunshin uses `uv` for dependency and runtime management.

```bash
git clone https://github.com/SiwooBae/kagebunshin.git
cd kagebunshin
uv python install 3.13
uv venv -p 3.13
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync
uv run playwright install chromium
```

### Using pip

```bash
git clone https://github.com/SiwooBae/kagebunshin.git
cd kagebunshin
pip install -e .
playwright install chromium
```

### Environment Setup

Set your API key in your environment:
```bash
export OPENAI_API_KEY="your-openai-api-key"
# or for Anthropic (if configured)
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

## Usage

### Command Line Interface

```bash
# Run the agent (using uv)
uv run -m kagebunshin

# Launch the interactive chat UI
uv run -m kagebunshin --chat

# Or if installed with pip
kagebunshin
kagebunshin --chat
```

### Programmatic Usage

```python
from kagebunshin import KageBunshinAgent
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        
        orchestrator = await KageBunshinAgent.create(context)
        async for chunk in orchestrator.astream("Your task"):
            print(chunk)
            
        await browser.close()
```

## Configuration

Edit `kagebunshin/config.py` to customize:

- **LLM Settings**: Model/provider, temperature, reasoning effort
- **Browser Settings**: Executable path, user data directory, permissions
- **Stealth Features**: Fingerprint profiles, human behavior simulation
- **Group Chat**: Redis connection settings for agent communication
- **Performance**: Concurrency limits, timeouts, delays

## Development

### Setting up for development

```bash
git clone https://github.com/SiwooBae/kagebunshin.git
cd kagebunshin
uv sync --all-extras
uv run playwright install chromium
```

### Code Quality

The project includes tools for maintaining code quality:

```bash
# Format code
uv run black .
uv run isort .

# Lint code  
uv run flake8 kagebunshin/

# Type checking
uv run mypy kagebunshin/
```

### Testing

```bash
uv run pytest
```

## Architecture

- **KageBunshinAgent**: Main orchestrator handling web automation tasks
- **StateManager**: Manages browser state and provides tools for LLM
- **GroupChat**: Redis-based communication system for agent coordination
- **HumanBehavior**: Simulates human-like interactions to avoid detection
- **FingerprintEvasion**: Randomizes browser fingerprints for stealth

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph) for agent orchestration
- Uses [Playwright](https://playwright.dev/) for browser automation
- Inspired by the need for cost-effective parallel web automation

