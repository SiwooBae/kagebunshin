# Testing Guide

This guide provides comprehensive information about the KageBunshin test suite, testing practices, and how to maintain and extend the tests.

## Overview

KageBunshin follows Test-Driven Development (TDD) principles with a comprehensive unit test suite covering all major components. The test suite includes 155 tests that verify functionality without relying on external dependencies.

## Quick Start

```bash
# Install test dependencies (pytest-asyncio included in dev dependencies)
uv sync --all-extras

# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run specific test module
uv run pytest tests/core/test_agent.py

# Run tests matching a pattern
uv run pytest -k "delegation"

# Run tests with coverage
uv run pytest --cov=kagebunshin --cov-report=html
```

## Test Structure

### Directory Organization

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── pytest.ini                    # Pytest configuration
├── core/                         # Core functionality tests
│   ├── test_agent.py             # Agent orchestration and workflow
│   ├── test_state.py             # State models and validation  
│   └── test_state_manager.py     # Browser operations
├── tools/                        # Agent tools tests
│   └── test_delegation.py        # Shadow clone delegation
├── communication/                # Group chat tests
│   └── test_group_chat.py        # Redis communication & fallback
├── utils/                        # Utility function tests
│   ├── test_formatting.py        # Text/HTML formatting
│   └── test_naming.py            # Agent name generation
└── automation/                   # Browser automation tests
    └── test_behavior.py          # Human behavior simulation
```

### Test Categories

#### Core Component Tests (`tests/core/`)

**Agent Tests** (`test_agent.py`)
- Agent initialization with default and custom parameters
- LLM tool binding and configuration
- Workflow execution and message handling
- Group chat client setup
- Instance tracking for concurrency limits

**State Model Tests** (`test_state.py`) 
- Pydantic model validation (BBox, Annotation, etc.)
- TypedDict behavior (KageBunshinState, TabInfo)
- Field parsing and default values
- Complex nested data structures

**State Manager Tests** (`test_state_manager.py`)
- Browser context management
- Page operations (navigation, clicking, typing)
- Screenshot capture and content extraction
- Error handling for invalid states

#### Tool & Communication Tests

**Delegation Tests** (`test_delegation.py`)
- Conversation history summarization
- Tool creation with browser contexts
- Parameter validation and error handling

**Group Chat Tests** (`test_group_chat.py`)
- Redis connection and fallback to memory
- Message serialization and deserialization
- Chat record management and cleanup
- Error handling for connection failures

#### Utility & Automation Tests

**Formatting Tests** (`test_formatting.py`)
- HTML to markdown conversion
- Context formatting for LLMs
- Chat content normalization
- Image context handling

**Behavior Tests** (`test_behavior.py`)
- Human delay simulation
- Mouse movement and typing patterns
- Scrolling behavior
- Action timing variations

## Testing Principles

### Test-Driven Development (TDD)

All tests follow the Red-Green-Refactor cycle:

1. **🔴 Red**: Write failing tests that describe desired behavior
2. **🟢 Green**: Write minimal code to make tests pass  
3. **🔧 Refactor**: Improve code while keeping tests green

### Key Testing Patterns

#### AAA Pattern (Arrange-Act-Assert)

```python
def test_should_create_agent_with_browser_context(self):
    # Arrange
    mock_context = Mock(spec=BrowserContext)
    mock_state_manager = Mock()
    
    # Act
    agent = KageBunshinAgent(mock_context, mock_state_manager)
    
    # Assert
    assert agent.initial_context == mock_context
    assert agent.state_manager == mock_state_manager
```

#### Descriptive Test Names

Test names follow the pattern: `test_should_<expected_behavior>_when_<condition>`

```python
def test_should_increment_clone_depth_when_delegating_tasks(self):
def test_should_fallback_to_memory_when_redis_unavailable(self):
def test_should_parse_captcha_field_from_string_values(self):
```

#### Comprehensive Mocking

External dependencies are thoroughly mocked:

```python
@pytest.fixture
def mock_browser_context():
    """Mock Playwright BrowserContext."""
    context = AsyncMock(spec=BrowserContext)
    context.pages = []
    return context

@pytest.fixture  
def mock_llm():
    """Mock LLM for testing."""
    llm = Mock()
    llm.invoke = AsyncMock(return_value=AIMessage(content="Mock response"))
    llm.bind_tools = Mock(return_value=llm)
    return llm
