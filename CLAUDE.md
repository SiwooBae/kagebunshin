# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🔴🟢🔧 Test-Driven Development (TDD)

**ALWAYS follow TDD principles when implementing new features or fixing bugs.**

### The Red-Green-Refactor Cycle

1. **🔴 RED**: Write a failing test that describes the desired behavior
2. **🟢 GREEN**: Write the minimal code to make the test pass
3. **🔧 REFACTOR**: Improve the code while keeping tests green

### TDD Workflow

For every new feature or bug fix:

```bash
# 1. RED: Write a failing test
# Create/update test file first
uv run pytest tests/path/to/test_file.py::TestClass::test_new_feature -v
# Should FAIL initially

# 2. GREEN: Implement minimal code
# Write just enough code to pass the test
uv run pytest tests/path/to/test_file.py::TestClass::test_new_feature -v
# Should PASS

# 3. REFACTOR: Improve code quality
# Run full test suite to ensure no regressions
uv run pytest tests/ -v
```

### TDD Commands

```bash
# Run tests in watch mode (install pytest-watch: uv add --dev pytest-watch)
ptw -- --testmon

# Run only failed tests from last run
uv run pytest --lf

# Run tests that failed, then continue with rest
uv run pytest --ff

# Run specific test method with minimal output
uv run pytest tests/core/test_module.py::TestClass::test_method -q

# Run tests with immediate failure output
uv run pytest -x --tb=short

# Run tests and stop after first failure
uv run pytest -x
```

### TDD Best Practices

1. **Write the simplest test first** - Start with the most basic case
2. **Test one behavior at a time** - Each test should verify one specific behavior
3. **Use descriptive test names** - Name tests as `test_should_do_something_when_condition`
4. **Test behavior, not implementation** - Focus on what the code does, not how
5. **Keep tests independent** - Each test should run in isolation
6. **Mock external dependencies** - Use mocks for databases, APIs, file systems

### TDD Example Pattern

```python
# 1. RED: Write failing test first
def test_should_calculate_total_price_when_adding_items():
    # Arrange
    cart = ShoppingCart()
    
    # Act & Assert
    with pytest.raises(AttributeError):  # Should fail initially
        cart.calculate_total()

# 2. GREEN: Implement minimal code
class ShoppingCart:
    def calculate_total(self):
        return 0.0  # Minimal implementation

# 3. REFACTOR: Improve while keeping tests green
def test_should_calculate_total_price_when_adding_items():
    # Arrange
    cart = ShoppingCart()
    cart.add_item("apple", 1.50, 2)
    cart.add_item("banana", 0.75, 3)
    
    # Act
    total = cart.calculate_total()
    
    # Assert
    assert total == 5.25  # 1.50*2 + 0.75*3
```

### Test Organization for TDD

- **File naming**: `test_<module_name>.py` for each source module
- **Class naming**: `TestClassName` for each class being tested
- **Method naming**: `test_should_<expected_behavior>_when_<condition>`
- **Test structure**: Follow Arrange-Act-Assert (AAA) pattern consistently

### Test Quality Guidelines

- **One assertion per test** when possible - makes failures easier to debug
- **Use fixtures for common setup** - defined in `conftest.py` or test classes
- **Mock external dependencies** - databases, APIs, file systems, network calls
- **Test edge cases and error scenarios** - not just happy paths
- **Use descriptive assertion messages** - `assert result == expected, f"Expected {expected}, got {result}"`
- **Keep tests fast** - use markers for slow tests: `@pytest.mark.slow`

### Test Data Management

- **Use factories** for creating test data (see `tests/conftest.py` fixtures)
- **Avoid hardcoded values** - use variables with descriptive names
- **Clean up after tests** - use fixtures with teardown or `@pytest.fixture(autouse=True)`
- **Isolate test data** - each test should create its own data

### KageBunshin Test Suite Structure

The project includes a comprehensive test suite with 155 tests covering all major components:

#### Core Component Tests (`tests/core/`)
- **test_agent.py** (15 tests): KageBunshinAgent initialization, tool binding, workflow execution
- **test_state.py** (14 tests): State models (BBox, Annotation, KageBunshinState) validation
- **test_state_manager.py** (34 tests): Browser operations, page navigation, element interactions

#### Tool & Communication Tests
- **test_delegation.py** (11 tests): Shadow clone spawning, context inheritance, resource cleanup
- **test_group_chat.py** (17 tests): Redis client, fallback to memory, message posting/retrieval

#### Utility & Automation Tests  
- **test_formatting.py** (27 tests): HTML/markdown conversion, context formatting, chat normalization
- **test_naming.py** (8 tests): Agent name generation with petname library
- **test_behavior.py** (29 tests): Human behavior simulation (delays, mouse movements, typing)

### Testing Best Practices for KageBunshin

#### Async Testing
```python
@pytest.mark.asyncio
async def test_should_handle_async_operations(self):
    """Use pytest.mark.asyncio for async test functions."""
    result = await some_async_function()
    assert result is not None
```

#### Mocking External Dependencies
```python
def test_should_mock_playwright_interactions(self, mock_page):
    """Mock Playwright Page objects for browser operations."""
    mock_page.click.return_value = AsyncMock()
    # Test browser interaction logic without actual browser
```

#### Fixture Usage
```python
def test_should_use_shared_fixtures(self, sample_state, mock_browser_context):
    """Leverage conftest.py fixtures for common test data."""
    assert sample_state["clone_depth"] == 0
    assert mock_browser_context is not None
```

#### Testing Agent Workflows
```python
def test_should_verify_agent_behavior_not_implementation(self):
    """Focus on what the agent does, not how it does it."""
    # Test the outcome, not internal method calls
    assert agent.can_delegate_tasks()
    assert agent.maintains_conversation_history()
```

### Running Tests

```bash
# Run all tests with TDD workflow
uv run pytest tests/ -v

# Run specific component tests
uv run pytest tests/core/test_agent.py -v

# Run tests with async debugging (asyncio-mode=auto configured in pytest.ini)
uv run pytest tests/ -v

# Test specific behaviors
uv run pytest tests/ -k "delegation" -v

# Run tests with coverage report
uv run pytest --cov=kagebunshin --cov-report=html

# Run tests quietly to see summary
uv run pytest -q

# Run tests and stop on first failure
uv run pytest -x
```

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

# Reference query templates with @ syntax
uv run -m kagebunshin -r @kagebunshin/config/prompts/useful_query_templates/literature_review.md
uv run -m kagebunshin -r @kagebunshin/config/prompts/useful_query_templates/E2E_testing.md

# Combine custom query with template
uv run -m kagebunshin "Execute this specific task" -r @path/to/template.md

# Using entry point (if installed)
kagebunshin "task description"
kagebunshin --repl
kagebunshin -r @path/to/template.md
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
- manager for browser operations and web automation
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

### Current Test Status (Updated)

As of the latest update:
- **Total tests**: 155 tests (all passing ✅)
- **Test coverage**: All major components covered
- **Async support**: Full pytest-asyncio configuration with auto mode
- **Mocking**: Comprehensive mocking of external dependencies (Playwright, Redis, LLMs)
- **Recent improvements**:
  - Fixed async mock hierarchy for proper Playwright object mocking
  - Corrected pytest configuration from `[tool:pytest]` to `[pytest]` format
  - Enhanced fixtures in `conftest.py` with proper async support
  - All tests now align with actual implementation interfaces
  - LLM-aware testing for non-deterministic summarization outputs
  - Proper Redis client mocking with `decode_responses=True`
  - Correct Langchain ToolCall objects with required fields