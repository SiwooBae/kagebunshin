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
    
    def test_should_format_text_context_with_markdown(self):
        """Test formatting text context with markdown."""
        result = format_text_context("# Test Page\n\nPage Content")
        
        assert "Page Content (Markdown):" in result
        assert "# Test Page" in result
        assert "Page Content" in result

    def test_should_format_text_context_without_title(self):
        """Test formatting text context without title."""
        result = format_text_context("Just some content")
        
        assert "Just some content" in result
        assert "PAGE CONTENT:" in result.upper() or "content" in result.lower()

    def test_should_handle_empty_content(self):
        """Test handling of empty content."""
        result = format_text_context("")
        
        assert "Page Content (Markdown):" in result
        assert result is not None


class TestFormatBboxContext:
    """Test suite for bounding box context formatting."""
    
    def test_should_format_single_bbox(self, sample_bbox):
        """Test formatting a single bounding box."""
        result = format_bbox_context([sample_bbox])
        
        # The function prioritizes ariaLabel over text
        assert "Submit button" in result  # ariaLabel is used instead of text
        assert "button" in result
        assert "bbox_id:" in result
        assert "🟢 CURRENT VIEWPORT" in result

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
        
        # The function prioritizes ariaLabel over text
        assert "Submit button" in result  # First bbox ariaLabel
        assert "Cancel button" in result  # Second bbox ariaLabel
        assert "🟢 CURRENT VIEWPORT (2 elements)" in result

    def test_should_handle_empty_bbox_list(self):
        """Test handling of empty bbox list."""
        result = format_bbox_context([])
        
        assert result is not None
        assert len(result.strip()) > 0  # Should return some default message

    def test_should_include_bbox_indices(self, sample_bbox):
        """Test that bbox indices are included in output."""
        result = format_bbox_context([sample_bbox])
        
        assert str(sample_bbox.globalIndex) in result

    def test_should_show_no_elements_for_empty_viewport_sections(self, sample_bbox):
        """Test that empty viewport sections explicitly show 'No elements'."""
        # Create a bbox that's only in the current viewport
        result = format_bbox_context([sample_bbox], include_viewport_context=True)
        
        # Should show current viewport with element
        assert "🟢 CURRENT VIEWPORT (1 elements)" in result
        
        # Should explicitly show "No elements" for empty sections
        assert "⬆️  ABOVE VIEWPORT: No elements" in result
        assert "⬇️  BELOW VIEWPORT: No elements" in result  
        assert "⬅️  LEFT OF VIEWPORT: No elements" in result
        assert "➡️  RIGHT OF VIEWPORT: No elements" in result

    def test_should_show_focused_indicator_for_focused_bbox(self):
        """Test that focused elements show [FOCUSED] indicator in formatting."""
        from kagebunshin.core.state import BBox, BoundingBox
        
        # Create a focused bbox
        focused_bbox = BBox(
            x=150.0,
            y=250.0,
            text="Search input",
            type="input",
            ariaLabel="Search field",
            selector='[data-ai-label="5"]',
            globalIndex=5,
            boundingBox=BoundingBox(left=150.0, top=250.0, width=200.0, height=30.0),
            focused=True
        )
        
        result = format_bbox_context([focused_bbox])
        
        # Should show FOCUSED indicator
        assert "[FOCUSED]" in result
        assert "bbox_id: 0 [FOCUSED]" in result  # Uses array index, not globalIndex
        assert "Search field" in result  # ariaLabel should still be shown

    def test_should_not_show_focused_indicator_for_unfocused_bbox(self, sample_bbox):
        """Test that unfocused elements do not show [FOCUSED] indicator."""
        result = format_bbox_context([sample_bbox])
        
        # Should NOT show FOCUSED indicator
        assert "[FOCUSED]" not in result
        assert "bbox_id: 0" in result  # Uses array index, not globalIndex


class TestFormatTabContext:
    """Test suite for tab context formatting."""
    
    def test_should_format_single_tab(self, sample_tab_info):
        """Test formatting single tab information."""
        result = format_tab_context([sample_tab_info], 0)
        
        assert "Test Tab" in result
        assert "Browser Tabs:" in result
        assert "[CURRENT]" in result or "🟢" in result

    def test_should_format_multiple_tabs(self, sample_tab_info):
        """Test formatting multiple tabs."""
        tab2 = {
            "page": Mock(),
            "tab_index": 1,
            "title": "Second Tab",
            "url": "https://example2.com",
            "is_active": False
        }
        
        result = format_tab_context([sample_tab_info, tab2], 0)
        
        assert "Test Tab" in result
        assert "Second Tab" in result
        assert "Browser Tabs:" in result

    def test_should_indicate_active_tab(self, sample_tab_info):
        """Test that active tab is clearly indicated."""
        result = format_tab_context([sample_tab_info], 0)
        
        # Active tab should be marked somehow
        assert "[CURRENT]" in result or "🟢" in result

    def test_should_handle_empty_tab_list(self):
        """Test handling of empty tab list."""
        result = format_tab_context([], 0)
        
        assert result is not None
        assert "No tabs available" in result


class TestFormatImgContext:
    """Test suite for image context formatting."""
    
    def test_should_format_image_context_with_base64(self):
        """Test formatting image context with base64 data."""
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77mgAAAABJRU5ErkJggg=="
        
        result = format_img_context(base64_data)
        
        assert isinstance(result, dict)
        assert result["type"] == "image_url"
        assert "data:image/jpeg;base64," in result["image_url"]["url"]
        assert base64_data in result["image_url"]["url"]

    def test_should_handle_empty_base64_data(self):
        """Test handling of empty base64 data."""
        result = format_img_context("")
        
        assert isinstance(result, dict)
        assert result["type"] == "image_url"
        assert "data:image/jpeg;base64," in result["image_url"]["url"]

    def test_should_format_without_title(self):
        """Test formatting image context returns proper dict structure."""
        base64_data = "test_image_data"
        
        result = format_img_context(base64_data)
        
        assert isinstance(result, dict)
        assert result["type"] == "image_url"
        assert base64_data in result["image_url"]["url"]


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
        # Images are skipped by default (include_placeholders=False)
        assert "Text part\nMore text" == result

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
        # Images are skipped by default
        assert result == "Here is an image:"

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

    def test_should_include_image_placeholders_when_requested(self):
        """Test including image placeholders when include_placeholders=True."""
        content = [
            "Text part",
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
            "More text"
        ]
        
        result = normalize_chat_content(content, include_placeholders=True)
        
        assert "Text part" in result
        assert "More text" in result
        assert "[image:" in result or "[image]" in result