"""
Unit tests for utility formatting functions.
"""

import pytest
from unittest.mock import Mock, patch
from langchain_core.messages import HumanMessage

from kagebunshin.utils.formatting import (
    html_to_markdown,
    format_text_context,
    format_bbox_context,
    format_tab_context,
    format_img_context,
    normalize_chat_content
)
from kagebunshin.core.state import BBox, TabInfo, BoundingBox


class TestHtmlToMarkdown:
    """Test suite for HTML to markdown conversion."""
    
    def test_should_convert_basic_html_to_markdown(self):
        """Test conversion of basic HTML elements."""
        html = "<h1>Title</h1><p>This is a paragraph with <strong>bold</strong> text.</p>"
        
        result = html_to_markdown(html)
        
        assert "# Title" in result
        assert "paragraph" in result
        assert "**bold**" in result or "bold" in result  # Different markdown converters

    def test_should_handle_empty_html(self):
        """Test handling of empty HTML."""
        result = html_to_markdown("")
        
        assert result == "" or result.strip() == ""

    def test_should_handle_html_with_links(self):
        """Test conversion of HTML links."""
        html = '<p>Visit <a href="https://example.com">our website</a> for more info.</p>'
        
        result = html_to_markdown(html)
        
        assert "example.com" in result
        assert "our website" in result

    def test_should_handle_html_lists(self):
        """Test conversion of HTML lists."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        
        result = html_to_markdown(html)
        
        assert "Item 1" in result
        assert "Item 2" in result

    def test_should_strip_unnecessary_whitespace(self):
        """Test that excessive whitespace is cleaned up."""
        html = "<p>   Text with    lots of   spaces   </p>"
        
        result = html_to_markdown(html)
        
        # Should not have excessive spaces
        assert "    " not in result.strip()
        assert "Text with" in result


class TestFormatTextContext:
    """Test suite for text context formatting."""
    
    def test_should_format_text_context_with_title(self):
        """Test formatting text context with a title."""
        result = format_text_context("Page Content", title="Test Page")
        
        assert "Test Page" in result
        assert "Page Content" in result

    def test_should_format_text_context_without_title(self):
        """Test formatting text context without title."""
        result = format_text_context("Just some content")
        
        assert "Just some content" in result
        assert "PAGE CONTENT:" in result.upper() or "content" in result.lower()

    def test_should_handle_empty_content(self):
        """Test handling of empty content."""
        result = format_text_context("", title="Empty Page")
        
        assert "Empty Page" in result
        assert result is not None


class TestFormatBboxContext:
    """Test suite for bounding box context formatting."""
    
    def test_should_format_single_bbox(self, sample_bbox):
        """Test formatting a single bounding box."""
        result = format_bbox_context([sample_bbox])
        
        assert "Click me" in result
        assert "button" in result
        assert "Submit button" in result
        assert str(sample_bbox.globalIndex) in result

    def test_should_format_multiple_bboxes(self, sample_bbox):
        """Test formatting multiple bounding boxes."""
        bbox2 = BBox(
            x=200.0,
            y=300.0,
            text="Second button",
            type="button",
            ariaLabel="Cancel button",
            selector='[data-ai-label="2"]',
            globalIndex=2,
            boundingBox=BoundingBox(left=200.0, top=300.0, width=80.0, height=30.0)
        )
        
        result = format_bbox_context([sample_bbox, bbox2])
        
        assert "Click me" in result
        assert "Second button" in result
        assert "Submit button" in result
        assert "Cancel button" in result

    def test_should_handle_empty_bbox_list(self):
        """Test handling of empty bbox list."""
        result = format_bbox_context([])
        
        assert result is not None
        assert len(result.strip()) > 0  # Should return some default message

    def test_should_include_bbox_indices(self, sample_bbox):
        """Test that bbox indices are included in output."""
        result = format_bbox_context([sample_bbox])
        
        assert str(sample_bbox.globalIndex) in result


class TestFormatTabContext:
    """Test suite for tab context formatting."""
    
    def test_should_format_single_tab(self, sample_tab_info):
        """Test formatting single tab information."""
        result = format_tab_context([sample_tab_info])
        
        assert "Test Tab" in result
        assert "https://example.com" in result
        assert "active" in result.lower() or "current" in result.lower()

    def test_should_format_multiple_tabs(self, sample_tab_info):
        """Test formatting multiple tabs."""
        tab2 = TabInfo(
            page=Mock(),
            tab_index=1,
            title="Second Tab",
            url="https://example2.com",
            is_active=False
        )
        
        result = format_tab_context([sample_tab_info, tab2])
        
        assert "Test Tab" in result
        assert "Second Tab" in result
        assert "example.com" in result
        assert "example2.com" in result

    def test_should_indicate_active_tab(self, sample_tab_info):
        """Test that active tab is clearly indicated."""
        result = format_tab_context([sample_tab_info])
        
        # Active tab should be marked somehow
        assert "active" in result.lower() or "*" in result or "current" in result.lower()

    def test_should_handle_empty_tab_list(self):
        """Test handling of empty tab list."""
        result = format_tab_context([])
        
        assert result is not None


class TestFormatImgContext:
    """Test suite for image context formatting."""
    
    def test_should_format_image_context_with_base64(self):
        """Test formatting image context with base64 data."""
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77mgAAAABJRU5ErkJggg=="
        
        result = format_img_context(base64_data, title="Test Screenshot")
        
        assert "Test Screenshot" in result
        # Should contain image format information
        assert "image" in result.lower() or "screenshot" in result.lower()

    def test_should_handle_empty_base64_data(self):
        """Test handling of empty base64 data."""
        result = format_img_context("", title="Empty Image")
        
        assert "Empty Image" in result
        assert result is not None

    def test_should_format_without_title(self):
        """Test formatting image context without title."""
        base64_data = "test_image_data"
        
        result = format_img_context(base64_data)
        
        assert result is not None
        assert len(result) > 0


class TestNormalizeChatContent:
    """Test suite for chat content normalization."""
    
    def test_should_normalize_string_content(self):
        """Test normalizing simple string content."""
        result = normalize_chat_content("Simple text message")
        
        assert result == "Simple text message"

    def test_should_normalize_list_content(self):
        """Test normalizing list content with mixed types."""
        content = [
            "Text part",
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
            "More text"
        ]
        
        result = normalize_chat_content(content)
        
        assert "Text part" in result
        assert "More text" in result
        assert "[Image]" in result or "image" in result.lower()

    def test_should_handle_dict_content(self):
        """Test handling of dictionary content."""
        content = {"text": "Dictionary message", "metadata": "extra"}
        
        result = normalize_chat_content(content)
        
        assert isinstance(result, str)
        assert len(result) > 0

    def test_should_handle_none_content(self):
        """Test handling of None content."""
        result = normalize_chat_content(None)
        
        assert result == "" or result is None

    def test_should_handle_numeric_content(self):
        """Test handling of numeric content."""
        result = normalize_chat_content(12345)
        
        assert result == "12345"

    def test_should_extract_text_from_image_url_dict(self):
        """Test extraction of text from image URL dictionary."""
        content = [
            {"type": "text", "text": "Here is an image:"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,test123"}}
        ]
        
        result = normalize_chat_content(content)
        
        assert "Here is an image:" in result
        # Should indicate image presence somehow
        assert "[Image]" in result or "image" in result.lower()

    def test_should_handle_complex_nested_content(self):
        """Test handling of complex nested content structures."""
        content = [
            "Start text",
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,/9j/test"
                }
            },
            ["nested", "list"],
            42,
            {"type": "text", "text": "End text"}
        ]
        
        result = normalize_chat_content(content)
        
        assert "Start text" in result
        assert "End text" in result
        assert isinstance(result, str)
        assert len(result) > 0