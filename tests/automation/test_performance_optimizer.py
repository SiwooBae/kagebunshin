"""
Tests for the PerformanceOptimizer module.
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from kagebunshin.automation.performance_optimizer import (
    PerformanceOptimizer, 
    InteractionRecord, 
    SiteProfile
)


class TestPerformanceOptimizer:
    """Test suite for PerformanceOptimizer class."""

    def test_initialization(self):
        """Test PerformanceOptimizer initialization with different modes."""
        # Test default mode
        optimizer = PerformanceOptimizer()
        assert optimizer.speed_mode == "balanced"
        
        # Test stealth mode
        stealth_optimizer = PerformanceOptimizer("stealth")
        assert stealth_optimizer.speed_mode == "stealth"
        assert stealth_optimizer.config["confidence_threshold"] == 0.9
        
        # Test fast mode
        fast_optimizer = PerformanceOptimizer("fast")
        assert fast_optimizer.speed_mode == "fast"
        assert fast_optimizer.config["confidence_threshold"] == 0.4

    def test_get_domain(self):
        """Test domain extraction from URLs."""
        optimizer = PerformanceOptimizer()
        
        assert optimizer.get_domain("https://example.com/path") == "example.com"
        assert optimizer.get_domain("http://subdomain.example.com") == "subdomain.example.com"
        assert optimizer.get_domain("https://www.google.com/search?q=test") == "www.google.com"
        assert optimizer.get_domain("invalid-url") == "unknown"

    def test_should_skip_native_attempt_no_data(self):
        """Test skip native decision with no historical data."""
        optimizer = PerformanceOptimizer("balanced")
        
        # With no data, should use fallback preference
        should_skip = optimizer.should_skip_native_attempt(
            "https://example.com", "#button", "click"
        )
        # Should not skip for balanced mode with no data
        assert not should_skip
        
        # Test with fast mode
        fast_optimizer = PerformanceOptimizer("fast")
        should_skip = fast_optimizer.should_skip_native_attempt(
            "https://example.com", "#button", "click"
        )
        # Fast mode might skip based on fallback preference
        assert isinstance(should_skip, bool)

    def test_should_skip_native_attempt_with_data(self):
        """Test skip native decision with historical data."""
        optimizer = PerformanceOptimizer("balanced")
        
        # Create a site profile with low success rate
        profile = SiteProfile(
            domain="example.com",
            total_interactions=10,
            native_success_rate=0.2,  # Low success rate
            confidence_score=0.2
        )
        optimizer.site_profiles["example.com"] = profile
        
        should_skip = optimizer.should_skip_native_attempt(
            "https://example.com", "#button", "click"
        )
        # Should skip native attempt due to low success rate
        assert should_skip

    def test_record_interaction(self):
        """Test recording interaction outcomes."""
        optimizer = PerformanceOptimizer("balanced")
        
        # Record first interaction
        optimizer.record_interaction(
            "https://example.com", "#button", "click", 
            native_success=True, fallback_needed=False, response_time=0.5
        )
        
        assert "example.com" in optimizer.site_profiles
        profile = optimizer.site_profiles["example.com"]
        assert profile.total_interactions == 1
        assert profile.native_success_rate == 1.0
        
        # Record second interaction (failure)
        optimizer.record_interaction(
            "https://example.com", "#button", "click",
            native_success=False, fallback_needed=True, response_time=1.0
        )
        
        assert profile.total_interactions == 2
        # Success rate should be updated (exponential moving average)
        assert 0.8 < profile.native_success_rate < 1.0

    def test_should_use_human_delays(self):
        """Test human delay decision logic."""
        optimizer = PerformanceOptimizer("stealth")
        
        # Stealth mode should always use human delays
        assert optimizer.should_use_human_delays("https://example.com") is True
        
        # Test with balanced mode and no profile
        balanced_optimizer = PerformanceOptimizer("balanced")
        assert balanced_optimizer.should_use_human_delays("https://example.com") is True
        
        # Test with site profile that doesn't require human behavior
        profile = SiteProfile(domain="example.com")
        profile.requires_human_behavior = False
        balanced_optimizer.site_profiles["example.com"] = profile
        
        assert balanced_optimizer.should_use_human_delays("https://example.com") is False

    def test_element_caching(self):
        """Test element information caching."""
        optimizer = PerformanceOptimizer("balanced")
        
        # Cache element info
        element_info = {
            "selector": "#button",
            "type": "button",
            "text": "Click me"
        }
        optimizer.cache_element_info("#button", element_info)
        
        # Retrieve cached info
        cached = optimizer.get_cached_element_info("#button")
        assert cached is not None
        assert cached["selector"] == "#button"
        assert cached["type"] == "button"
        
        # Test cache expiry
        with patch('time.time', return_value=time.time() + 400):  # Expire cache
            cached_expired = optimizer.get_cached_element_info("#button")
            assert cached_expired is None

    def test_get_optimal_delay_profile(self):
        """Test delay profile selection."""
        optimizer = PerformanceOptimizer("fast")
        
        # With no profile, should return fast for fast mode
        profile = optimizer.get_optimal_delay_profile("https://example.com", "click")
        assert profile == "fast"
        
        # Test with site that requires human behavior
        site_profile = SiteProfile(domain="example.com")
        site_profile.requires_human_behavior = True
        optimizer.site_profiles["example.com"] = site_profile
        
        profile = optimizer.get_optimal_delay_profile("https://example.com", "click")
        assert profile == "fast"  # Fast mode with human behavior required

    def test_performance_stats(self):
        """Test performance statistics generation."""
        optimizer = PerformanceOptimizer("balanced")
        
        # Initially empty stats
        stats = optimizer.get_performance_stats()
        assert stats["total_interactions"] == 0
        
        # Record some interactions
        optimizer.record_interaction(
            "https://example.com", "#button1", "click",
            native_success=True, fallback_needed=False, response_time=0.3
        )
        optimizer.record_interaction(
            "https://test.com", "#button2", "type",
            native_success=False, fallback_needed=True, response_time=0.8
        )
        
        stats = optimizer.get_performance_stats()
        assert stats["total_interactions"] == 2
        assert stats["overall_native_success_rate"] == 0.5
        assert stats["fallback_usage_rate"] == 0.5
        assert "example.com" in stats["site_profiles"]
        assert "test.com" in stats["site_profiles"]

    def test_stealth_mode_behavior(self):
        """Test that stealth mode disables optimization features."""
        stealth_optimizer = PerformanceOptimizer("stealth")
        
        # Should never skip native attempts
        should_skip = stealth_optimizer.should_skip_native_attempt(
            "https://example.com", "#button", "click"
        )
        assert should_skip is False
        
        # Should always use human delays
        assert stealth_optimizer.should_use_human_delays("https://example.com") is True
        
        # Caching should be disabled
        assert not stealth_optimizer.config["cache_enabled"]

    def test_clear_cache_and_reset(self):
        """Test cache clearing and learning data reset."""
        optimizer = PerformanceOptimizer("balanced")
        
        # Add some data
        optimizer.cache_element_info("#button", {"selector": "#button"})
        optimizer.record_interaction(
            "https://example.com", "#button", "click",
            native_success=True, fallback_needed=False, response_time=0.5
        )
        
        assert len(optimizer.element_cache) > 0
        assert len(optimizer.site_profiles) > 0
        assert len(optimizer.interaction_history) > 0
        
        # Clear cache
        optimizer.clear_cache()
        assert len(optimizer.element_cache) == 0
        
        # Reset learning
        optimizer.reset_learning()
        assert len(optimizer.site_profiles) == 0
        assert len(optimizer.interaction_history) == 0

    def test_confidence_scoring(self):
        """Test confidence score calculation."""
        optimizer = PerformanceOptimizer("balanced")
        
        # Record multiple successful interactions
        for i in range(5):
            optimizer.record_interaction(
                "https://reliable-site.com", f"#button{i}", "click",
                native_success=True, fallback_needed=False, response_time=0.3
            )
        
        profile = optimizer.site_profiles["reliable-site.com"]
        assert profile.confidence_score >= 0.8
        
        # Record multiple failed interactions for another site
        for i in range(5):
            optimizer.record_interaction(
                "https://problematic-site.com", f"#button{i}", "click", 
                native_success=False, fallback_needed=True, response_time=1.0
            )
        
        problematic_profile = optimizer.site_profiles["problematic-site.com"]
        assert problematic_profile.confidence_score <= 0.2


class TestInteractionRecord:
    """Test suite for InteractionRecord dataclass."""

    def test_interaction_record_creation(self):
        """Test creating InteractionRecord instances."""
        record = InteractionRecord(
            timestamp=time.time(),
            element_selector="#button",
            action_type="click",
            native_success=True,
            fallback_needed=False,
            response_time=0.5,
            domain="example.com"
        )
        
        assert record.element_selector == "#button"
        assert record.action_type == "click"
        assert record.native_success is True
        assert record.domain == "example.com"


class TestSiteProfile:
    """Test suite for SiteProfile dataclass."""

    def test_site_profile_creation(self):
        """Test creating SiteProfile instances."""
        profile = SiteProfile(domain="example.com")
        
        assert profile.domain == "example.com"
        assert profile.total_interactions == 0
        assert profile.native_success_rate == 0.0
        assert profile.requires_human_behavior is True
        assert 0.0 <= profile.confidence_score <= 1.0

    def test_site_profile_with_custom_values(self):
        """Test SiteProfile with custom initialization values."""
        profile = SiteProfile(
            domain="test.com",
            total_interactions=10,
            native_success_rate=0.8,
            requires_human_behavior=False,
            confidence_score=0.9
        )
        
        assert profile.domain == "test.com"
        assert profile.total_interactions == 10
        assert profile.native_success_rate == 0.8
        assert profile.requires_human_behavior is False
        assert profile.confidence_score == 0.9