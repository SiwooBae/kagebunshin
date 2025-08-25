"""
Example usage of the comprehensive Agent API for KageBunshin.

This demonstrates the new simplified API with full configuration control,
eliminating the need to edit settings files.
"""

import asyncio
import dotenv
from kagebunshin import Agent
from langchain.chat_models import ChatOpenAI

dotenv.load_dotenv()


async def simple_example():
    """Simplest usage - uses intelligent defaults."""
    print("=== Simple Example ===")
    
    agent = Agent(task="Find a news article on the latest AI safety research")
    result = await agent.run()
    print(f"Result: {result}")


async def custom_llm_example():
    """Example with custom LLM instance."""
    print("\n=== Custom LLM Example ===")
    
    agent = Agent(
        task="Find repo stars and analyze recent activity trends",
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0)
    )
    
    result = await agent.run()
    print(f"Result: {result}")


async def comprehensive_config_example():
    """Example with comprehensive configuration."""
    print("\n=== Comprehensive Configuration Example ===")
    
    agent = Agent(
        task="Research the latest AI safety developments and compile a summary",
        
        # LLM Configuration
        llm_model="gpt-4o-mini",          # Use a specific model
        llm_provider="openai",            # Provider
        llm_reasoning_effort="medium",    # Higher reasoning for complex task
        llm_temperature=0.2,              # Lower temperature for consistency
        
        # Summarizer Configuration
        summarizer_model="gpt-5-nano",    # Cheaper model for action summaries
        enable_summarization=True,        # Enable to see what the agent is doing
        
        # Browser Configuration
        headless=False,                   # Visible browser for debugging
        viewport_width=1920,              # Larger viewport
        viewport_height=1080,
        
        # Workflow Configuration
        recursion_limit=200,              # Allow deeper recursion for complex tasks
        max_iterations=150,               # More iterations for thorough research
        timeout=120,                      # Longer timeout per operation
        
        # Multi-agent Configuration
        group_room="ai_research",         # Custom group chat room
        username="ai_researcher"          # Custom agent name
    )
    
    result = await agent.run()
    print(f"Result: {result}")


async def mixed_config_example():
    """Example mixing LLM instance with configuration parameters."""
    print("\n=== Mixed Configuration Example ===")
    
    # Use custom LLM but override some settings
    custom_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    
    agent = Agent(
        task="Compare pricing of top 3 cloud providers for ML workloads",
        llm=custom_llm,                   # Use custom LLM instance
        llm_reasoning_effort="high",      # But use high reasoning effort
        viewport_width=1440,              # Custom viewport
        enable_summarization=True,        # Enable summaries
        headless=True                     # Run in background
    )
    
    result = await agent.run()
    print(f"Result: {result}")


async def validation_example():
    """Example showing configuration validation."""
    print("\n=== Configuration Validation Example ===")
    
    try:
        # This will raise a validation error
        agent = Agent(
            task="",  # Empty task
            viewport_width=0,  # Invalid viewport
            llm_provider="invalid"  # Invalid provider
        )
    except ValueError as e:
        print(f"Configuration error (expected): {e}")
    
    # This will work
    agent = Agent(
        task="Valid task",
        viewport_width=1280,
        llm_provider="openai"
    )
    print("Valid configuration created successfully!")


if __name__ == "__main__":
    # Run examples
    asyncio.run(simple_example())
    asyncio.run(custom_llm_example())
    # asyncio.run(comprehensive_config_example())  # Uncomment for full demo
    # asyncio.run(mixed_config_example())          # Uncomment for mixed demo
    asyncio.run(validation_example())