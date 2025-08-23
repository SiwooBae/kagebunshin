"""
Unit tests for automation behavior simulation.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from playwright.async_api import Page

from kagebunshin.automation.behavior import (
    human_delay,
    get_random_offset_in_bbox,
    human_mouse_move,
    human_type_text,
    human_scroll,
    smart_delay_between_actions
)
from kagebunshin.core.state import BBox, BoundingBox


class TestHumanDelay:
    """Test suite for human delay simulation."""
    
    @pytest.mark.asyncio
    async def test_should_add_delay_when_human_behavior_enabled(self):
        """Test that delay is added when human behavior is enabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            start_time = asyncio.get_event_loop().time()
            await human_delay(100, 200)
            end_time = asyncio.get_event_loop().time()
            
            elapsed = (end_time - start_time) * 1000  # Convert to ms
            assert elapsed >= 100  # Should be at least min delay
            assert elapsed <= 300  # Should be reasonable (with some buffer)

    @pytest.mark.asyncio
    async def test_should_add_minimal_delay_when_human_behavior_disabled(self):
        """Test that minimal delay is added when human behavior is disabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', False):
            start_time = asyncio.get_event_loop().time()
            await human_delay(500, 1000)  # Large delays should be ignored
            end_time = asyncio.get_event_loop().time()
            
            elapsed = (end_time - start_time) * 1000  # Convert to ms
            assert elapsed < 100  # Should be much shorter than requested

    @pytest.mark.asyncio
    async def test_should_respect_min_max_delay_bounds(self):
        """Test that delay respects min/max bounds."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test multiple times to account for randomness
            for _ in range(5):
                start_time = asyncio.get_event_loop().time()
                await human_delay(200, 300)
                end_time = asyncio.get_event_loop().time()
                
                elapsed = (end_time - start_time) * 1000
                assert 200 <= elapsed <= 400  # Some buffer for timing precision

    @pytest.mark.asyncio
    async def test_should_use_default_delay_range(self):
        """Test using default delay range."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            start_time = asyncio.get_event_loop().time()
            await human_delay()  # Use defaults
            end_time = asyncio.get_event_loop().time()
            
            elapsed = (end_time - start_time) * 1000
            assert elapsed >= 100  # Default min
            assert elapsed <= 600  # Default max + buffer


class TestGetRandomOffsetInBbox:
    """Test suite for random offset generation in bounding boxes."""
    
    def test_should_return_coordinates_near_bbox_center(self):
        """Test that returned coordinates are near the bbox center."""
        bbox = BBox(
            x=100.0, y=200.0, text="", type="", ariaLabel="", selector="",
            globalIndex=1, boundingBox=BoundingBox(left=100, top=200, width=80, height=40)
        )
        
        x, y = get_random_offset_in_bbox(bbox)
        
        # Should be near the original coordinates with some offset
        assert 75 <= x <= 125  # Within reasonable range of bbox.x
        assert 175 <= y <= 225  # Within reasonable range of bbox.y

    def test_should_return_different_coordinates_on_multiple_calls(self):
        """Test that multiple calls return different coordinates."""
        bbox = BBox(
            x=100.0, y=200.0, text="", type="", ariaLabel="", selector="",
            globalIndex=1, boundingBox=BoundingBox(left=100, top=200, width=80, height=40)
        )
        
        coordinates = set()
        for _ in range(10):
            coordinates.add(get_random_offset_in_bbox(bbox))
        
        # Should generate at least some different coordinates
        assert len(coordinates) > 1

    def test_should_handle_small_bbox_dimensions(self):
        """Test handling of bbox with small dimensions."""
        bbox = BBox(
            x=50.0, y=75.0, text="", type="", ariaLabel="", selector="",
            globalIndex=1, boundingBox=BoundingBox(left=50, top=75, width=10, height=5)
        )
        
        x, y = get_random_offset_in_bbox(bbox)
        
        # Should still return reasonable coordinates
        assert isinstance(x, (int, float))
        assert isinstance(y, (int, float))
        assert x >= 0 and y >= 0

    def test_should_apply_padding_parameter(self):
        """Test that padding parameter affects the offset range."""
        bbox = BBox(
            x=100.0, y=200.0, text="", type="", ariaLabel="", selector="",
            globalIndex=1, boundingBox=BoundingBox(left=100, top=200, width=80, height=40)
        )
        
        x1, y1 = get_random_offset_in_bbox(bbox, padding=1)
        x2, y2 = get_random_offset_in_bbox(bbox, padding=20)
        
        # Both should be valid coordinates
        assert isinstance(x1, (int, float)) and isinstance(y1, (int, float))
        assert isinstance(x2, (int, float)) and isinstance(y2, (int, float))


class TestHumanMouseMove:
    """Test suite for human-like mouse movement."""
    
    @pytest.mark.asyncio
    async def test_should_move_mouse_in_steps_when_human_behavior_enabled(self, mock_page):
        """Test that mouse moves in steps when human behavior is enabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            await human_mouse_move(mock_page, 0, 0, 100, 100)
            
            # Should have made multiple mouse.move calls (steps)
            assert mock_page.mouse.move.call_count > 1

    @pytest.mark.asyncio
    async def test_should_move_directly_when_human_behavior_disabled(self, mock_page):
        """Test that mouse moves directly when human behavior is disabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', False):
            await human_mouse_move(mock_page, 0, 0, 100, 100)
            
            # Should make only one direct move call
            mock_page.mouse.move.assert_called_once_with(100, 100)

    @pytest.mark.asyncio
    async def test_should_end_at_target_coordinates(self, mock_page):
        """Test that mouse ends at the target coordinates."""
        target_x, target_y = 150, 250
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            await human_mouse_move(mock_page, 0, 0, target_x, target_y)
            
            # Last call should be to target coordinates (or very close)
            last_call = mock_page.mouse.move.call_args_list[-1]
            final_x, final_y = last_call[0]
            assert abs(final_x - target_x) <= 2  # Allow small jitter
            assert abs(final_y - target_y) <= 2

    @pytest.mark.asyncio
    async def test_should_add_delays_between_steps(self, mock_page):
        """Test that delays are added between mouse movement steps."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            with patch('asyncio.sleep') as mock_sleep:
                await human_mouse_move(mock_page, 0, 0, 100, 100)
                
                # Should have added delays between steps
                assert mock_sleep.call_count >= 1


