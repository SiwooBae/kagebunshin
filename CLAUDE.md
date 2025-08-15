# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Installation and Setup
```bash
# Install dependencies with uv (recommended)
uv python install 3.13
uv venv -p 3.13
source .venv/bin/activate
uv sync
uv run playwright install chromium

# Development setup with optional dependencies
uv sync --all-extras

# Alternative with pip
pip install -e .
playwright install chromium
```

### Running the Application
```bash
# Run single task (one-shot mode)
uv run -m kagebunshin "task description here"

# Run interactive REPL mode with persistent memory
uv run -m kagebunshin --repl

# Using entry point (if installed)
kagebunshin "task description"
kagebunshin --repl
```

### Testing and Code Quality
```bash
# Run tests
uv run pytest

# Code formatting
uv run black .
uv run isort .

# Linting
uv run flake8 kagebunshin/

# Type checking
uv run mypy kagebunshin/
```

### Environment Configuration
```bash
# Required API key
export OPENAI_API_KEY="your-openai-api-key"
# Optional for Anthropic
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# Optional Redis group chat settings
export KAGE_REDIS_HOST="127.0.0.1"
export KAGE_REDIS_PORT="6379"
export KAGE_GROUPCHAT_ROOM="lobby"

# Enable summarization (disabled by default)
export KAGE_ENABLE_SUMMARIZATION="1"

# Limit concurrent agents
export KAGE_MAX_KAGEBUNSHIN_INSTANCES="5"
```

## Architecture Overview

### Core Components

**KageBunshinAgent** (`kagebunshin/core/agent.py`):
- Main orchestrator implementing LangGraph-based ReAct pattern
- Handles LLM interactions, tool binding, and conversation flow
- Manages persistent message history across turns
- Uses GPT-5-mini/nano models by default with reasoning effort settings
- Integrates group chat for multi-agent coordination

**KageBunshinStateManager** (`kagebunshin/core/state_manager.py`):
- Stateless manager for browser operations and web automation
- Provides tools for clicking, typing, scrolling, navigation
- Handles screenshot capture, element annotation, and markdown extraction
- Implements human-like behavior simulation (delays, mouse movement)

**KageBunshinState** (`kagebunshin/core/state.py`):
- TypedDict defining the core state structure
- Contains input, messages, browser context, and derived annotations
- Shared across the LangGraph workflow nodes

### Key Features

**Agent Delegation** (`kagebunshin/tools/delegation.py`):
- `delegate` tool spawns parallel shadow-clone sub-agents with conversation context inheritance
- Uses LangGraph's `InjectedState` to access current conversation state dynamically
- Automatically summarizes parent's conversation history for clone context
- Each clone gets fresh browser context for isolation plus parent context briefing
- Clones receive structured briefing with parent context, mission, and coordination instructions
- Supports concurrent task execution with automatic resource cleanup
- Hard cap on simultaneous instances (default: 5)

**Group Chat Communication** (`kagebunshin/communication/group_chat.py`):
- Redis-based group chat for agent coordination
- Prevents duplicate work and enables emergent behavior
- Automatic intro messages and task announcements

**Stealth Browser Automation** (`kagebunshin/automation/`):
- Fingerprint evasion with multiple profiles (Windows/Mac/Linux)
- Human behavior simulation (typing patterns, mouse movement, delays)
- Comprehensive stealth arguments and disabled Chrome components
- Anti-bot detection mitigation

### LLM Configuration

The system uses a two-tier LLM approach:
- **Main LLM**: GPT-5-mini with "low" reasoning effort for primary agent tasks
- **Summarizer LLM**: GPT-5-nano with "minimal" reasoning effort for action summaries

Models are configurable via settings.py and support both OpenAI and Anthropic providers.

### Tool Architecture

Browser automation tools are bound to LLM via LangGraph's ToolNode:
- Web navigation (goto_url, go_back, go_forward)
- Element interaction (click, type, scroll)
- Content extraction (extract_text, take_screenshot)
- Tab management (new_tab, close_tab, switch_tab)
- Agent coordination (delegate, post_groupchat)

### Entry Points

- **CLI Runner** (`kagebunshin/cli/runner.py`): Colored streaming output with session management
- **Main Module** (`kagebunshin/__main__.py`): Entry point delegation to CLI
- **Script**: `kagebunshin` command via pyproject.toml

### State Management Pattern

The architecture follows a "stateless orchestrator" pattern:
- State flows through LangGraph nodes as TypedDict
- State manager operates on current state without persistence
- Browser context provides natural state boundary
- Message history persisted in agent for conversation continuity

### Conversation Context Inheritance

Enhanced delegation system ensures clones inherit parent context:
- Uses LangGraph's `InjectedState` to access current conversation state at delegation time
- Automatically summarizes last 15 meaningful messages from parent's conversation history
- Clones receive structured briefing including parent context summary and specific mission
- Enables coordinated swarm intelligence with shared understanding of overall progress
- Summarization uses lightweight LLM (GPT-5-nano) to minimize cost and latency

### Configuration Management

Settings centralized in `kagebunshin/config/settings.py`:
- LLM models, providers, and reasoning parameters
- Browser launch options and stealth configurations  
- Human behavior simulation parameters
- Group chat and concurrency limits
- Extensive fingerprint profiles for different OS/browser combinations

### Testing Framework

Uses pytest with async support (`pytest-asyncio`) for testing async components.