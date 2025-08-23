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
def mock_browser_context():
    """Mock Playwright BrowserContext."""
    context = AsyncMock(spec=BrowserContext)
    context.pages = []
    return context


@pytest.fixture
def mock_page():
    """Mock Playwright Page."""
    page = AsyncMock(spec=Page)
    page.url = "https://example.com"
    page.title.return_value = "Test Page"
    page.screenshot.return_value = b"fake_screenshot_data"
    page.content.return_value = "<html><body>Test content</body></html>"
    return page


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
def mock_browser_context():
    """Mock Playwright BrowserContext."""
    context = AsyncMock(spec=BrowserContext)
    context.pages = []
    return context


@pytest.fixture
def mock_page():
    """Mock Playwright Page."""
    page = AsyncMock(spec=Page)
    page.url = "https://example.com"
    page.title.return_value = "Test Page"
    page.screenshot.return_value = b"fake_screenshot_data"
    page.content.return_value = "<html><body>Test content</body></html>"
    return page


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
    return llm


@pytest.pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    redis_client = AsyncMock()
    redis_client.lpush = AsyncMock()
    redis_client.lrange = AsyncMock(return_value=[])
    redis_client.ltrim = AsyncMock()
    return redis_client


@pytest.pytest.fixture
async def state_manager(mock_browser_context, mock_page):
    """Create a KageBunshinStateManager for testing."""
    mock_browser_context.pages = [mock_page]
    manager = KageBunshinStateManager(mock_browser_context)
    return manager


@pytest.pytest.fixture
async def kage_agent(mock_browser_context, state_manager, mock_llm):
    """Create a KageBunshinAgent for testing."""
    with patch('kagebunshin.core.agent.init_chat_model', return_value=mock_llm):
        agent = KageBunshinAgent(
            context=mock_browser_context,
            state_manager=state_manager,
            system_prompt="Test system prompt"
        )
        return agent



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
    return llm


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    redis_client = AsyncMock()
    redis_client.lpush = AsyncMock()
    redis_client.lrange = AsyncMock(return_value=[])
    redis_client.ltrim = AsyncMock()
    return redis_client


@pytest.fixture
async def state_manager(mock_browser_context, mock_page):
    """Create a KageBunshinStateManager for testing."""
    mock_browser_context.pages = [mock_page]
    manager = KageBunshinStateManager(mock_browser_context)
    return manager


@pytest.fixture
async def kage_agent(mock_browser_context, state_manager, mock_llm):
    """Create a KageBunshinAgent for testing."""
    with patch('kagebunshin.core.agent.init_chat_model', return_value=mock_llm):
        agent = KageBunshinAgent(
            context=mock_browser_context,
            state_manager=state_manager,
            system_prompt="Test system prompt"
        )
        return agent