```

## Async Testing

Many components are asynchronous, requiring special handling:

### Configuration

```ini
# pytest.ini
[tool:pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

### Async Test Example

```python
@pytest.mark.asyncio
async def test_should_handle_async_browser_operations(self, mock_page):
    """Test async browser operations with proper mocking."""
    mock_page.goto = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_data")
    
    # Test async functionality
    await browser_operation(mock_page)
    
    mock_page.goto.assert_called_once()
    mock_page.screenshot.assert_called_once()
```

## Fixtures and Test Data

### Shared Fixtures (`conftest.py`)

The test suite uses comprehensive fixtures for common test data:

```python
@pytest.fixture
def sample_bbox():
    """Sample BBox for testing."""
    return BBox(
        x=100.0, y=200.0,
        text="Click me", type="button",
        ariaLabel="Submit button",
        selector='[data-ai-label="1"]',
        globalIndex=1,
        boundingBox=BoundingBox(left=100.0, top=200.0, width=80.0, height=30.0)
    )

@pytest.fixture  
def sample_state(mock_browser_context):
    """Sample KageBunshinState for testing."""
    return KageBunshinState(
        input="Test query",
        messages=[HumanMessage(content="Hello")],
        context=mock_browser_context,
        clone_depth=0
    )
```

### Factory Pattern

For complex test data, use factory functions:

```python
def create_test_agent(context=None, **kwargs):
    """Factory function for creating test agents."""
    if context is None:
        context = Mock(spec=BrowserContext)
    
    defaults = {
        'system_prompt': 'Test prompt',
        'clone_depth': 0,
        'enable_summarization': False
    }
    defaults.update(kwargs)
    
    return KageBunshinAgent(context, Mock(), **defaults)
```

## Best Practices

### Test Quality Guidelines

1. **One Assertion Per Test**: Makes failures easier to debug
2. **Mock External Dependencies**: Never make real API calls or browser operations
3. **Test Behavior, Not Implementation**: Focus on what the code does, not how
4. **Use Descriptive Names**: Test names should explain the expected behavior
5. **Keep Tests Independent**: Each test should run in isolation
6. **Test Edge Cases**: Include error scenarios and boundary conditions

### Error Testing

Always test error scenarios:

```python
def test_should_handle_invalid_page_index_gracefully(self):
    """Test graceful handling of invalid page indices."""
    state_manager.current_page_index = 999
    
    with pytest.raises(ValueError, match="Invalid page index"):
        state_manager.get_current_page()
```

### Performance Testing

Use markers for slow tests:

```python
@pytest.mark.slow
def test_should_handle_large_message_history(self):
    """Test with large message history (marked as slow)."""
    messages = [HumanMessage(f"Message {i}") for i in range(1000)]
    # Test large data handling
```

## Running Tests

### Basic Commands

```bash
# Run all tests
uv run pytest

# Verbose output with test names
uv run pytest -v

# Stop on first failure
uv run pytest -x

# Run specific file
uv run pytest tests/core/test_agent.py

# Run specific test
uv run pytest tests/core/test_agent.py::TestKageBunshinAgent::test_should_initialize_with_default_parameters
```

### Advanced Options

```bash
# Run tests matching pattern
uv run pytest -k "delegation"

# Run only failed tests from last run
uv run pytest --lf

# Run failed tests first, then continue
uv run pytest --ff

# Parallel execution (requires pytest-xdist)
uv run pytest -n auto

# Coverage report
uv run pytest --cov=kagebunshin --cov-report=html
```

### Watch Mode

For continuous testing during development:

```bash
# Install pytest-watch
uv add --dev pytest-watch

# Run in watch mode
ptw -- --testmon
```

## Debugging Tests

### Common Issues

**Import Errors**: Ensure all dependencies are properly mocked
```python
# Good: Mock the dependency
with patch('module.external_dependency') as mock_dep:
    # Test code

# Bad: Real import that might fail
import external_dependency
```

**Async Issues**: Use proper async fixtures and marks
```python
# Good: Async fixture
@pytest.fixture
async def async_fixture():
    return await create_async_resource()

# Good: Async test
@pytest.mark.asyncio  
async def test_async_function():
    result = await async_function()
    assert result is not None
```

**State Pollution**: Keep tests independent
```python
# Good: Fresh state per test
def test_should_handle_clean_state(self):
    agent = create_fresh_agent()
    # Test with clean state

# Bad: Shared state between tests
class TestAgent:
    agent = None  # Don't do this
```

### Debugging Commands

```bash
# Run with Python debugger
uv run pytest --pdb

# Drop into debugger on failure
uv run pytest --pdb-trace

# Show local variables on failure
uv run pytest -l

# Disable output capture for debugging prints
uv run pytest -s
```

## Extending Tests

### Adding New Test Modules

1. Create test file in appropriate directory
2. Follow naming convention: `test_<module_name>.py`
3. Import necessary fixtures from `conftest.py`
4. Follow AAA pattern and descriptive naming

```python
"""
Unit tests for new_module.
"""
import pytest
from unittest.mock import Mock, AsyncMock

from kagebunshin.new_module import NewClass

class TestNewClass:
    """Test suite for NewClass functionality."""
    
    def test_should_create_instance_with_valid_parameters(self):
        """Test creating instance with valid parameters."""
        # Arrange
        param = "test_value"
        
        # Act
        instance = NewClass(param)
        
        # Assert
        assert instance.param == param
```

### Adding New Fixtures

Add reusable fixtures to `conftest.py`:

```python
@pytest.fixture
def sample_new_data():
    """Sample data for new functionality."""
    return {
        'field1': 'value1',
        'field2': 42,
        'field3': ['item1', 'item2']
    }
```

### Testing New Features

When adding new features, always:

1. Write tests first (TDD approach)
2. Mock all external dependencies
3. Test both success and failure scenarios
4. Include edge cases and boundary conditions
5. Update documentation if needed

## Current Test Suite Status

As of the latest update, the test suite includes:
- **Total tests**: 155 tests across 8 test files  
- **Test breakdown by file**:
  - `core/test_state_manager.py`: 34 tests (browser operations and page management)
  - `automation/test_behavior.py`: 29 tests (human behavior simulation and delays) 
  - `utils/test_formatting.py`: 27 tests (text/HTML formatting and conversions)
  - `communication/test_group_chat.py`: 17 tests (Redis chat system with fallback)
  - `core/test_agent.py`: 15 tests (agent orchestration and workflow)
  - `core/test_state.py`: 14 tests (Pydantic state models validation)
  - `tools/test_delegation.py`: 11 tests (shadow clone delegation system)
  - `utils/test_naming.py`: 8 tests (agent name generation with petname)

All tests are currently **passing** and follow TDD principles with comprehensive mocking of external dependencies.

### Recent Test Suite Improvements

The test suite has been significantly improved with:
- **Fixed async mocking**: Proper AsyncMock hierarchy for Playwright objects (Page, Mouse, Keyboard)
- **Corrected pytest configuration**: Updated from `[tool:pytest]` to `[pytest]` format
- **Enhanced fixtures**: Comprehensive mock objects in `conftest.py` with proper async support
- **Implementation alignment**: All tests now align with actual implementation interfaces
- **LLM-aware testing**: Delegation tests handle non-deterministic LLM outputs appropriately
- **Redis mocking**: Proper Redis client mocking with `decode_responses=True`
- **Tool call structure**: Correct Langchain ToolCall objects with required fields
- **Complete state manager coverage**: 34 tests covering all browser operations

## Continuous Integration

Tests are designed to run in CI environments:

- No external dependencies (everything mocked)
- Deterministic outcomes
- Fast execution (< 1 second per test)
- Clear failure messages
- Proper cleanup of resources

## Troubleshooting

### Common Test Failures

**Async Warnings**: Add proper async configuration
```python
# In conftest.py
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

**Mock Issues**: Ensure mocks match real interfaces
```python
# Use spec to catch interface mismatches
mock_page = Mock(spec=Page)
mock_context = AsyncMock(spec=BrowserContext)
```

**Fixture Errors**: Check fixture dependencies
```python
# Ensure fixtures are properly ordered
@pytest.fixture
def dependent_fixture(base_fixture):
    return create_dependent_resource(base_fixture)
```

For additional help, check the test output carefully - pytest provides detailed error messages and suggestions for common issues.