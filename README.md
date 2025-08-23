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
uv run -m kagebunshin "Your task description"

# Run with interactive REPL mode
uv run -m kagebunshin --repl

# Reference a markdown file as the task
uv run -m kagebunshin -r @kagebunshin/config/prompts/useful_query_templates/literature_review.md

# Combine custom query with markdown file reference
uv run -m kagebunshin "Execute this task" -r @path/to/template.md

# Or if installed with pip
kagebunshin "Your task"
kagebunshin --repl
kagebunshin -r @path/to/file.md
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

The test suite covers all major components with 129+ comprehensive tests:

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── core/                    # Core functionality tests
│   ├── test_agent.py       # KageBunshinAgent initialization & workflow
│   ├── test_state.py       # State models and validation
│   └── test_state_manager.py # Browser operations & page management
├── tools/                   # Agent tools tests
│   └── test_delegation.py  # Shadow clone delegation system
├── communication/           # Group chat tests
│   └── test_group_chat.py  # Redis-based communication
├── utils/                   # Utility function tests
│   ├── test_formatting.py  # Text/HTML formatting & normalization
│   └── test_naming.py      # Agent name generation
└── automation/             # Browser automation tests
    └── test_behavior.py    # Human behavior simulation
```

#### Testing Features

- **🔴 TDD Compliant**: Tests written assuming current implementation works
- **🧪 Comprehensive Mocking**: External dependencies (Playwright, Redis, LLMs) properly mocked
- **⚡ Async Support**: Full pytest-asyncio configuration for async components
- **📝 AAA Pattern**: Arrange-Act-Assert structure throughout
- **🎯 Behavioral Testing**: Focus on behavior, not implementation details
- **🛡️ Defensive Testing**: Error handling and edge case coverage

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
│   └── prompts/           # System prompts
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

### Architecture Benefits

- **🎯 Clear Separation**: Each module has a focused, single responsibility
- **📈 Scalable Design**: Easy to extend with new tools, behaviors, and UI components
- **🔍 Better Organization**: Related functionality is logically grouped together
- **🧩 Modular Components**: Large monolithic files decomposed into focused modules
- **🌳 Hierarchical Structure**: Nested organization for complex subsystems

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph) for agent orchestration
- Uses [Playwright](https://playwright.dev/) for browser automation
- Inspired by the need for cost-effective parallel web automation

