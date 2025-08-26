"""
Tests for behavior.py profile-aware functions.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from kagebunshin.automation.behavior import (
    human_delay,
    human_mouse_move, 
    human_type_text,
    human_scroll,
    smart_delay_between_actions
)


class TestProfileAwareBehavior:
    """Test suite for profile-aware behavior functions."""

    @pytest.mark.asyncio
    async def test_human_delay_with_profiles(self):
        """Test human_delay with different profiles."""
        
        # Test with minimal profile
        start_time = asyncio.get_event_loop().time()
        await human_delay(100, 500, profile="minimal")
        end_time = asyncio.get_event_loop().time()
        
        # Should use shorter delays for minimal profile
        delay_time = end_time - start_time
        assert 0.05 <= delay_time <= 0.15  # Should use profile range
        
        # Test with normal profile (fallback)
        start_time = asyncio.get_event_loop().time()
        await human_delay(100, 500, profile="normal")
        end_time = asyncio.get_event_loop().time()
        
        delay_time = end_time - start_time
        assert 0.1 <= delay_time <= 1.0  # Should use profile range

    @pytest.mark.asyncio
    async def test_human_mouse_move_with_profiles(self):
        """Test human_mouse_move with different delay profiles."""
        mock_page = AsyncMock()
        mock_page.mouse.move = AsyncMock()
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test with fast profile
            await human_mouse_move(mock_page, 0, 0, 100, 100, profile="fast")
            
            # Should have called mouse.move multiple times (steps)
            assert mock_page.mouse.move.call_count >= 3
            mock_page.mouse.move.reset_mock()
            
            # Test with minimal profile (should be faster)
            await human_mouse_move(mock_page, 0, 0, 100, 100, profile="minimal")
            
            # Should still have called mouse.move multiple times
            assert mock_page.mouse.move.call_count >= 3

    @pytest.mark.asyncio
    async def test_human_type_text_with_profiles(self):
        """Test human_type_text with different profiles."""
        mock_page = AsyncMock()
        mock_page.keyboard.type = AsyncMock()
        mock_page.keyboard.insert_text = AsyncMock()
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test with minimal profile (should disable human typing)
            await human_type_text(mock_page, "test", profile="minimal")
            
            # Should use fast insert_text instead of character-by-character
            mock_page.keyboard.insert_text.assert_called_once_with("test")
            mock_page.keyboard.type.assert_not_called()
            
            # Reset mocks
            mock_page.keyboard.insert_text.reset_mock()
            mock_page.keyboard.type.reset_mock()
            
            # Test with human profile
            await human_type_text(mock_page, "test", profile="human")
            
            # Should type character by character
            assert mock_page.keyboard.type.call_count == 4  # One call per character
            mock_page.keyboard.insert_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_human_scroll_with_profiles(self):
        """Test human_scroll with different profiles."""
        mock_page = AsyncMock()
        mock_page.mouse.wheel = AsyncMock()
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test with minimal profile (should disable human scrolling)
            await human_scroll(mock_page, 0, 0, "down", 500, profile="minimal")
            
            # Should do single wheel action
            mock_page.mouse.wheel.assert_called_once_with(0, 500)
            mock_page.mouse.wheel.reset_mock()
            
            # Test with human profile (should use multiple increments)
            await human_scroll(mock_page, 0, 0, "down", 500, profile="human")
            
            # Should have called wheel multiple times
            assert mock_page.mouse.wheel.call_count >= 3

    @pytest.mark.asyncio
    async def test_smart_delay_between_actions_with_profiles(self):
        """Test smart_delay_between_actions with profiles."""
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test with minimal profile
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("click", profile="minimal")
            end_time = asyncio.get_event_loop().time()
            
            delay_time = end_time - start_time
            assert 0.02 <= delay_time <= 0.1  # Should use minimal profile range
            
            # Test with human profile
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("click", profile="human")
            end_time = asyncio.get_event_loop().time()
            
            delay_time = end_time - start_time
            assert 0.1 <= delay_time <= 0.5  # Should use human profile range

    @pytest.mark.asyncio
    async def test_adaptive_profile_behavior(self):
        """Test behavior with adaptive profile."""
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test smart delay with adaptive profile
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("type", profile="adaptive")
            end_time = asyncio.get_event_loop().time()
            
            delay_time = end_time - start_time
            # Should use base ranges for adaptive
            assert 0.02 <= delay_time <= 0.2

    @pytest.mark.asyncio
    async def test_behavior_with_disabled_human_behavior(self):
        """Test that profiles are respected when human behavior is disabled."""
        mock_page = AsyncMock()
        mock_page.keyboard.insert_text = AsyncMock()
        mock_page.mouse.move = AsyncMock()
        mock_page.mouse.wheel = AsyncMock()
        
        # Patch the module-level import
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', False):
            # All functions should use fast non-human behavior regardless of profile
            await human_type_text(mock_page, "test", profile="human")
            mock_page.keyboard.insert_text.assert_called_once_with("test")
            
            await human_mouse_move(mock_page, 0, 0, 100, 100, profile="human")
            mock_page.mouse.move.assert_called_once_with(100, 100)
            
            await human_scroll(mock_page, 0, 0, "down", 500, profile="human")
            mock_page.mouse.wheel.assert_called_once_with(0, 500)

    @pytest.mark.asyncio
    async def test_complexity_multiplier_with_profiles(self):
        """Test that complexity multipliers work with profiles."""
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test with fast profile and complex page
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("click", page_complexity="complex", profile="fast")
            end_time = asyncio.get_event_loop().time()
            
            delay_time = end_time - start_time
            # Fast profile should reduce complexity impact
            assert delay_time < 0.5  # Should be faster than normal complex delays

    @pytest.mark.asyncio
    async def test_profile_fallback_behavior(self):
        """Test behavior when profile is not recognized."""
        
        # Test with invalid profile name
        start_time = asyncio.get_event_loop().time()
        await smart_delay_between_actions("click", profile="invalid_profile")
        end_time = asyncio.get_event_loop().time()
        
        delay_time = end_time - start_time
        # Should fall back to default behavior
        assert 0.5 <= delay_time <= 2.5  # Default click range

    @pytest.mark.asyncio 
    async def test_action_type_mapping(self):
        """Test that different action types use appropriate delay ranges."""
        
        with patch('kagebunshin.automation.behavior.ACTIVATE_HUMAN_BEHAVIOR', True):
            # Test navigate action (should be longer)
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("navigate", profile="fast")
            end_time = asyncio.get_event_loop().time()
            
            navigate_delay = end_time - start_time
            
            # Test click action (should be shorter)
            start_time = asyncio.get_event_loop().time()
            await smart_delay_between_actions("click", profile="fast")
            end_time = asyncio.get_event_loop().time()
            
            click_delay = end_time - start_time
            
            # Navigate should generally take longer than click
            assert navigate_delay >= click_delay or abs(navigate_delay - click_delay) < 0.1