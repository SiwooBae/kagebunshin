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

### From PyPI (Recommended)

```bash
# Using uv (recommended)
uv add kagebunshin
uv run playwright install chromium

# Or using pip
pip install kagebunshin
playwright install chromium
```

### Development Installation

For development or to get the latest features:

```bash
# Using uv
git clone https://github.com/SiwooBae/kagebunshin.git
cd kagebunshin
uv python install 3.13
uv venv -p 3.13
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync
uv run playwright install chromium

# Using pip
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
uv run -m kagebunshin "Your task description"

# Run with interactive REPL mode
uv run -m kagebunshin --repl

# Reference a markdown file as the task
uv run -m kagebunshin -r @kagebunshin/config/prompts/useful_query_templates/literature_review.md

# Combine custom query with markdown file reference
uv run -m kagebunshin "Execute this task" -r @path/to/template.md

# Available query templates:
# - @kagebunshin/config/prompts/useful_query_templates/literature_review.md
# - @kagebunshin/config/prompts/useful_query_templates/E2E_testing.md

# Or if installed with pip
kagebunshin "Your task"
kagebunshin --repl
kagebunshin -r @path/to/file.md
```

### Programmatic Usage

#### Simple API (Recommended)

The simplified `Agent` class provides comprehensive configuration without needing to edit settings files:

```python
import asyncio
from kagebunshin import Agent

# Simplest usage - uses intelligent defaults
async def main():
    agent = Agent(task="Find me some desk toys")
    result = await agent.run()
    print(result)

asyncio.run(main())
```

##### With Custom LLM

```python
from langchain.chat_models import ChatOpenAI

async def main():
    agent = Agent(
        task="Find repo stars and analyze trends",
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0)
    )
    result = await agent.run()
    print(result)

asyncio.run(main())
```

##### Full Configuration Example

```python
agent = Agent(
    task="Complex research with multiple steps",
    
    # LLM Configuration
    llm_model="gpt-5",                    # Model name
    llm_provider="openai",               # "openai" or "anthropic"
    llm_reasoning_effort="high",         # "minimal", "low", "medium", "high"
    llm_temperature=0.1,                 # Temperature (0.0-2.0)
    
    # Summarizer Configuration
    summarizer_model="gpt-5-nano",       # Cheaper model for summaries
    enable_summarization=True,           # Enable action summaries
    
    # Browser Configuration
    headless=False,                      # Visible browser
    viewport_width=1280,                 # Browser viewport width
    viewport_height=1280,                # Browser viewport height
    browser_executable_path="/path/chrome", # Custom browser
    user_data_dir="~/chrome-profile",   # Persistent profile
    
    # Workflow Configuration
    recursion_limit=200,                 # Max recursion depth
    max_iterations=150,                  # Max iterations
    timeout=120,                         # Timeout per operation
    
    # Multi-agent Configuration
    group_room="research_team",          # Group chat room
    username="lead_researcher"           # Agent name
)
result = await agent.run()
```

##### Available Parameters

**LLM Configuration:**
- `llm`: Pre-configured LLM instance (optional)
- `llm_model`: Model name (default: "gpt-5-mini")
- `llm_provider`: "openai" or "anthropic" (default: "openai")
- `llm_reasoning_effort`: "minimal", "low", "medium", "high" (default: "low")
- `llm_temperature`: Temperature 0.0-2.0 (default: 1.0)

**Summarizer Configuration:**
- `summarizer_model`: Model for summaries (default: "gpt-5-nano")
- `summarizer_provider`: Provider for summarizer (default: "openai")
- `enable_summarization`: Enable action summaries (default: False)

**Browser Configuration:**
- `headless`: Run in headless mode (default: False)
- `viewport_width`: Browser width (default: 1280)
- `viewport_height`: Browser height (default: 1280)
- `browser_executable_path`: Custom browser path (default: auto-detect)
- `user_data_dir`: Persistent profile directory (default: temporary)

**Workflow Configuration:**
- `recursion_limit`: Max recursion depth (default: 150)
- `max_iterations`: Max iterations per task (default: 100)
- `timeout`: Timeout per operation in seconds (default: 60)

**Multi-agent Configuration:**
- `group_room`: Group chat room name (default: "lobby")
- `username`: Agent name (default: auto-generated)

#### Advanced API

For more control over the browser lifecycle, use the lower-level `KageBunshinAgent`:

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

### BrowseComp eval

Evaluate Kagebunshin on OpenAI's BrowseComp benchmark.

Prereqs:
- Ensure Playwright browsers are installed (see Installation). If using Chromium: `uv run playwright install chromium`.
- Set `OPENAI_API_KEY` for the grader model.