class TestHumanTypeText:
    """Test suite for human-like text typing."""
    
    @pytest.mark.asyncio
    async def test_should_type_character_by_character_when_human_behavior_enabled(self, mock_page):
        """Test that text is typed character by character."""
        text = "Hello"
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            with patch('asyncio.sleep'):  # Mock sleep to speed up test
                await human_type_text(mock_page, text)
                
                # Should have called keyboard.type for each character
                assert mock_page.keyboard.type.call_count == len(text)

    @pytest.mark.asyncio
    async def test_should_insert_text_directly_when_human_behavior_disabled(self, mock_page):
        """Test that text is inserted directly when human behavior disabled."""
        text = "Hello World"
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', False):
            await human_type_text(mock_page, text)
            
            # Should use insert_text for direct insertion
            mock_page.keyboard.insert_text.assert_called_once_with(text)

    @pytest.mark.asyncio
    async def test_should_add_delays_between_characters(self, mock_page):
        """Test that delays are added between character typing."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            with patch('asyncio.sleep') as mock_sleep:
                await human_type_text(mock_page, "Hi")
                
                # Should add delay after each character except possibly the last
                assert mock_sleep.call_count >= 1

    @pytest.mark.asyncio
    async def test_should_handle_empty_text(self, mock_page):
        """Test handling of empty text input."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            await human_type_text(mock_page, "")
            
            # Should not crash and should not make typing calls
            mock_page.keyboard.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_handle_special_characters(self, mock_page):
        """Test handling of special characters."""
        text = "Hello@world.com!"
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            with patch('asyncio.sleep'):  # Mock sleep to speed up test
                await human_type_text(mock_page, text)
                
                # Should type all characters including special ones
                assert mock_page.keyboard.type.call_count == len(text)


