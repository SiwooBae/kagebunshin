"""
Performance optimization module for KageBunshin web automation.

This module provides intelligent strategies to improve automation speed
without compromising reliability through confidence scoring, caching,
and adaptive behavior.
"""

import time
import hashlib
import logging
from typing import Dict, Optional, Tuple, List, Any
from urllib.parse import urlparse
from dataclasses import dataclass, field
from collections import defaultdict, deque

from ..core.state import BBox

logger = logging.getLogger(__name__)


@dataclass
class InteractionRecord:
    """Record of a single element interaction attempt."""
    timestamp: float
    element_selector: str
    action_type: str  # 'click', 'type', 'select'
    native_success: bool
    fallback_needed: bool
    response_time: float
    domain: str


@dataclass
class SiteProfile:
    """Performance profile for a specific domain."""
    domain: str
    total_interactions: int = 0
    native_success_rate: float = 0.0
    avg_response_time: float = 0.0
    requires_human_behavior: bool = True
    last_updated: float = field(default_factory=time.time)
    confidence_score: float = 0.5  # 0=always fallback, 1=always native


class PerformanceOptimizer:
    """
    Intelligent performance optimizer that learns from interaction patterns
    to make speed vs reliability trade-offs.
    """

    def __init__(self, speed_mode: str = "balanced"):
        """
        Initialize the performance optimizer.
        
        Args:
            speed_mode: One of "stealth", "balanced", "fast"
        """
        self.speed_mode = speed_mode
        self.site_profiles: Dict[str, SiteProfile] = {}
        self.element_cache: Dict[str, Dict[str, Any]] = {}
        self.interaction_history: deque = deque(maxlen=1000)
        self.cache_ttl = 300  # 5 minutes
        
        # Speed mode configurations
        self.mode_configs = {
            "stealth": {
                "confidence_threshold": 0.9,  # Very conservative
                "cache_enabled": False,
                "parallel_verification": False,
                "min_interactions_for_learning": 20,
                "fallback_preference": 0.8  # Prefer fallback
            },
            "balanced": {
                "confidence_threshold": 0.7,  # Moderate
                "cache_enabled": True,
                "parallel_verification": True,
                "min_interactions_for_learning": 10,
                "fallback_preference": 0.5  # Neutral
            },
            "fast": {
                "confidence_threshold": 0.4,  # Aggressive
                "cache_enabled": True,
                "parallel_verification": True,
                "min_interactions_for_learning": 5,
                "fallback_preference": 0.2  # Prefer native
            }
        }
        
        self.config = self.mode_configs.get(speed_mode, self.mode_configs["balanced"])

    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            netloc = urlparse(url).netloc.lower()
            return netloc if netloc else "unknown"
        except Exception:
            return "unknown"

    def should_skip_native_attempt(self, url: str, element_selector: str, action_type: str) -> bool:
        """
        Determine if we should skip the native attempt and go straight to fallback.
        
        Args:
            url: Current page URL
            element_selector: CSS selector for the element
            action_type: Type of action (click, type, select)
            
        Returns:
            True if we should skip native and use fallback directly
        """
        if self.speed_mode == "stealth":
            return False  # Always try both in stealth mode
            
        domain = self.get_domain(url)
        profile = self.site_profiles.get(domain)
        
        if not profile:
            # No data yet, use conservative approach
            return self.config["fallback_preference"] > 0.6
            
        # Check if we have enough data to make decisions
        if profile.total_interactions < self.config["min_interactions_for_learning"]:
            return self.config["fallback_preference"] > 0.6
            
        # Use confidence score to decide
        confidence_threshold = self.config["confidence_threshold"]
        
        # If site generally fails native attempts, skip to fallback
        if profile.native_success_rate < (1 - confidence_threshold):
            logger.debug(f"Skipping native attempt for {domain} (success rate: {profile.native_success_rate:.2f})")
            return True
            
        return False

    def should_use_human_delays(self, url: str) -> bool:
        """
        Determine if we should use human-like delays for this site.
        
        Args:
            url: Current page URL
            
        Returns:
            True if human delays should be used
        """
        if self.speed_mode == "stealth":
            return True  # Always use human delays in stealth mode
            
        domain = self.get_domain(url)
        profile = self.site_profiles.get(domain)
        
        if not profile:
            return True  # Default to human delays for unknown sites
            
        return profile.requires_human_behavior

    def record_interaction(self, url: str, element_selector: str, action_type: str, 
                          native_success: bool, fallback_needed: bool, response_time: float):
        """
        Record the outcome of an interaction for learning.
        
        Args:
            url: Current page URL
            element_selector: CSS selector for the element
            action_type: Type of action performed
            native_success: Whether native attempt succeeded
            fallback_needed: Whether fallback was needed
            response_time: Time taken for the interaction
        """
        domain = self.get_domain(url)
        
        # Create interaction record
        record = InteractionRecord(
            timestamp=time.time(),
            element_selector=element_selector,
            action_type=action_type,
            native_success=native_success,
            fallback_needed=fallback_needed,
            response_time=response_time,
            domain=domain
        )
        
        self.interaction_history.append(record)
        
        # Update site profile
        if domain not in self.site_profiles:
            self.site_profiles[domain] = SiteProfile(domain=domain)
            
        profile = self.site_profiles[domain]
        profile.total_interactions += 1
        profile.last_updated = time.time()
        
        # Update success rate (exponential moving average)
        alpha = 0.1  # Learning rate
        if profile.total_interactions == 1:
            profile.native_success_rate = 1.0 if native_success else 0.0
        else:
            new_success_rate = 1.0 if native_success else 0.0
            profile.native_success_rate = (1 - alpha) * profile.native_success_rate + alpha * new_success_rate
            
        # Update average response time
        if profile.total_interactions == 1:
            profile.avg_response_time = response_time
        else:
            profile.avg_response_time = (1 - alpha) * profile.avg_response_time + alpha * response_time
            
        # Update confidence score based on recent performance
        recent_records = [r for r in self.interaction_history 
                         if r.domain == domain and time.time() - r.timestamp < 300]  # Last 5 minutes
        
        if len(recent_records) >= 3:
            recent_success_rate = sum(1 for r in recent_records if r.native_success) / len(recent_records)
            profile.confidence_score = recent_success_rate
            
        # Determine if site requires human behavior (if native success rate is low)
        profile.requires_human_behavior = profile.native_success_rate < 0.8
        
        logger.debug(f"Updated profile for {domain}: success_rate={profile.native_success_rate:.2f}, "
                    f"confidence={profile.confidence_score:.2f}, requires_human={profile.requires_human_behavior}")

    def get_cached_element_info(self, element_selector: str) -> Optional[Dict[str, Any]]:
        """
        Get cached information about an element.
        
        Args:
            element_selector: CSS selector for the element
            
        Returns:
            Cached element info or None if not found/expired
        """
        if not self.config["cache_enabled"]:
            return None
            
        cache_key = hashlib.md5(element_selector.encode()).hexdigest()
        
        if cache_key in self.element_cache:
            cached_info = self.element_cache[cache_key]
            if time.time() - cached_info["timestamp"] < self.cache_ttl:
                return cached_info["data"]
            else:
                # Expired, remove from cache
                del self.element_cache[cache_key]
                
        return None

    def cache_element_info(self, element_selector: str, element_info: Dict[str, Any]):
        """
        Cache information about an element.
        
        Args:
            element_selector: CSS selector for the element
            element_info: Information to cache
        """
        if not self.config["cache_enabled"]:
            return
            
        cache_key = hashlib.md5(element_selector.encode()).hexdigest()
        self.element_cache[cache_key] = {
            "timestamp": time.time(),
            "data": element_info
        }

    def get_optimal_delay_profile(self, url: str, action_type: str) -> str:
        """
        Get the optimal delay profile for the given context.
        
        Args:
            url: Current page URL
            action_type: Type of action being performed
            
        Returns:
            Delay profile name ("minimal", "fast", "normal", "human")
        """
        if self.speed_mode == "stealth":
            return "human"
            
        domain = self.get_domain(url)
        profile = self.site_profiles.get(domain)
        
        if not profile or profile.requires_human_behavior:
            if self.speed_mode == "fast":
                return "fast"
            return "normal"
            
        # For sites that work well with native interactions
        if self.speed_mode == "fast":
            return "fast"  # Changed from "minimal" to "fast"
        elif self.speed_mode == "balanced":
            return "fast"
        else:
            return "normal"

    def should_use_parallel_verification(self, url: str) -> bool:
        """
        Determine if parallel state verification should be used.
        
        Args:
            url: Current page URL
            
        Returns:
            True if parallel verification should be used
        """
        return self.config["parallel_verification"]

    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get current performance statistics.
        
        Returns:
            Dictionary with performance metrics
        """
        total_interactions = len(self.interaction_history)
        if total_interactions == 0:
            return {"total_interactions": 0}
            
        native_successes = sum(1 for r in self.interaction_history if r.native_success)
        fallbacks_needed = sum(1 for r in self.interaction_history if r.fallback_needed)
        avg_response_time = sum(r.response_time for r in self.interaction_history) / total_interactions
        
        site_stats = {}
        for domain, profile in self.site_profiles.items():
            site_stats[domain] = {
                "total_interactions": profile.total_interactions,
                "native_success_rate": profile.native_success_rate,
                "avg_response_time": profile.avg_response_time,
                "requires_human_behavior": profile.requires_human_behavior,
                "confidence_score": profile.confidence_score
            }
            
        return {
            "total_interactions": total_interactions,
            "overall_native_success_rate": native_successes / total_interactions,
            "fallback_usage_rate": fallbacks_needed / total_interactions,
            "avg_response_time": avg_response_time,
            "cached_elements": len(self.element_cache),
            "tracked_sites": len(self.site_profiles),
            "site_profiles": site_stats,
            "speed_mode": self.speed_mode
        }

    def clear_cache(self):
        """Clear all cached data."""
        self.element_cache.clear()
        logger.info("Element cache cleared")

    def reset_learning(self):
        """Reset all learning data."""
        self.site_profiles.clear()
        self.interaction_history.clear()
        logger.info("Learning data reset")