"""
Example usage of the simplified Agent API for KageBunshin.

This demonstrates how to use the new simplified API that handles all browser 
lifecycle management automatically, similar to browser-use.
"""

import asyncio
import dotenv
from kagebunshin import Agent
from langchain.chat_models import ChatOpenAI

dotenv.load_dotenv()


async def main():
    # Create agent with task and LLM
    agent = Agent(
        task="Find the number of stars of the browser-use repo on GitHub",
        llm=ChatOpenAI(model="gpt-4o-mini"),
        headless=False,  # Set to True to run in background
    )
    
    # Run the agent and get result
    result = await agent.run()
    print(f"Result: {result}")


async def advanced_example():
    """Example with more configuration options."""
    
    agent = Agent(
        task="Search for the latest Python release notes and summarize key features",
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0.1),
        headless=True,
        enable_summarization=True,
        group_room="research_team",
        username="python_researcher"
    )
    
    result = await agent.run()
    print(f"Advanced result: {result}")


if __name__ == "__main__":
    # Run simple example
    asyncio.run(main())
    
    # Uncomment to run advanced example
    # asyncio.run(advanced_example())