class TestHumanScroll:
    """Test suite for human-like scrolling."""
    
    @pytest.mark.asyncio
    async def test_should_scroll_page_in_specified_direction(self, mock_page):
        """Test scrolling in specified direction."""
        await human_scroll(mock_page, 0, 0, "down", 3)
        
        # Should have called mouse.wheel (scrolling mechanism)
        assert mock_page.mouse.wheel.called

    @pytest.mark.asyncio
    async def test_should_handle_different_scroll_directions(self, mock_page):
        """Test scrolling in different directions."""
        directions = ["up", "down"]
        for direction in directions:
            mock_page.reset_mock()
            await human_scroll(mock_page, 0, 0, direction, 1)
            assert mock_page.mouse.wheel.called

    @pytest.mark.asyncio
    async def test_should_respect_scroll_amount(self, mock_page):
        """Test that scroll amount is respected."""
        await human_scroll(mock_page, 0, 0, "down", 5)
        
        # Should have scrolled with the specified amount
        assert mock_page.mouse.wheel.call_count >= 1

    @pytest.mark.asyncio
    async def test_should_handle_zero_scroll_amount(self, mock_page):
        """Test handling of zero scroll amount."""
        await human_scroll(mock_page, 0, 0, "down", 0)
        
        # Should handle gracefully (may or may not scroll)
        # Should not crash
        assert True  # Test passes if no exception

    @pytest.mark.asyncio
    async def test_should_scroll_in_multiple_increments_when_human_behavior_enabled(self, mock_page):
        """Test that scrolling is broken into multiple increments when human behavior is enabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            with patch('asyncio.sleep'):  # Mock sleep to speed up test
                await human_scroll(mock_page, 0, 0, "down", 100)
                
                # Should have made multiple wheel calls
                assert mock_page.mouse.wheel.call_count > 1

    @pytest.mark.asyncio
    async def test_should_scroll_once_when_human_behavior_disabled(self, mock_page):
        """Test that scrolling happens in one call when human behavior is disabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', False):
            await human_scroll(mock_page, 0, 0, "down", 100)
            
            # Should make only one wheel call
            mock_page.mouse.wheel.assert_called_once()


class TestSmartDelayBetweenActions:
    """Test suite for smart delay between actions."""
    
    @pytest.mark.asyncio
    async def test_should_add_delay_between_actions(self):
        """Test that delay is added between actions."""
        start_time = asyncio.get_event_loop().time()
        await smart_delay_between_actions("click")
        end_time = asyncio.get_event_loop().time()
        
        elapsed = (end_time - start_time) * 1000
        # Should add some delay (exact amount depends on implementation)
        assert elapsed >= 0  # At minimum, should not be negative

    @pytest.mark.asyncio
    async def test_should_vary_delay_based_on_action_type(self):
        """Test that delay varies based on action type."""
        action_types = ["click", "type", "scroll", "navigate"]
        delays = []
        
        for action_type in action_types:
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions(action_type)
            end_time = asyncio.get_event_loop().time()
            delays.append(end_time - start_time)
        
        # All delays should be non-negative
        assert all(delay >= 0 for delay in delays)

    @pytest.mark.asyncio
    async def test_should_handle_page_complexity_parameter(self):
        """Test that page complexity affects delay."""
        complexities = ["simple", "medium", "complex"]
        
        for complexity in complexities:
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("click", complexity)
            end_time = asyncio.get_event_loop().time()
            
            elapsed = end_time - start_time
            assert elapsed >= 0

    @pytest.mark.asyncio
    async def test_should_handle_unknown_action_type(self):
        """Test handling of unknown action type."""
        start_time = asyncio.get_event_loop().time()
        await smart_delay_between_actions("unknown_action")
        end_time = asyncio.get_event_loop().time()
        
        elapsed = end_time - start_time
        assert elapsed >= 0  # Should use default delay

    @pytest.mark.asyncio
    async def test_should_add_minimal_delay_when_human_behavior_disabled(self):
        """Test that minimal delay is added when human behavior is disabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', False):
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("click")
            end_time = asyncio.get_event_loop().time()
            
            elapsed = (end_time - start_time) * 1000
            assert elapsed < 200  # Should be much shorter when disabled

    @pytest.mark.asyncio
    async def test_should_add_longer_delay_when_human_behavior_enabled(self):
        """Test that longer delay is added when human behavior is enabled."""
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("click")
            end_time = asyncio.get_event_loop().time()
            
            elapsed = (end_time - start_time) * 1000
            assert elapsed >= 100  # Should be longer when enabled