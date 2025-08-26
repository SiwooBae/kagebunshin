"""
Command-line interface for KageBunshin performance benchmarks.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from .benchmark_runner import run_quick_benchmark, run_full_benchmark, BenchmarkRunner
from .benchmark_config import BenchmarkConfig, BenchmarkScenario, PerformanceMode


def create_custom_config(args):
    """Create a custom benchmark configuration from command line arguments."""
    
    # Parse performance modes
    modes = []
    for mode_str in args.modes:
        try:
            modes.append(PerformanceMode(mode_str.lower()))
        except ValueError:
            valid_modes = [m.value for m in PerformanceMode]
            print(f"❌ Invalid performance mode: {mode_str}")
            print(f"   Valid modes: {', '.join(valid_modes)}")
            sys.exit(1)
    
    # Handle headless setting
    headless = not getattr(args, 'no_headless', False)
    
    config = BenchmarkConfig(
        runs_per_scenario=args.runs,
        timeout_per_run=args.timeout,
        headless=headless,
        performance_modes=modes
    )
    
    # Add custom scenarios if specified
    if args.scenarios:
        custom_scenarios = []
        for scenario_name in args.scenarios:
            # Find matching default scenario
            default_scenario = None
            for scenario in config.scenarios:
                if scenario.name == scenario_name:
                    default_scenario = scenario
                    break
            
            if default_scenario:
                custom_scenarios.append(default_scenario)
            else:
                available_scenarios = [s.name for s in config.scenarios]
                print(f"❌ Unknown scenario: {scenario_name}")
                print(f"   Available scenarios: {', '.join(available_scenarios)}")
                sys.exit(1)
        
        config.scenarios = custom_scenarios
    
    return config


async def main():
    """Main CLI entry point."""
    
    parser = argparse.ArgumentParser(
        description="KageBunshin Performance Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run quick test
  python -m evals quick
  
  # Run full benchmark suite
  python -m evals full
  
  # Custom benchmark with specific modes
  python -m evals custom --modes stealth balanced --runs 2
  
  # Test specific scenarios
  python -m evals custom --scenarios simple_form_fill navigation_heavy
  
  # Visible browser mode for debugging
  python -m evals quick --no-headless

Available scenarios:
  simple_form_fill    - Fill out a simple form
  navigation_heavy    - Navigate through multiple pages  
  search_and_extract  - Search and extract information
  complex_interaction - Complex multi-step interactions

Available performance modes:
  stealth   - Maximum reliability, no optimization
  balanced  - Default balanced approach (default)
  fast      - Maximum speed optimization
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Benchmark command')
    
    # Quick benchmark command
    quick_parser = subparsers.add_parser('quick', help='Run quick benchmark (2 runs, 1 scenario)')
    quick_parser.add_argument('--no-headless', action='store_true', 
                             help='Run with visible browser (for debugging)')
    
    # Full benchmark command  
    full_parser = subparsers.add_parser('full', help='Run full benchmark suite')
    full_parser.add_argument('--no-headless', action='store_true',
                            help='Run with visible browser (for debugging)')
    
    # Custom benchmark command
    custom_parser = subparsers.add_parser('custom', help='Run custom benchmark configuration')
    custom_parser.add_argument('--modes', nargs='+', default=['stealth', 'balanced', 'fast'],
                              help='Performance modes to test (default: all)')
    custom_parser.add_argument('--scenarios', nargs='+', 
                              help='Specific scenarios to run (default: all)')
    custom_parser.add_argument('--runs', type=int, default=3,
                              help='Number of runs per scenario (default: 3)')
    custom_parser.add_argument('--timeout', type=int, default=300,
                              help='Timeout per run in seconds (default: 300)')
    custom_parser.add_argument('--no-headless', action='store_true',
                              help='Run with visible browser (for debugging)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available scenarios and modes')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # List available options
    if args.command == 'list':
        print("📋 Available Benchmark Scenarios:")
        print("-" * 40)
        config = BenchmarkConfig()
        for scenario in config.scenarios:
            print(f"  {scenario.name:<20} - {scenario.description}")
            print(f"  {'':20}   Task: {scenario.task[:60]}...")
            if scenario.target_url:
                print(f"  {'':20}   URL: {scenario.target_url}")
            print()
        
        print("⚡ Available Performance Modes:")
        print("-" * 40) 
        for mode in PerformanceMode:
            print(f"  {mode.value:<12} - ", end="")
            if mode == PerformanceMode.STEALTH:
                print("Maximum reliability, minimal optimization")
            elif mode == PerformanceMode.BALANCED:
                print("Balanced approach (default)")
            elif mode == PerformanceMode.FAST:
                print("Maximum speed optimization")
        return
    
    try:
        # Handle headless setting
        headless_mode = not getattr(args, 'no_headless', False)
        if not headless_mode:
            print("🖥️  Running in visible browser mode (--no-headless)")
        
        # Run appropriate benchmark
        if args.command == 'quick':
            print("🚀 Running quick benchmark...")
            # Override headless setting for quick benchmark
            if hasattr(args, 'no_headless') and args.no_headless:
                # Create custom config for quick benchmark with headless=False
                from .benchmark_config import BenchmarkScenario
                config = BenchmarkConfig(
                    runs_per_scenario=2,
                    headless=False,
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
                await runner.run_and_report()
            else:
                await run_quick_benchmark()
            
        elif args.command == 'full':
            print("🎯 Running full benchmark suite...")
            config = BenchmarkConfig(headless=headless_mode)
            runner = BenchmarkRunner(config)
            await runner.run_and_report()
            
        elif args.command == 'custom':
            print("⚙️  Running custom benchmark...")
            config = create_custom_config(args)
            runner = BenchmarkRunner(config)
            await runner.run_and_report()
        
        print("\n✅ Benchmark completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Benchmark failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())