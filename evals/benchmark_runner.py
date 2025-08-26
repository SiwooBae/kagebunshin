"""
Main benchmark runner for KageBunshin performance evaluation.
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .benchmark_config import BenchmarkConfig, PerformanceMode
from .performance_measurement import PerformanceMeasurement, ScenarioSummary


class BenchmarkRunner:
    """Main class for running KageBunshin performance benchmarks."""
    
    def __init__(self, config: BenchmarkConfig = None):
        self.config = config or BenchmarkConfig()
        self.measurement = PerformanceMeasurement(self.config)
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)
    
    async def run_all_benchmarks(self) -> List[ScenarioSummary]:
        """Run all configured benchmarks and return results."""
        
        print("🚀 Starting KageBunshin Performance Benchmarks")
        print(f"   Scenarios: {len(self.config.scenarios)}")
        print(f"   Performance Modes: {[mode.value for mode in self.config.performance_modes]}")
        print(f"   Runs per scenario: {self.config.runs_per_scenario}")
        print("")
        
        all_summaries = []
        total_benchmarks = len(self.config.scenarios) * len(self.config.performance_modes)
        current_benchmark = 0
        
        for scenario in self.config.scenarios:
            print(f"📋 Scenario: {scenario.name}")
            print(f"   Description: {scenario.description}")
            print(f"   Task: {scenario.task}")
            if scenario.target_url:
                print(f"   Target URL: {scenario.target_url}")
            print("")
            
            for mode in self.config.performance_modes:
                current_benchmark += 1
                print(f"⚡ [{current_benchmark}/{total_benchmarks}] Running in {mode.value} mode...")
                
                try:
                    summary = await self.measurement.run_scenario_benchmarks(scenario, mode)
                    all_summaries.append(summary)
                    
                    if summary.success_rate > 0:
                        print(f"   ✅ {summary.success_rate:.0%} success rate, avg time: {summary.average_time:.2f}s")
                    else:
                        print(f"   ❌ All runs failed")
                        
                except Exception as e:
                    print(f"   💥 Benchmark failed with error: {e}")
                
                print("")
        
        return all_summaries
    
    def save_results(self, summaries: List[ScenarioSummary], filename: Optional[str] = None) -> str:
        """Save benchmark results to a JSON file."""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_results_{timestamp}.json"
        
        filepath = self.results_dir / filename
        
        # Convert summaries to serializable format
        results_data = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "runs_per_scenario": self.config.runs_per_scenario,
                "timeout_per_run": self.config.timeout_per_run,
                "headless": self.config.headless,
                "viewport_width": self.config.viewport_width,
                "viewport_height": self.config.viewport_height,
                "performance_modes": [mode.value for mode in self.config.performance_modes],
                "scenarios": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "task": s.task,
                        "target_url": s.target_url,
                        "expected_operations": s.expected_operations,
                        "timeout": s.timeout
                    }
                    for s in self.config.scenarios
                ]
            },
            "results": []
        }
        
        for summary in summaries:
            summary_data = {
                "scenario_name": summary.scenario_name,
                "performance_mode": summary.performance_mode,
                "total_runs": summary.total_runs,
                "successful_runs": summary.successful_runs,
                "success_rate": summary.success_rate,
                "average_time": summary.average_time,
                "median_time": summary.median_time,
                "min_time": summary.min_time,
                "max_time": summary.max_time,
                "std_deviation": summary.std_deviation,
                "runs": [
                    {
                        "run_number": run.run_number,
                        "execution_time": run.execution_time,
                        "success": run.success,
                        "error_message": run.error_message
                    }
                    for run in summary.runs
                ]
            }
            results_data["results"].append(summary_data)
        
        with open(filepath, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        return str(filepath)
    
    def generate_report(self, summaries: List[ScenarioSummary]) -> str:
        """Generate a comprehensive benchmark report."""
        
        report = self.measurement.format_summary_table(summaries)
        
        # Add performance comparison analysis
        report += "\n\n"
        report += "=" * 80 + "\n"
        report += "Performance Analysis\n"
        report += "=" * 80 + "\n\n"
        
        # Group by scenario for analysis
        scenarios = {}
        for summary in summaries:
            if summary.scenario_name not in scenarios:
                scenarios[summary.scenario_name] = {}
            scenarios[summary.scenario_name][summary.performance_mode] = summary
        
        for scenario_name, mode_summaries in scenarios.items():
            report += f"📊 {scenario_name.title().replace('_', ' ')}:\n"
            
            stealth_summary = mode_summaries.get("stealth")
            balanced_summary = mode_summaries.get("balanced") 
            fast_summary = mode_summaries.get("fast")
            
            if stealth_summary and stealth_summary.success_rate > 0:
                baseline_time = stealth_summary.average_time
                
                # Compare balanced mode
                if balanced_summary and balanced_summary.success_rate > 0:
                    improvement = (baseline_time - balanced_summary.average_time) / baseline_time
                    report += f"   • Balanced mode: {improvement:+.1%} vs stealth "
                    if improvement > 0:
                        report += f"({balanced_summary.average_time:.2f}s vs {baseline_time:.2f}s) ⚡\n"
                    else:
                        report += f"({balanced_summary.average_time:.2f}s vs {baseline_time:.2f}s) 🐌\n"
                
                # Compare fast mode  
                if fast_summary and fast_summary.success_rate > 0:
                    improvement = (baseline_time - fast_summary.average_time) / baseline_time
                    report += f"   • Fast mode: {improvement:+.1%} vs stealth "
                    if improvement > 0:
                        report += f"({fast_summary.average_time:.2f}s vs {baseline_time:.2f}s) 🚀\n"
                    else:
                        report += f"({fast_summary.average_time:.2f}s vs {baseline_time:.2f}s) 🐌\n"
                
                # Reliability analysis
                modes_by_reliability = sorted(
                    [(mode, summary.success_rate) for mode, summary in mode_summaries.items()],
                    key=lambda x: x[1],
                    reverse=True
                )
                
                if len(modes_by_reliability) > 1:
                    most_reliable = modes_by_reliability[0]
                    report += f"   • Most reliable: {most_reliable[0]} ({most_reliable[1]:.0%} success rate)\n"
            
            else:
                report += f"   • ⚠️  No successful stealth mode baseline for comparison\n"
            
            report += "\n"
        
        # Overall summary
        report += "🎯 Key Findings:\n"
        
        # Calculate average improvements across all scenarios
        total_scenarios = len(scenarios)
        balanced_improvements = []
        fast_improvements = []
        
        for scenario_name, mode_summaries in scenarios.items():
            stealth = mode_summaries.get("stealth")
            balanced = mode_summaries.get("balanced")
            fast = mode_summaries.get("fast")
            
            if stealth and stealth.success_rate > 0:
                if balanced and balanced.success_rate > 0:
                    improvement = (stealth.average_time - balanced.average_time) / stealth.average_time
                    balanced_improvements.append(improvement)
                
                if fast and fast.success_rate > 0:
                    improvement = (stealth.average_time - fast.average_time) / stealth.average_time
                    fast_improvements.append(improvement)
        
        if balanced_improvements:
            avg_balanced_improvement = sum(balanced_improvements) / len(balanced_improvements)
            report += f"   • Balanced mode average improvement: {avg_balanced_improvement:+.1%}\n"
        
        if fast_improvements:
            avg_fast_improvement = sum(fast_improvements) / len(fast_improvements)
            report += f"   • Fast mode average improvement: {avg_fast_improvement:+.1%}\n"
        
        # Success rate analysis
        all_success_rates = [(s.performance_mode, s.success_rate) for s in summaries]
        mode_success_rates = {}
        for mode, rate in all_success_rates:
            if mode not in mode_success_rates:
                mode_success_rates[mode] = []
            mode_success_rates[mode].append(rate)
        
        for mode, rates in mode_success_rates.items():
            avg_success_rate = sum(rates) / len(rates)
            report += f"   • {mode.title()} mode average success rate: {avg_success_rate:.1%}\n"
        
        return report
    
    async def run_and_report(self) -> str:
        """Run all benchmarks and generate a complete report."""
        
        print("Starting comprehensive performance benchmark...")
        print("")
        
        # Run benchmarks
        summaries = await self.run_all_benchmarks()
        
        # Save raw results
        results_file = self.save_results(summaries)
        print(f"💾 Raw results saved to: {results_file}")
        print("")
        
        # Generate and display report
        report = self.generate_report(summaries)
        
        # Save report to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.results_dir / f"benchmark_report_{timestamp}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"📊 Report saved to: {report_file}")
        print("")
        print(report)
        
        return report


async def run_quick_benchmark() -> str:
    """Run a quick benchmark with minimal scenarios for testing."""
    from .benchmark_config import BenchmarkScenario
    
    config = BenchmarkConfig(
        runs_per_scenario=2,  # Reduced for quick testing
        scenarios=[
            BenchmarkScenario(
                name="quick_navigation",
                description="Quick navigation test",
                task="Go to example.com and extract the page content",
                target_url="https://example.com",
                expected_operations=["browser_goto", "extract_page_content"],
                timeout=60
            )
        ]
    )
    
    runner = BenchmarkRunner(config)
    return await runner.run_and_report()


async def run_full_benchmark() -> str:
    """Run the full benchmark suite with all scenarios."""
    config = BenchmarkConfig()  # Uses all default scenarios
    runner = BenchmarkRunner(config)
    return await runner.run_and_report()


if __name__ == "__main__":
    # Run quick benchmark if executed directly
    asyncio.run(run_quick_benchmark())