Quick start (uv):
```bash
uv run -m evals.run_browsercomp --headless --num-examples 20 --grader-model gpt-5 --grader-provider openai
```

Quick start (pip):
```bash
python -m evals.run_browsercomp --headless --num-examples 20 --grader-model gpt-5 --grader-provider openai
```

Options:
- `--num-examples N`: sample N problems from the test set. When provided, `--n-repeats` must remain 1.
- `--n-repeats N`: repeat each example N times (only when running the full set).
- `--headless`: run the browser without a visible window.
- `--browser {chromium,chrome}`: choose Playwright Chromium or your local Chrome.
- `--grader-model`, `--grader-provider`: LLM used for grading (default `gpt-5` on `openai`).
- `--report PATH`: path to save the HTML report (defaults to `runs/browsecomp-report-<timestamp>.html`).

Output:
- Prints aggregate metrics (e.g., accuracy) to stdout.
- Saves a standalone HTML report with prompts, responses, and per-sample scores.

## Configuration

Edit `kagebunshin/config/settings.py` to customize:

- **LLM Settings**: Model/provider, temperature, reasoning effort
- **Browser Settings**: Executable path, user data directory, permissions
- **Stealth Features**: Fingerprint profiles, human behavior simulation
- **Group Chat**: Redis connection settings for agent coordination
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

Kagebunshin includes a comprehensive unit test suite following TDD (Test-Driven Development) principles:

```bash
# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run specific test module
uv run pytest tests/core/test_agent.py

# Run tests with coverage report
uv run pytest --cov=kagebunshin

# Run tests in watch mode (requires pytest-watch)
ptw -- --testmon
```

#### Test Structure

The test suite covers all major components with 155 comprehensive tests:

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── core/                    # Core functionality tests (63 tests)
│   ├── test_agent.py       # KageBunshinAgent initialization & workflow (15 tests)
│   ├── test_state.py       # State models and validation (14 tests)
│   └── test_state_manager.py # Browser operations & page management (34 tests)
├── tools/                   # Agent tools tests (11 tests)
│   └── test_delegation.py  # Shadow clone delegation system
├── communication/           # Group chat tests (17 tests)
│   └── test_group_chat.py  # Redis-based communication
├── utils/                   # Utility function tests (35 tests)
│   ├── test_formatting.py  # Text/HTML formatting & normalization (27 tests)
│   └── test_naming.py      # Agent name generation (8 tests)
└── automation/             # Browser automation tests (29 tests)
    └── test_behavior.py    # Human behavior simulation

# Configuration files (in project root):
pytest.ini                   # Pytest configuration with asyncio support
```
## Project Structure

Kagebunshin features a clean, modular architecture optimized for readability and extensibility:

```
kagebunshin/
├── core/                    # 🧠 Core agent functionality
│   ├── agent.py            # Main KageBunshinAgent orchestrator
│   ├── state.py            # State models and data structures
│   └── state_manager.py    # Browser state operations
│
├── automation/             # 🤖 Browser automation & stealth
│   ├── behavior.py         # Human behavior simulation
│   ├── fingerprinting.py   # Browser fingerprint evasion
│   └── browser/            # Browser-specific utilities
│
├── tools/                  # 🔧 Agent tools & capabilities
│   └── delegation.py       # Agent cloning and delegation
│
├── communication/          # 💬 Agent coordination
│   └── group_chat.py       # Redis-based group chat
│
├── cli/                    # 🖥️ Command-line interface
│   ├── runner.py          # CLI runner and REPL
│   └── ui/                # Future UI components
│
├── config/                 # ⚙️ Configuration management
│   ├── settings.py        # All configuration settings
│   └── prompts/           # System prompts and query templates
│       ├── kagebunshin_system_prompt.md     # Main system prompt
│       ├── kagebunshin_system_prompt_v2.md  # Alternative system prompt  
│       ├── tell_the_cur_state.md           # State description prompt
│       └── useful_query_templates/         # Pre-built query templates
│           ├── literature_review.md        # Academic literature review
│           └── E2E_testing.md             # End-to-end testing
│
└── utils/                  # 🛠️ Shared utilities
    ├── formatting.py      # HTML/text formatting for LLM
    ├── logging.py         # Logging utilities
    └── naming.py          # Agent name generation
```

### Key Components

- **🧠 Core Agent**: Orchestrates web automation tasks using LangGraph
- **🤖 Automation**: Human-like behavior simulation and stealth browsing
- **🔧 Tools**: Agent delegation system for parallel task execution
- **💬 Communication**: Redis-based group chat for agent coordination
- **🖥️ CLI**: Interactive command-line interface with streaming updates

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph) for agent orchestration
- Uses [Playwright](https://playwright.dev/) for browser automation
- Inspired by the need for cost-effective parallel web automation

