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
        
        with pytest.raises(ValueError, match="No pages available in browser context"):
            state_manager.get_current_page()

    def test_should_get_browser_context_from_state(self, state_manager, sample_state):
        """Test getting browser context from state."""
        state_manager.set_state(sample_state)
        
        context = state_manager.get_context()
        
        assert context == sample_state["context"]

    def test_should_raise_error_when_context_is_none(self, state_manager, mock_browser_context):
        """Test that None context in state raises appropriate error."""
        # Create a state with None context (simulating the reported issue)
        state_with_none_context = {
            "input": "test",
            "messages": [],
            "context": None,  # This is what was causing the original error
            "clone_depth": 0
        }
        
        # set_state should now catch this and raise an error
        with pytest.raises(ValueError, match="State must contain a valid browser context"):
            state_manager.set_state(state_with_none_context)
            
    def test_should_handle_extract_page_content_with_none_context(self, state_manager):
        """Test that extract_page_content handles None context gracefully."""
        # Manually set a state with None context to test the extract_page_content error handling
        state_manager.current_state = {
            "input": "test", 
            "messages": [],
            "context": None,
            "clone_depth": 0
        }
        
        # This should now return a proper error message instead of crashing
        import asyncio
        result = asyncio.run(state_manager.extract_page_content())
        
        assert "Error extracting page content" in result
        assert "Browser context is None" in result

    def test_should_get_tools_for_llm(self, state_manager):
        """Test that state manager provides tools for LLM binding."""
        tools = state_manager.get_tools_for_llm()
        
        assert isinstance(tools, list)
        assert len(tools) > 0
        # Verify some expected tool names exist
        tool_names = [tool.name for tool in tools]
        expected_tools = ['click', 'type_text', 'scroll', 'refresh', 'extract_page_content', 
                         'go_back', 'go_forward', 'hover', 'press_key', 'drag', 'wait_for', 
                         'browser_goto', 'browser_select_option', 'list_tabs', 'switch_tab', 
                         'open_new_tab', 'close_tab', 'take_note']
        for expected_tool in expected_tools:
            assert expected_tool in tool_names

    @pytest.mark.asyncio
    async def test_should_get_current_page_data(self, state_manager, mock_page, sample_state):
        """Test getting current page data with annotation."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.annotate_page') as mock_annotate:
                mock_annotation = Mock(spec=Annotation)
                mock_annotation.bboxes = [Mock()]
                mock_annotate.return_value = mock_annotation
                
                result = await state_manager.get_current_page_data()
                
                assert result == mock_annotation
                assert state_manager.prev_snapshot == mock_annotation
                assert state_manager.current_bboxes == mock_annotation.bboxes

    @pytest.mark.asyncio
    async def test_should_navigate_to_url(self, state_manager, mock_page, sample_state):
        """Test navigating to a URL."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.smart_delay_between_actions') as mock_delay:
                result = await state_manager.browser_goto("https://example.com")
                
                mock_page.goto.assert_called_once_with("https://example.com")
                mock_delay.assert_called_once()
                assert "Successfully navigated" in result

    @pytest.mark.asyncio 
    async def test_should_click_element_by_bbox_id(self, state_manager, mock_page, sample_state, sample_bbox):
        """Test clicking an element by bbox_id."""
        state_manager.set_state(sample_state)
        state_manager.current_bboxes = [sample_bbox]
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch.object(state_manager, '_capture_page_state') as mock_capture:
                mock_capture.side_effect = [("url1", "hash1", 1), ("url2", "hash2", 1)]
                
                result = await state_manager.click(0)
                
                assert "Successfully clicked" in result
                assert state_manager._action_count > 0

    @pytest.mark.asyncio
    async def test_should_type_text_in_element(self, state_manager, mock_page, sample_state, sample_bbox):
        """Test typing text in an element."""
        state_manager.set_state(sample_state)
        state_manager.current_bboxes = [sample_bbox]
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch.object(state_manager, '_capture_page_state') as mock_capture:
                mock_capture.side_effect = [("url1", "hash1", 1), ("url2", "hash2", 1)]
                
                result = await state_manager.type_text(0, "test input")
                
                assert "Successfully typed" in result
                assert state_manager._action_count > 0

    @pytest.mark.asyncio
    async def test_should_scroll_page(self, state_manager, mock_page, sample_state):
        """Test scrolling the page."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.human_scroll') as mock_scroll:
                with patch('kagebunshin.core.state_manager.smart_delay_between_actions'):
                    result = await state_manager.scroll("page", "down")
                    
                    mock_scroll.assert_called_once()
                    assert "Successfully scrolled" in result

    @pytest.mark.asyncio
    async def test_should_extract_page_content(self, state_manager, mock_page, sample_state):
        """Test extracting page content."""
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Test Page"
        mock_page.content.return_value = "<html><body>Test content</body></html>"
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.html_to_markdown') as mock_converter:
                mock_converter.return_value = "Test content"
                
                result = await state_manager.extract_page_content()
                
                assert "Test Page" in result
                assert "Test content" in result
                mock_converter.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_extract_pdf_page_content(self, state_manager, mock_page, sample_state):
        """Test extracting PDF page content."""
        mock_page.url = "https://example.com/document.pdf"
        mock_page.title.return_value = "Test PDF"
        mock_page.content.return_value = '<html><embed type="application/pdf" src="document.pdf"></embed></html>'
        
        # Mock the request context and response for PDF content
        mock_request_context = AsyncMock()
        mock_response = AsyncMock()
        mock_response.body.return_value = b"fake pdf content"
        mock_request_context.get.return_value = mock_response
        mock_page.context.request = mock_request_context
        
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('pypdf.PdfReader') as mock_pdf_reader:
                # Mock PDF reader to return some text
                mock_page_obj = Mock()
                mock_page_obj.extract_text.return_value = "This is test PDF content extracted from the document."
                mock_reader_instance = Mock()
                mock_reader_instance.pages = [mock_page_obj]
                mock_pdf_reader.return_value = mock_reader_instance
                
                result = await state_manager.extract_page_content()
                
                assert "Test PDF" in result
                assert "Content Type: PDF Document" in result
                assert "This is test PDF content extracted from the document." in result
                mock_pdf_reader.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_handle_pdf_extraction_error(self, state_manager, mock_page, sample_state):
        """Test handling PDF extraction errors gracefully."""
        mock_page.url = "https://example.com/document.pdf"
        mock_page.title.return_value = "Test PDF"
        mock_page.content.return_value = '<html><embed type="application/pdf" src="document.pdf"></embed></html>'
        
        # Mock the request context to fail
        mock_request_context = AsyncMock()
        mock_request_context.get.side_effect = Exception("Network error")
        mock_page.context.request = mock_request_context
        
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            result = await state_manager.extract_page_content()
            
            assert "Test PDF" in result
            assert "Content Type: PDF Document" in result
            assert "Error: Failed to extract text from PDF" in result
            assert "Network error" in result

    @pytest.mark.asyncio
    async def test_should_refresh_page(self, state_manager, mock_page, sample_state):
        """Test refreshing the current page."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            result = await state_manager.refresh()
            
            mock_page.reload.assert_called_once()
            assert "Successfully refreshed" in result

    @pytest.mark.asyncio
    async def test_should_go_back(self, state_manager, mock_page, sample_state):
        """Test navigating back in browser history."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.smart_delay_between_actions'):
                result = await state_manager.go_back()
                
                mock_page.go_back.assert_called_once()
                assert "Successfully navigated back" in result

    @pytest.mark.asyncio
    async def test_should_go_forward(self, state_manager, mock_page, sample_state):
        """Test navigating forward in browser history."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            with patch('kagebunshin.core.state_manager.smart_delay_between_actions'):
                result = await state_manager.go_forward()
                
                mock_page.go_forward.assert_called_once()
                assert "Successfully navigated forward" in result

    @pytest.mark.asyncio
    async def test_should_hover_over_element(self, state_manager, mock_page, sample_state, sample_bbox):
        """Test hovering over an element."""
        state_manager.set_state(sample_state)
        state_manager.current_bboxes = [sample_bbox]
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            result = await state_manager.hover(0)
            
            mock_page.hover.assert_called_once_with(sample_bbox.selector, timeout=3000)
            assert "Hovered over" in result

    @pytest.mark.asyncio
    async def test_should_press_key(self, state_manager, mock_page, sample_state):
        """Test pressing a keyboard key."""
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_current_page', return_value=mock_page):
            result = await state_manager.press_key("Enter")
            
            mock_page.keyboard.press.assert_called_once_with("Enter")
            assert "Pressed key" in result

    @pytest.mark.asyncio
    async def test_should_list_tabs(self, state_manager, mock_page, sample_state):
        """Test listing browser tabs."""
        mock_page.title.return_value = "Test Tab"
        mock_page.url = "https://example.com"
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_tabs') as mock_get_tabs:
            mock_get_tabs.return_value = [{
                "tab_index": 0,
                "title": "Test Tab", 
                "url": "https://example.com",
                "is_active": True
            }]
            
            result = await state_manager.list_tabs()
            
            assert "Available tabs:" in result
            assert "Test Tab" in result

    @pytest.mark.asyncio
    async def test_should_switch_tab(self, state_manager, mock_page, sample_state):
        """Test switching to a different tab."""
        mock_page.title.return_value = "Test Tab"
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_context') as mock_get_context:
            mock_get_context.return_value.pages = [mock_page, mock_page]
            
            result = await state_manager.switch_tab(1)
            
            mock_page.bring_to_front.assert_called()
            assert "Successfully switched" in result

    @pytest.mark.asyncio
    async def test_should_open_new_tab(self, state_manager, sample_state):
        """Test opening a new browser tab."""
        mock_context = AsyncMock(spec=BrowserContext)
        mock_new_page = AsyncMock(spec=Page)
        mock_context.new_page.return_value = mock_new_page
        mock_context.pages = [mock_new_page]
        
        state_manager.set_state(sample_state)
        
        with patch.object(state_manager, 'get_context', return_value=mock_context):
            result = await state_manager.open_new_tab("https://example.com")
            
            mock_context.new_page.assert_called_once()
            mock_new_page.goto.assert_called_once_with("https://example.com")
            assert "Successfully opened" in result

    @pytest.mark.asyncio
    async def test_should_close_tab(self, state_manager, sample_state):
        """Test closing a browser tab."""
        mock_page1 = AsyncMock(spec=Page)
        mock_page2 = AsyncMock(spec=Page)
        mock_page1.title.return_value = "Tab 1"
        mock_context = AsyncMock(spec=BrowserContext)
        mock_context.pages = [mock_page1, mock_page2]
        
        state_manager.set_state(sample_state)
        state_manager.current_page_index = 1
        
        with patch.object(state_manager, 'get_context', return_value=mock_context):
            result = await state_manager.close_tab(1)
            
            mock_page2.close.assert_called_once()
            assert "Successfully closed" in result

    def test_should_take_note(self, state_manager):
        """Test taking a note."""
        result = state_manager.take_note("This is a test note")
        
        assert "Note recorded" in result

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

    def test_should_get_bbox_by_id(self, state_manager, sample_bbox):
        """Test getting bbox by ID."""
        state_manager.current_bboxes = [sample_bbox]
        
        result = state_manager._get_bbox_by_id(0)
        
        assert result == sample_bbox

    def test_should_return_none_for_invalid_bbox_id(self, state_manager):
        """Test that invalid bbox ID returns None."""
        result = state_manager._get_bbox_by_id(999)
        
        assert result is None

    def test_should_get_selector_from_bbox(self, state_manager, sample_bbox):
        """Test getting CSS selector from bbox."""
        state_manager.current_bboxes = [sample_bbox]
        
        selector = state_manager._get_selector(0)
        
        assert selector == sample_bbox.selector

    def test_should_raise_error_for_invalid_bbox_selector(self, state_manager):
        """Test that invalid bbox ID raises error in selector method."""
        with pytest.raises(ValueError, match="Invalid bbox_id"):
            state_manager._get_selector(999)

    def test_should_increment_action_count(self, state_manager):
        """Test incrementing action count."""
        initial_count = state_manager._action_count
        
        state_manager.increment_action_count()
        
        assert state_manager._action_count == initial_count + 1

    def test_should_get_action_count_property(self, state_manager):
        """Test getting action count via property."""
        state_manager._action_count = 5
        
        assert state_manager.num_actions_done == 5

    def test_should_get_bboxes_property(self, state_manager, sample_bbox):
        """Test getting bboxes via property."""
        state_manager.current_bboxes = [sample_bbox]
        
        bboxes = state_manager.bboxes
        
        assert len(bboxes) == 1
        assert bboxes[0] == sample_bbox
        # Should return a copy, not the original
        assert bboxes is not state_manager.current_bboxes