"""
KageBunshin Performance Evaluation Framework

This module provides comprehensive benchmarking tools to measure
real-world performance improvements from the performance optimizer.

Quick Start:
    # Run a quick benchmark
    python -m evals quick
    
    # Run full benchmark suite  
    python -m evals full
    
    # Programmatic usage
    from evals import run_quick_benchmark, run_full_benchmark
    
    import asyncio
    result = asyncio.run(run_quick_benchmark())
"""

from .benchmark_config import BenchmarkConfig, BenchmarkScenario, PerformanceMode
from .performance_measurement import PerformanceMeasurement, BenchmarkResult, ScenarioSummary  
from .benchmark_runner import BenchmarkRunner, run_quick_benchmark, run_full_benchmark

__all__ = [
    # Configuration
    "BenchmarkConfig", 
    "BenchmarkScenario", 
    "PerformanceMode",
    
    # Measurement
    "PerformanceMeasurement",
    "BenchmarkResult", 
    "ScenarioSummary",
    
    # Runner
    "BenchmarkRunner",
    "run_quick_benchmark",
    "run_full_benchmark"
]