"""
Benchmark configuration for KageBunshin performance evaluation.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum


class PerformanceMode(Enum):
    """Performance modes available for benchmarking."""
    STEALTH = "stealth"      # Maximum reliability, minimal optimization
    BALANCED = "balanced"    # Default balanced mode
    FAST = "fast"           # Maximum speed optimization


@dataclass
class BenchmarkScenario:
    """Configuration for a single benchmark scenario."""
    name: str
    description: str
    task: str
    target_url: Optional[str] = None
    expected_operations: List[str] = None
    timeout: int = 300  # 5 minutes default timeout
    
    def __post_init__(self):
        if self.expected_operations is None:
            self.expected_operations = []


@dataclass 
class BenchmarkConfig:
    """Configuration for running performance benchmarks."""
    
    # Benchmark execution settings
    runs_per_scenario: int = 3
    timeout_per_run: int = 300  # 5 minutes
    
    # Agent configuration 
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 1280
    
    # Performance modes to test
    performance_modes: List[PerformanceMode] = None
    
    # Scenarios to run
    scenarios: List[BenchmarkScenario] = None
    
    # Environment cleanup
    clean_browser_data: bool = True
    
    def __post_init__(self):
        if self.performance_modes is None:
            self.performance_modes = [
                PerformanceMode.STEALTH,
                PerformanceMode.BALANCED, 
                PerformanceMode.FAST
            ]
        
        if self.scenarios is None:
            self.scenarios = self._get_default_scenarios()
    
    def _get_default_scenarios(self) -> List[BenchmarkScenario]:
        """Get default benchmark scenarios."""
        return [
            BenchmarkScenario(
                name="simple_form_fill",
                description="Fill out a simple form with basic fields",
                task="Go to httpbin.org/forms/post, fill out the form with test data, and submit it",
                target_url="https://httpbin.org/forms/post",
                expected_operations=["browser_goto", "type_text", "type_text", "type_text", "click"],
                timeout=120
            ),
            BenchmarkScenario(
                name="navigation_heavy",
                description="Navigate through multiple pages and links",
                task="Go to example.com, then navigate to the IANA website link, explore the documentation section, and return back",
                target_url="https://example.com",
                expected_operations=["browser_goto", "click", "click", "go_back", "go_back"],
                timeout=180
            ),
            BenchmarkScenario(
                name="search_and_extract",
                description="Perform a search and extract information from results",
                task="Go to DuckDuckGo, search for 'web automation testing', and extract information from the first 3 results",
                target_url="https://duckduckgo.com", 
                expected_operations=["browser_goto", "type_text", "click", "extract_page_content", "click", "extract_page_content"],
                timeout=240
            ),
            BenchmarkScenario(
                name="complex_interaction",
                description="Complex page interaction with multiple steps",
                task="Go to httpbin.org, explore the HTTP Methods section, test GET and POST endpoints, and extract the response data",
                target_url="https://httpbin.org",
                expected_operations=["browser_goto", "click", "click", "extract_page_content", "click", "extract_page_content"],
                timeout=300
            )
        ]
    
    def get_environment_for_mode(self, mode: PerformanceMode) -> Dict[str, str]:
        """Get environment variables for a specific performance mode."""
        env_vars = {
            "KAGE_PERFORMANCE_MODE": mode.value,
            "KAGE_ENABLE_PERFORMANCE_LEARNING": "1",  # Always enable learning for benchmarks
        }
        
        # Add any mode-specific settings
        if mode == PerformanceMode.STEALTH:
            env_vars["KAGE_ENABLE_PERFORMANCE_LEARNING"] = "0"  # Disable learning in stealth mode
        
        return env_vars