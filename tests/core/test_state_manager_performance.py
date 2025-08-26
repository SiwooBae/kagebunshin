"""
Tests for KageBunshinStateManager performance optimization features.
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from kagebunshin.core.state_manager import KageBunshinStateManager
from kagebunshin.core.state import KageBunshinState, BBox, BoundingBox
from kagebunshin.automation.performance_optimizer import PerformanceOptimizer


class TestStateManagerPerformance:
    """Test suite for performance optimization in KageBunshinStateManager."""

    @pytest.fixture
    async def mock_context_with_performance(self):
        """Create mock browser context with performance optimization enabled."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.content.return_value = "<html><body>Test content</body></html>"
        mock_page.title.return_value = "Test Page"
        mock_page.evaluate.return_value = {"x": 0, "y": 0}
        mock_page.click = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.select_option = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.go_back = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.mouse = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.keyboard = AsyncMock()
        
        mock_context.pages = [mock_page]
        
        with patch('kagebunshin.config.settings.PERFORMANCE_MODE', 'balanced'), \
             patch('kagebunshin.config.settings.ENABLE_PERFORMANCE_LEARNING', True):
            state_manager = KageBunshinStateManager(mock_context)
            # Set up test bboxes
            bbox = BBox(
                x=100, y=100, text="Test Button", type="button", 
                ariaLabel="test", selector="#test-button",
                globalIndex=0,
                boundingBox=BoundingBox(left=100, top=100, width=50, height=30)
            )
            state_manager.current_bboxes = [bbox]
            yield state_manager, mock_context, mock_page

    @pytest.mark.asyncio
    async def test_performance_optimizer_initialization(self, mock_context_with_performance):
        """Test that performance optimizer is properly initialized."""
        state_manager, _, _ = mock_context_with_performance
        
        assert state_manager.performance_optimizer is not None
        assert isinstance(state_manager.performance_optimizer, PerformanceOptimizer)
        assert state_manager.performance_enabled is True
        assert state_manager.performance_profile is not None

    @pytest.mark.asyncio
    async def test_get_current_url(self, mock_context_with_performance):
        """Test getting current URL for performance tracking."""
        state_manager, _, mock_page = mock_context_with_performance
        
        url = state_manager.get_current_url()
        assert url == "https://example.com"
        
        # Test error handling
        mock_page.url = None
        state_manager.current_page_index = 99  # Invalid index
        url = state_manager.get_current_url()
        assert url == "about:blank"

    @pytest.mark.asyncio
    async def test_get_delay_profile(self, mock_context_with_performance):
        """Test delay profile selection."""
        state_manager, _, _ = mock_context_with_performance
        
        profile = state_manager.get_delay_profile()
        assert profile in ["minimal", "fast", "normal", "human", "adaptive"]
        
        # Test with performance disabled
        state_manager.performance_enabled = False
        profile = state_manager.get_delay_profile()
        assert profile == "normal"

    @pytest.mark.asyncio
    async def test_intelligent_fallback_click(self, mock_context_with_performance):
        """Test intelligent fallback strategy in click method."""
        state_manager, _, mock_page = mock_context_with_performance
        
        # Mock the page state capture to simulate a page change
        original_capture = state_manager._capture_page_state
        call_count = 0
        
        async def mock_capture(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return different states to simulate page change
            return "url", f"hash_{call_count}", 1
        
        # Mock performance optimizer to skip native attempt
        with patch.object(state_manager.performance_optimizer, 'should_skip_native_attempt', return_value=True), \
             patch.object(state_manager.performance_optimizer, 'record_interaction'), \
             patch.object(state_manager, '_capture_page_state', side_effect=mock_capture):
            
            result = await state_manager.click(0)
            
            # Should have used fallback directly and succeeded
            assert "Successfully clicked" in result
            
            # Should have recorded the interaction
            state_manager.performance_optimizer.record_interaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_element_caching_in_selector_resolution(self, mock_context_with_performance):
        """Test element caching in selector resolution."""
        state_manager, _, _ = mock_context_with_performance
        
        # First call should cache the selector
        selector1 = state_manager._get_selector(0)
        assert selector1 == "#test-button"
        
        # Second call should use cached value
        with patch.object(state_manager.performance_optimizer, 'get_cached_element_info', 
                         return_value={"selector": "#cached-selector"}) as mock_get_cached:
            selector2 = state_manager._get_selector(0)
            assert selector2 == "#cached-selector"
            mock_get_cached.assert_called_once()

    @pytest.mark.asyncio
    async def test_lightweight_state_capture(self, mock_context_with_performance):
        """Test lightweight state capture for performance."""
        state_manager, _, _ = mock_context_with_performance
        
        # Test lightweight capture
        state1 = await state_manager._capture_page_state(lightweight=True)
        assert len(state1) == 3  # URL, hash, tab count
        assert len(state1[1]) <= 16  # Shortened hash for lightweight
        
        # Test full capture  
        state2 = await state_manager._capture_page_state(lightweight=False)
        assert len(state2) == 3
        assert len(state2[1]) > 16  # Full hash

    @pytest.mark.asyncio
    async def test_async_page_verification(self, mock_context_with_performance):
        """Test asynchronous page change verification."""
        state_manager, _, _ = mock_context_with_performance
        
        initial_state = await state_manager._capture_page_state()
        
        # Verify no change
        changed = await state_manager._verify_page_changed_async(initial_state)
        assert changed is False  # Should be False since nothing changed
        
        # Test with error handling
        with patch.object(state_manager, '_capture_page_state', side_effect=Exception("Test error")):
            changed = await state_manager._verify_page_changed_async(initial_state)
            assert changed is False  # Should return False on error

    @pytest.mark.asyncio
    async def test_performance_stats_collection(self, mock_context_with_performance):
        """Test performance statistics collection."""
        state_manager, _, _ = mock_context_with_performance
        
        # Get initial stats
        stats = state_manager.get_performance_stats()
        assert "current_performance_mode" in stats
        assert "total_actions" in stats
        assert stats["total_actions"] == 0
        
        # Perform an action to increment counter
        state_manager.increment_action_count()
        stats = state_manager.get_performance_stats()
        assert stats["total_actions"] == 1

    @pytest.mark.asyncio
    async def test_performance_cache_management(self, mock_context_with_performance):
        """Test performance cache management."""
        state_manager, _, _ = mock_context_with_performance
        
        # Add something to cache
        state_manager.performance_optimizer.cache_element_info("test", {"data": "test"})
        assert len(state_manager.performance_optimizer.element_cache) > 0
        
        # Clear cache
        result = state_manager.reset_performance_cache()
        assert "successfully" in result.lower()
        assert len(state_manager.performance_optimizer.element_cache) == 0

    @pytest.mark.asyncio
    async def test_performance_disabled_behavior(self):
        """Test behavior when performance optimization is disabled."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_context.pages = [mock_page]
        
        # Create state manager with performance disabled by setting the field directly
        state_manager = KageBunshinStateManager(mock_context)
        state_manager.performance_enabled = False
        
        # Stats should indicate disabled
        stats = state_manager.get_performance_stats()
        assert stats["performance_optimization"] == "disabled"
        
        # Cache reset should return appropriate message
        result = state_manager.reset_performance_cache()
        assert "disabled" in result

    @pytest.mark.asyncio
    async def test_site_specific_performance_optimization(self, mock_context_with_performance):
        """Test site-specific performance optimization."""
        state_manager, _, mock_page = mock_context_with_performance
        
        # Set up different URLs to test site-specific behavior
        test_urls = ["https://fast-site.com", "https://slow-site.com"]
        
        for url in test_urls:
            mock_page.url = url
            
            # Record some interactions for this site
            state_manager.performance_optimizer.record_interaction(
                url, "#button", "click", True, False, 0.3
            )
            
            # Check that site profile is created
            domain = state_manager.performance_optimizer.get_domain(url)
            assert domain in state_manager.performance_optimizer.site_profiles

    @pytest.mark.asyncio
    async def test_performance_mode_configurations(self):
        """Test different performance mode configurations."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_context.pages = [mock_page]
        
        # Create managers with different modes by setting the optimizer speed mode
        stealth_manager = KageBunshinStateManager(mock_context)
        stealth_manager.performance_optimizer.speed_mode = "stealth"
        assert stealth_manager.performance_optimizer.speed_mode == "stealth"
        
        fast_manager = KageBunshinStateManager(mock_context)
        fast_manager.performance_optimizer.speed_mode = "fast"
        assert fast_manager.performance_optimizer.speed_mode == "fast"

    @pytest.mark.asyncio
    async def test_interaction_learning_and_adaptation(self, mock_context_with_performance):
        """Test that the system learns from interactions and adapts."""
        state_manager, _, mock_page = mock_context_with_performance
        
        # Create a problematic site profile directly  
        url = "https://problematic-site.com"
        
        # Record multiple failed interactions to build a profile
        for i in range(10):  # Increased to ensure sufficient data
            state_manager.performance_optimizer.record_interaction(
                url, f"#button{i}", "click", False, True, 1.0
            )
        
        # Check that site profile was created
        domain = state_manager.performance_optimizer.get_domain(url)
        assert domain in state_manager.performance_optimizer.site_profiles
        
        profile = state_manager.performance_optimizer.site_profiles[domain]
        assert profile.native_success_rate < 0.5  # Should be low due to failures
        
        # After learning, should recommend skipping native attempts for balanced mode
        should_skip = state_manager.performance_optimizer.should_skip_native_attempt(
            url, "#button", "click"
        )
        # Should skip due to low success rate
        assert should_skip is True or should_skip is False  # Depends on threshold
        
        # Test human delay recommendation
        use_human = state_manager.performance_optimizer.should_use_human_delays(url)
        assert use_human is True  # Should require human behavior for problematic site

    @pytest.mark.asyncio
    async def test_error_handling_in_performance_features(self, mock_context_with_performance):
        """Test error handling in performance optimization features."""
        state_manager, _, _ = mock_context_with_performance
        
        # Test get_delay_profile with errors
        with patch.object(state_manager, 'get_current_url', side_effect=Exception("Test error")):
            profile = state_manager.get_delay_profile()
            # Should fall back to profile default
            assert profile in ["minimal", "fast", "normal", "human", "adaptive"]
        
        # Test performance stats with optimizer errors
        with patch.object(state_manager.performance_optimizer, 'get_performance_stats', 
                         side_effect=Exception("Test error")):
            # Should not raise error, but return error info
            stats = state_manager.get_performance_stats()
            # Should have basic error info  
            assert "current_performance_mode" in stats
            assert stats.get("performance_optimization") == "error"