# KageBunshin Performance Benchmarks

This directory contains a comprehensive benchmarking framework to measure real-world performance improvements from the KageBunshin performance optimizer.

## Quick Start

```bash
# Run a quick test (2 runs, 1 simple scenario)
python -m evals quick

# Run the full benchmark suite (all scenarios, all modes, 3 runs each)  
python -m evals full

# List available scenarios and performance modes
python -m evals list
```

## Performance Modes

- **stealth**: Maximum reliability, no performance optimization (baseline)
- **balanced**: Intelligent optimization with good reliability (default)
- **fast**: Maximum speed optimization with acceptable reliability

## Benchmark Scenarios

1. **simple_form_fill**: Fill out a basic form with test data
2. **navigation_heavy**: Navigate through multiple pages and links  
3. **search_and_extract**: Perform search and extract information from results
4. **complex_interaction**: Multi-step interactions with data extraction

## Custom Benchmarks

```bash
# Test only specific performance modes
python -m evals custom --modes stealth balanced --runs 2

# Test specific scenarios  
python -m evals custom --scenarios simple_form_fill navigation_heavy

# Visible browser mode for debugging
python -m evals quick --no-headless

# Custom configuration
python -m evals custom --modes fast --scenarios simple_form_fill --runs 5 --timeout 120
```

## Programmatic Usage

```python
import asyncio
from evals import run_quick_benchmark, run_full_benchmark, BenchmarkRunner, BenchmarkConfig

# Quick benchmark
result = asyncio.run(run_quick_benchmark())

# Full benchmark  
result = asyncio.run(run_full_benchmark())

# Custom benchmark
config = BenchmarkConfig(
    runs_per_scenario=2,
    headless=True,
    performance_modes=["balanced", "fast"]
)
runner = BenchmarkRunner(config)
result = asyncio.run(runner.run_and_report())
```

## Output

The benchmark system provides:

1. **Real-time progress**: Shows which scenarios are running and their results
2. **Summary table**: Performance comparison across all modes and scenarios  
3. **Detailed analysis**: Performance improvements, success rates, and reliability metrics
4. **Raw data**: JSON files with detailed timing data for further analysis
5. **Reports**: Human-readable benchmark reports saved to files

### Example Output

```
KageBunshin Performance Benchmark Results
================================================================================

Scenario: simple_form_fill
------------------------------------------------------------
Mode         Success Rate  Avg Time   Min Time   Max Time
------------------------------------------------------------
stealth           100%      15.23s     14.87s     15.61s
balanced          100%      11.45s     11.02s     11.89s
fast              100%       8.76s      8.43s      9.12s

  balanced vs stealth: +24.8% improvement
  fast vs stealth: +42.5% improvement

📊 Simple Form Fill:
   • Balanced mode: +24.8% vs stealth (11.45s vs 15.23s) ⚡
   • Fast mode: +42.5% vs stealth (8.76s vs 15.23s) 🚀
   • Most reliable: stealth (100% success rate)

🎯 Key Findings:
   • Balanced mode average improvement: +20.3%
   • Fast mode average improvement: +38.7%
   • Stealth mode average success rate: 100.0%
   • Balanced mode average success rate: 95.8%
   • Fast mode average success rate: 91.7%
```

## Results Storage

Results are automatically saved to the `evals/results/` directory:

- `benchmark_results_YYYYMMDD_HHMMSS.json`: Raw timing data
- `benchmark_report_YYYYMMDD_HHMMSS.txt`: Human-readable report

## Environment Requirements

- **OpenAI API Key**: Set `OPENAI_API_KEY` environment variable
- **Playwright**: Browser automation (installed automatically with KageBunshin)
- **Internet Connection**: Required for testing real websites

## Performance Notes

- Benchmarks use isolated browser environments for each test
- Environment variables are properly isolated between different performance modes
- Temporary browser profiles are cleaned up automatically
- Each scenario runs multiple times to ensure statistical validity

## Troubleshooting

### Common Issues

**Timeouts**: Increase timeout with `--timeout 600` for slower connections
**Browser Issues**: Use `--no-headless` to see browser interactions visually
**API Limits**: Reduce runs with `--runs 1` to minimize API usage

### Debug Mode

```bash
# Run with visible browser to see what's happening
python -m evals quick --no-headless

# Test just one scenario with minimal runs
python -m evals custom --scenarios simple_form_fill --runs 1 --no-headless
```

This benchmarking framework provides **real, measured performance data** to validate the effectiveness of the KageBunshin performance optimization system.