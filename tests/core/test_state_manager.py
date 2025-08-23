"""
Unit tests for KageBunshinStateManager.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from playwright.async_api import Page, BrowserContext

from kagebunshin.core.state_manager import KageBunshinStateManager
from kagebunshin.core.state import KageBunshinState, BBox, Annotation


class TestKageBunshinStateManager:
    """Test suite for KageBunshinStateManager browser operations."""
    
    def test_should_initialize_with_browser_context(self, mock_browser_context):
        """Test state manager initialization with browser context."""
        manager = KageBunshinStateManager(mock_browser_context)
        
        assert manager.current_state["context"] == mock_browser_context
        assert len(manager.current_bboxes) == 0
        assert manager._action_count == 0
        assert manager.current_page_index == 0

    @pytest.mark.asyncio
    async def test_should_create_new_page_when_none_exists(self):
        """Test that factory method creates a new page when context has none."""
        mock_context = AsyncMock(spec=BrowserContext)
        mock_context.pages = []
        mock_page = AsyncMock(spec=Page)
        mock_context.new_page.return_value = mock_page
        
        with patch('kagebunshin.core.state_manager.apply_fingerprint_profile') as mock_fingerprint:
            manager = await KageBunshinStateManager.create(mock_context)
            
            mock_context.new_page.assert_called_once()
            mock_fingerprint.assert_called_once_with(mock_page)
            mock_page.goto.assert_called_once_with("https://www.google.com")

    @pytest.mark.asyncio
    async def test_should_use_existing_page_when_available(self):
        """Test that factory method uses existing pages when available."""
        mock_context = AsyncMock(spec=BrowserContext)
        mock_page = AsyncMock(spec=Page)
        mock_context.pages = [mock_page]
        
        manager = await KageBunshinStateManager.create(mock_context)
        
        mock_context.new_page.assert_not_called()
        assert isinstance(manager, KageBunshinStateManager)

    def test_should_set_state_and_reset_derived_data(self, state_manager, sample_state):
        """Test that setting state resets derived data."""
        state_manager.current_bboxes = [Mock()]  # Add some data
        
        state_manager.set_state(sample_state)
        
        assert state_manager.current_state == sample_state
        assert len(state_manager.current_bboxes) == 0

    def test_should_get_current_page_from_state(self, state_manager, mock_page, mock_browser_context):
        """Test getting the current page from browser context."""
        mock_browser_context.pages = [mock_page]
        state = KageBunshinState(
            input="test",
            messages=[],
            context=mock_browser_context,
            clone_depth=0
        )
        state_manager.set_state(state)
        
        current_page = state_manager.get_current_page()
        
        assert current_page == mock_page

    def test_should_raise_error_when_no_state_set(self):
        """Test that methods raise error when no state is set."""
        manager = KageBunshinStateManager(Mock())
        manager.current_state = None
        
        with pytest.raises(ValueError, match="No state set"):
            manager.get_current_page()

    def test_should_raise_error_for_invalid_page_index(self, state_manager, mock_browser_context):
        """Test that invalid page index raises error."""
        mock_browser_context.pages = []
        state = KageBunshinState(
            input="test",
            messages=[],
            context=mock_browser_context,
            clone_depth=0
        )
        state_manager.set_state(state)
        
        with pytest.raises(ValueError, match="Invalid page index"):
            state_manager.get_current_page()

    def test_should_get_browser_context_from_state(self, state_manager, sample_state):
        """Test getting browser context from state."""
        state_manager.set_state(sample_state)
        
        context = state_manager.get_context()
        
        assert context == sample_state["context"]

    def test_should_get_tools_for_llm(self, state_manager):
        """Test that state manager provides tools for LLM binding."""
        tools = state_manager.get_tools_for_llm()
        
        assert isinstance(tools, list)
        assert len(tools) > 0
        # Verify some expected tool names exist
        tool_names = [tool.name for tool in tools]
        expected_tools = ['goto_url', 'click', 'type_text', 'take_screenshot']
        for expected_tool in expected_tools:
            assert expected_tool in tool_names

    @pytest.mark.asyncio
    async def test_should_take_screenshot_of_current_page(self, state_manager, mock_page, sample_state):
        """Test taking screenshot of the current page."""
        mock_page.screenshot.return_value = b"screenshot_data"
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            screenshot_data = await state_manager._take_screenshot()
            
            assert screenshot_data == b"screenshot_data"
            mock_page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_navigate_to_url(self, state_manager, mock_page, sample_state):
        """Test navigating to a URL."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch.object(state_manager, 'smart_delay_between_actions') as mock_delay:
                await state_manager._goto_url("https://example.com")
                
                mock_page.goto.assert_called_once_with("https://example.com")
                mock_delay.assert_called_once()

    @pytest.mark.asyncio 
    async def test_should_click_element_by_selector(self, state_manager, mock_page, sample_state, sample_bbox):
        """Test clicking an element by selector."""
        state_manager.set_state(sample_state)
        state_manager.current_bboxes = [sample_bbox]
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.get_random_offset_in_bbox') as mock_offset:
                with patch('kagebunshin.core.state_manager.human_mouse_move') as mock_move:
                    mock_offset.return_value = (150, 220)
                    
                    await state_manager._click('[data-ai-label="1"]')
                    
                    mock_page.click.assert_called_once()
                    mock_move.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_type_text_in_element(self, state_manager, mock_page, sample_state):
        """Test typing text in an element."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.human_type_text') as mock_type:
                await state_manager._type_text('[data-ai-label="1"]', "test input")
                
                mock_page.click.assert_called_once_with('[data-ai-label="1"]')
                mock_type.assert_called_once_with(mock_page, "test input")

    @pytest.mark.asyncio
    async def test_should_scroll_page(self, state_manager, mock_page, sample_state):
        """Test scrolling the page."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.human_scroll') as mock_scroll:
                await state_manager._scroll("down", 3)
                
                mock_scroll.assert_called_once_with(mock_page, "down", 3)

    @pytest.mark.asyncio
    async def test_should_extract_page_text(self, state_manager, mock_page, sample_state):
        """Test extracting text from page."""
        mock_page.content.return_value = "<html><body>Test content</body></html>"
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.html_to_markdown') as mock_converter:
                mock_converter.return_value = "Test content"
                
                result = await state_manager._extract_text()
                
                assert "Test content" in result
                mock_converter.assert_called_once()

    def test_should_initialize_summarizer_llm_when_available(self, mock_browser_context):
        """Test that summarizer LLM is initialized when available."""
        with patch('kagebunshin.core.state_manager.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            
            manager = KageBunshinStateManager(mock_browser_context)
            
            assert manager.summarizer_llm == mock_llm

    def test_should_handle_summarizer_llm_initialization_failure(self, mock_browser_context):
        """Test graceful handling when summarizer LLM fails to initialize."""
        with patch('kagebunshin.core.state_manager.init_chat_model') as mock_init:
            mock_init.side_effect = Exception("LLM init failed")
            
            manager = KageBunshinStateManager(mock_browser_context)
            
            assert manager.summarizer_llm is None