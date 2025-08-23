"""
Shared fixtures and test configuration for KageBunshin tests.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from playwright.async_api import BrowserContext, Page

from kagebunshin.core.state import KageBunshinState, BBox, TabInfo, Annotation, BoundingBox
from kagebunshin.core.state_manager import KageBunshinStateManager
from kagebunshin.core.agent import KageBunshinAgent


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_mouse():
    """Mock Playwright Mouse object."""
    mouse = AsyncMock()
    mouse.click = AsyncMock()
    mouse.move = AsyncMock()
    mouse.wheel = AsyncMock()
    return mouse


@pytest.fixture
def mock_keyboard():
    """Mock Playwright Keyboard object."""
    keyboard = AsyncMock()
    keyboard.type = AsyncMock()
    keyboard.press = AsyncMock()
    keyboard.insert_text = AsyncMock()
    return keyboard


@pytest.fixture
def mock_page(mock_mouse, mock_keyboard):
    """Mock Playwright Page with comprehensive method mocking."""
    page = AsyncMock(spec=Page)
    
    # Properties
    page.url = "https://example.com"
    
    # Async methods that return values
    page.title = AsyncMock(return_value="Test Page")
    page.screenshot = AsyncMock(return_value=b"fake_screenshot_data")
    page.content = AsyncMock(return_value="<html><body>Test content</body></html>")
    page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
    page.query_selector = AsyncMock(return_value=MagicMock())
    
    # Async methods that don't return values
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.select_option = AsyncMock()
    page.reload = AsyncMock()
    page.bring_to_front = AsyncMock()
    page.close = AsyncMock()
    
    # Objects with methods
    page.mouse = mock_mouse
    page.keyboard = mock_keyboard
    
    return page


@pytest.fixture
def mock_browser_context(mock_page):
    """Mock Playwright BrowserContext with comprehensive method mocking."""
    context = AsyncMock(spec=BrowserContext)
    
    # Properties
    context.pages = [mock_page]
    
    # Async methods
    context.new_page = AsyncMock(return_value=mock_page)
    context.close = AsyncMock()
    
    return context


@pytest.fixture
def sample_bbox():
    """Sample BBox for testing."""
    return BBox(
        x=100.0,
        y=200.0,
        text="Click me",
        type="button",
        ariaLabel="Submit button",
        selector='[data-ai-label="1"]',
        globalIndex=1,
        boundingBox=BoundingBox(left=100.0, top=200.0, width=80.0, height=30.0)
    )


@pytest.fixture
def sample_annotation(sample_bbox):
    """Sample Annotation for testing."""
    return Annotation(
        img="base64_encoded_image_data",
        bboxes=[sample_bbox],
        markdown="# Test Page\n\nSample content",
        totalElements=1
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


@pytest.fixture
def sample_tab_info(mock_page):
    """Sample TabInfo for testing."""
    return TabInfo(
        page=mock_page,
        tab_index=0,
        title="Test Tab",
        url="https://example.com",
        is_active=True
    )


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    llm = Mock()
    llm.invoke = AsyncMock(return_value=AIMessage(content="Mock response"))
    llm.bind_tools = Mock(return_value=llm)
    llm.astream = AsyncMock()
    return llm


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    redis_client = AsyncMock()
    redis_client.lpush = AsyncMock()
    redis_client.lrange = AsyncMock(return_value=[])
    redis_client.ltrim = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)
    redis_client.close = AsyncMock()
    return redis_client


@pytest.fixture
def mock_group_chat_client():
    """Mock GroupChatClient for testing."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.post = AsyncMock()
    client.history = AsyncMock(return_value=[])
    return client


@pytest.fixture
def state_manager(mock_browser_context):
    """Create a KageBunshinStateManager for testing."""
    manager = KageBunshinStateManager(mock_browser_context)
    return manager


@pytest.fixture
async def async_state_manager(mock_browser_context):
    """Create a KageBunshinStateManager for async testing."""
    manager = KageBunshinStateManager(mock_browser_context)
    return manager


@pytest.fixture
def kage_agent(mock_browser_context, state_manager, mock_llm):
    """Create a KageBunshinAgent for testing."""
    with patch('kagebunshin.core.agent.init_chat_model', return_value=mock_llm):
        with patch('kagebunshin.communication.group_chat.GroupChatClient'):
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=state_manager,
                system_prompt="Test system prompt"
            )
            return agent


@pytest.fixture
async def async_kage_agent(mock_browser_context, async_state_manager, mock_llm):
    """Create a KageBunshinAgent for async testing."""
    with patch('kagebunshin.core.agent.init_chat_model', return_value=mock_llm):
        with patch('kagebunshin.communication.group_chat.GroupChatClient'):
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=async_state_manager,
                system_prompt="Test system prompt"
            )
            return agent


@pytest.fixture
def sample_messages():
    """Sample message list for testing."""
    return [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
        HumanMessage(content="How are you?"),
        AIMessage(content="I'm doing well, thanks!")
    ]


@pytest.fixture
def sample_tool_response():
    """Sample tool response for testing."""
    return {
        "status": "success",
        "message": "Action completed successfully",
        "data": {"key": "value"}
    }


# Utility fixtures for common test patterns
@pytest.fixture
def mock_successful_page_response(mock_page):
    """Configure mock page for successful responses."""
    mock_page.title.return_value = "Success Page"
    mock_page.url = "https://example.com/success"
    mock_page.content.return_value = "<html><body><h1>Success</h1></body></html>"
    return mock_page


@pytest.fixture
def mock_error_page_response(mock_page):
    """Configure mock page for error responses."""
    mock_page.title.return_value = "Error Page"
    mock_page.url = "https://example.com/error"
    mock_page.content.return_value = "<html><body><h1>404 Not Found</h1></body></html>"
    return mock_page


# Factory fixtures for creating test data
@pytest.fixture
def bbox_factory():
    """Factory for creating BBox instances."""
    def create_bbox(x=100, y=200, text="Test", bbox_type="button", global_index=1):
        return BBox(
            x=float(x),
            y=float(y),
            text=text,
            type=bbox_type,
            ariaLabel=f"{text} {bbox_type}",
            selector=f'[data-ai-label="{global_index}"]',
            globalIndex=global_index,
            boundingBox=BoundingBox(left=float(x), top=float(y), width=80.0, height=30.0)
        )
    return create_bbox


@pytest.fixture
def state_factory(mock_browser_context):
    """Factory for creating KageBunshinState instances."""
    def create_state(input_text="Test", messages=None, clone_depth=0):
        if messages is None:
            messages = [HumanMessage(content=input_text)]
        return KageBunshinState(
            input=input_text,
            messages=messages,
            context=mock_browser_context,
            clone_depth=clone_depth
        )
    return create_state