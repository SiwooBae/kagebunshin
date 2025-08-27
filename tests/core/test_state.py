"""
Unit tests for KageBunshin state models.
"""

import pytest
from unittest.mock import Mock
from pydantic import ValidationError

from kagebunshin.core.state import (
    BBox, 
    BoundingBox, 
    HierarchyInfo, 
    FrameStats, 
    Annotation, 
    TabInfo, 
    KageBunshinState
)
from langchain_core.messages import HumanMessage


class TestBoundingBox:
    """Test suite for BoundingBox model."""
    
    def test_should_create_bounding_box_with_valid_data(self):
        """Test creating BoundingBox with valid coordinates."""
        bbox = BoundingBox(left=10.5, top=20.0, width=100.0, height=50.0)
        
        assert bbox.left == 10.5
        assert bbox.top == 20.0
        assert bbox.width == 100.0
        assert bbox.height == 50.0

    def test_should_accept_integer_coordinates(self):
        """Test that BoundingBox accepts integer coordinates."""
        bbox = BoundingBox(left=10, top=20, width=100, height=50)
        
        assert bbox.left == 10.0
        assert bbox.top == 20.0
        assert bbox.width == 100.0
        assert bbox.height == 50.0


class TestHierarchyInfo:
    """Test suite for HierarchyInfo model."""
    
    def test_should_create_hierarchy_info_with_defaults(self):
        """Test creating HierarchyInfo with default values."""
        hierarchy = HierarchyInfo(
            depth=3,
            siblingIndex=2,
            totalSiblings=5,
            childrenCount=10,
            interactiveChildrenCount=3,
            semanticRole="button"
        )
        
        assert hierarchy.depth == 3
        assert hierarchy.siblingIndex == 2
        assert hierarchy.totalSiblings == 5
        assert hierarchy.childrenCount == 10
        assert hierarchy.interactiveChildrenCount == 3
        assert hierarchy.semanticRole == "button"
        assert hierarchy.hierarchy == []  # Default empty list

    def test_should_create_hierarchy_info_with_custom_hierarchy(self):
        """Test creating HierarchyInfo with custom hierarchy path."""
        hierarchy_path = [
            {"tag": "html", "class": ""},
            {"tag": "body", "class": "main"},
            {"tag": "div", "class": "container"}
        ]
        
        hierarchy = HierarchyInfo(
            depth=2,
            hierarchy=hierarchy_path,
            siblingIndex=0,
            totalSiblings=1,
            childrenCount=0,
            interactiveChildrenCount=0,
            semanticRole="generic"
        )
        
        assert hierarchy.hierarchy == hierarchy_path


class TestBBox:
    """Test suite for BBox model."""
    
    def test_should_create_bbox_with_required_fields(self):
        """Test creating BBox with all required fields."""
        bbox = BBox(
            x=100.0,
            y=200.0,
            text="Click me",
            type="button",
            ariaLabel="Submit button",
            selector='[data-ai-label="1"]',
            globalIndex=1,
            boundingBox=BoundingBox(left=100.0, top=200.0, width=80.0, height=30.0)
        )
        
        assert bbox.x == 100.0
        assert bbox.y == 200.0
        assert bbox.text == "Click me"
        assert bbox.type == "button"
        assert bbox.ariaLabel == "Submit button"
        assert bbox.selector == '[data-ai-label="1"]'
        assert bbox.globalIndex == 1
        assert bbox.isCaptcha is False  # Default value

    def test_should_parse_captcha_field_correctly(self):
        """Test that isCaptcha field is parsed correctly from various inputs."""
        # Test with boolean True
        bbox1 = BBox(
            x=0, y=0, text="", type="", ariaLabel="", selector="", 
            globalIndex=0, boundingBox=BoundingBox(left=0, top=0, width=0, height=0),
            isCaptcha=True
        )
        assert bbox1.isCaptcha is True
        
        # Test with string 'true'
        bbox2 = BBox(
            x=0, y=0, text="", type="", ariaLabel="", selector="", 
            globalIndex=0, boundingBox=BoundingBox(left=0, top=0, width=0, height=0),
            isCaptcha="true"
        )
        assert bbox2.isCaptcha is True
        
        # Test with empty string (should be False)
        bbox3 = BBox(
            x=0, y=0, text="", type="", ariaLabel="", selector="", 
            globalIndex=0, boundingBox=BoundingBox(left=0, top=0, width=0, height=0),
            isCaptcha=""
        )
        assert bbox3.isCaptcha is False

    def test_should_have_default_values_for_optional_fields(self):
        """Test that optional fields have correct default values."""
        bbox = BBox(
            x=0, y=0, text="", type="", ariaLabel="", selector="", 
            globalIndex=0, boundingBox=BoundingBox(left=0, top=0, width=0, height=0)
        )
        
        assert bbox.isCaptcha is False
        assert bbox.className is None
        assert bbox.elementId is None
        assert bbox.frameContext == "main"
        assert bbox.viewportPosition == "in-viewport"
        assert bbox.distanceFromViewport == 0
        assert bbox.focused is False  # Default value

    def test_should_create_bbox_with_focused_true(self):
        """Test creating BBox with focused=True."""
        bbox = BBox(
            x=100.0,
            y=200.0,
            text="Search input",
            type="input",
            ariaLabel="Search field",
            selector='[data-ai-label="5"]',
            globalIndex=5,
            boundingBox=BoundingBox(left=100.0, top=200.0, width=200.0, height=30.0),
            focused=True
        )
        
        assert bbox.focused is True
        assert bbox.x == 100.0
        assert bbox.type == "input"

    def test_should_create_bbox_with_focused_false_explicitly(self):
        """Test creating BBox with focused=False explicitly set."""
        bbox = BBox(
            x=50.0,
            y=100.0,
            text="Submit",
            type="button",
            ariaLabel="Submit form",
            selector='[data-ai-label="10"]',
            globalIndex=10,
            boundingBox=BoundingBox(left=50.0, top=100.0, width=80.0, height=30.0),
            focused=False
        )
        
        assert bbox.focused is False
        assert bbox.x == 50.0
        assert bbox.type == "button"


