"""
Performance measurement utilities for KageBunshin benchmarking.
"""

import asyncio
import time
import os
import tempfile
import shutil
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from .benchmark_config import BenchmarkConfig, BenchmarkScenario, PerformanceMode


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    scenario_name: str
    performance_mode: str
    run_number: int
    
    # Timing measurements
    start_time: float
    end_time: float
    execution_time: float
    
    # Execution details
    success: bool
    result_text: Optional[str] = None
    error_message: Optional[str] = None
    
    # Performance metrics
    operations_completed: int = 0
    total_operations_expected: int = 0
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.execution_time <= 0:
            self.execution_time = self.end_time - self.start_time


@dataclass
class ScenarioSummary:
    """Summary of all runs for a single scenario."""
    scenario_name: str
    performance_mode: str
    
    # Aggregated timing
    runs: List[BenchmarkResult] = field(default_factory=list)
    average_time: float = 0.0
    median_time: float = 0.0
    min_time: float = 0.0
    max_time: float = 0.0
    std_deviation: float = 0.0
    
    # Success metrics
    success_rate: float = 0.0
    total_runs: int = 0
    successful_runs: int = 0
    
    def calculate_summary(self):
        """Calculate summary statistics from runs."""
        if not self.runs:
            return
        
        self.total_runs = len(self.runs)
        successful_times = [r.execution_time for r in self.runs if r.success]
        self.successful_runs = len(successful_times)
        self.success_rate = self.successful_runs / self.total_runs
        
        if successful_times:
            self.average_time = sum(successful_times) / len(successful_times)
            self.min_time = min(successful_times)
            self.max_time = max(successful_times)
            
            # Calculate median
            sorted_times = sorted(successful_times)
            n = len(sorted_times)
            if n % 2 == 0:
                self.median_time = (sorted_times[n//2 - 1] + sorted_times[n//2]) / 2
            else:
                self.median_time = sorted_times[n//2]
            
            # Calculate standard deviation
            if len(successful_times) > 1:
                variance = sum((t - self.average_time) ** 2 for t in successful_times) / (len(successful_times) - 1)
                self.std_deviation = variance ** 0.5


class PerformanceMeasurement:
    """Utility class for measuring KageBunshin performance."""
    
    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.original_env = {}
    
    @asynccontextmanager
    async def isolated_environment(self, mode: PerformanceMode):
        """Context manager for isolated environment setup."""
        # Store original environment
        mode_env = self.config.get_environment_for_mode(mode)
        original_values = {}
        
        try:
            # Set environment variables for this mode
            for key, value in mode_env.items():
                original_values[key] = os.environ.get(key)
                os.environ[key] = value
            
            # Create temporary browser data directory if needed
            temp_dir = None
            if self.config.clean_browser_data:
                temp_dir = tempfile.mkdtemp(prefix="kage_benchmark_")
            
            yield temp_dir
            
        finally:
            # Restore original environment
            for key, original_value in original_values.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value
            
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    async def run_single_benchmark(
        self, 
        scenario: BenchmarkScenario, 
        mode: PerformanceMode, 
        run_number: int
    ) -> BenchmarkResult:
        """Run a single benchmark scenario with the specified performance mode."""
        
        async with self.isolated_environment(mode) as temp_dir:
            result = BenchmarkResult(
                scenario_name=scenario.name,
                performance_mode=mode.value,
                run_number=run_number,
                start_time=0,
                end_time=0,
                execution_time=0,
                success=False,
                total_operations_expected=len(scenario.expected_operations)
            )
            
            try:
                # Import Agent here to get fresh imports with new environment variables
                from kagebunshin import Agent
                
                # Create agent with benchmark configuration
                agent_config = {
                    "task": scenario.task,
                    "headless": self.config.headless,
                    "viewport_width": self.config.viewport_width,
                    "viewport_height": self.config.viewport_height,
                }
                
                if temp_dir:
                    agent_config["user_data_dir"] = temp_dir
                
                agent = Agent(**agent_config)
                
                # Measure execution time
                result.start_time = time.time()
                
                # Run the benchmark with timeout
                try:
                    result.result_text = await asyncio.wait_for(
                        agent.run(),
                        timeout=scenario.timeout
                    )
                    result.success = True
                    
                except asyncio.TimeoutError:
                    result.error_message = f"Benchmark timed out after {scenario.timeout} seconds"
                    result.success = False
                
                result.end_time = time.time()
                result.execution_time = result.end_time - result.start_time
                
            except Exception as e:
                result.end_time = time.time()
                result.execution_time = result.end_time - result.start_time
                result.error_message = str(e)
                result.success = False
            
            return result
    
    async def run_scenario_benchmarks(
        self, 
        scenario: BenchmarkScenario, 
        mode: PerformanceMode
    ) -> ScenarioSummary:
        """Run all benchmark runs for a scenario in a specific performance mode."""
        
        summary = ScenarioSummary(
            scenario_name=scenario.name,
            performance_mode=mode.value
        )
        
        print(f"Running {self.config.runs_per_scenario} runs of '{scenario.name}' in {mode.value} mode...")
        
        for run_num in range(1, self.config.runs_per_scenario + 1):
            print(f"  Run {run_num}/{self.config.runs_per_scenario}...")
            
            result = await self.run_single_benchmark(scenario, mode, run_num)
            summary.runs.append(result)
            
            if result.success:
                print(f"    ✅ Completed in {result.execution_time:.2f}s")
            else:
                print(f"    ❌ Failed: {result.error_message}")
            
            # Brief delay between runs to allow cleanup
            await asyncio.sleep(2)
        
        summary.calculate_summary()
        return summary
    
    def format_summary_table(self, summaries: List[ScenarioSummary]) -> str:
        """Format benchmark summaries into a readable table."""
        
        lines = []
        lines.append("=" * 80)
        lines.append("KageBunshin Performance Benchmark Results")
        lines.append("=" * 80)
        lines.append("")
        
        # Group by scenario
        scenarios = {}
        for summary in summaries:
            if summary.scenario_name not in scenarios:
                scenarios[summary.scenario_name] = []
            scenarios[summary.scenario_name].append(summary)
        
        for scenario_name, scenario_summaries in scenarios.items():
            lines.append(f"Scenario: {scenario_name}")
            lines.append("-" * 60)
            lines.append(f"{'Mode':<12} {'Success Rate':<12} {'Avg Time':<10} {'Min Time':<10} {'Max Time':<10}")
            lines.append("-" * 60)
            
            for summary in scenario_summaries:
                lines.append(
                    f"{summary.performance_mode:<12} "
                    f"{summary.success_rate:>10.1%} "
                    f"{summary.average_time:>9.2f}s "
                    f"{summary.min_time:>9.2f}s "
                    f"{summary.max_time:>9.2f}s"
                )
            
            # Calculate performance improvements
            if len(scenario_summaries) >= 2:
                lines.append("")
                stealth_summary = next((s for s in scenario_summaries if s.performance_mode == "stealth"), None)
                
                for summary in scenario_summaries:
                    if summary.performance_mode != "stealth" and stealth_summary and stealth_summary.average_time > 0:
                        improvement = (stealth_summary.average_time - summary.average_time) / stealth_summary.average_time
                        lines.append(f"  {summary.performance_mode} vs stealth: {improvement:+.1%} improvement")
            
            lines.append("")
        
        return "\n".join(lines)