class TestFrameStats:
    """Test suite for FrameStats model."""
    
    def test_should_create_frame_stats_with_valid_data(self):
        """Test creating FrameStats with frame processing data."""
        stats = FrameStats(
            totalFrames=5,
            accessibleFrames=3,
            maxDepth=2
        )
        
        assert stats.totalFrames == 5
        assert stats.accessibleFrames == 3
        assert stats.maxDepth == 2


class TestAnnotation:
    """Test suite for Annotation model."""
    
    def test_should_create_annotation_with_required_fields(self, sample_bbox):
        """Test creating Annotation with required fields."""
        annotation = Annotation(
            img="base64_image_data",
            bboxes=[sample_bbox],
            markdown="# Page Title\n\nContent here"
        )
        
        assert annotation.img == "base64_image_data"
        assert len(annotation.bboxes) == 1
        assert annotation.bboxes[0] == sample_bbox
        assert annotation.markdown == "# Page Title\n\nContent here"
        assert annotation.totalElements == 0  # Default value

    def test_should_create_annotation_with_enhanced_data(self, sample_bbox):
        """Test creating Annotation with enhanced data fields."""
        viewport_categories = {"in-viewport": 5, "below-fold": 3}
        frame_stats = FrameStats(totalFrames=2, accessibleFrames=2, maxDepth=1)
        
        annotation = Annotation(
            img="base64_image_data",
            bboxes=[sample_bbox],
            markdown="# Page Title",
            viewportCategories=viewport_categories,
            frameStats=frame_stats,
            totalElements=8
        )
        
        assert annotation.viewportCategories == viewport_categories
        assert annotation.frameStats == frame_stats
        assert annotation.totalElements == 8


class TestTabInfo:
    """Test suite for TabInfo TypedDict."""
    
    def test_should_create_tab_info_with_required_fields(self, mock_page):
        """Test creating TabInfo with all required fields."""
        tab_info = TabInfo(
            page=mock_page,
            tab_index=0,
            title="Test Page",
            url="https://example.com",
            is_active=True
        )
        
        assert tab_info["page"] == mock_page
        assert tab_info["tab_index"] == 0
        assert tab_info["title"] == "Test Page"
        assert tab_info["url"] == "https://example.com"
        assert tab_info["is_active"] is True


class TestKageBunshinState:
    """Test suite for KageBunshinState TypedDict."""
    
    def test_should_create_state_with_required_fields(self, mock_browser_context):
        """Test creating KageBunshinState with all required fields."""
        messages = [HumanMessage(content="Hello")]
        
        state = KageBunshinState(
            input="Test query",
            messages=messages,
            context=mock_browser_context,
            clone_depth=0
        )
        
        assert state["input"] == "Test query"
        assert state["messages"] == messages
        assert state["context"] == mock_browser_context
        assert state["clone_depth"] == 0

    def test_should_handle_empty_messages_list(self, mock_browser_context):
        """Test that state can be created with empty messages list."""
        state = KageBunshinState(
            input="",
            messages=[],
            context=mock_browser_context,
            clone_depth=0
        )
        
        assert len(state["messages"]) == 0
        assert state["input"] == ""

    def test_should_handle_different_clone_depths(self, mock_browser_context):
        """Test that state correctly handles different clone depths."""
        state1 = KageBunshinState(
            input="root agent task",
            messages=[],
            context=mock_browser_context,
            clone_depth=0
        )
        
        state2 = KageBunshinState(
            input="clone agent task",
            messages=[],
            context=mock_browser_context,
            clone_depth=2
        )
        
        assert state1["clone_depth"] == 0
        assert state2["clone_depth"] == 2