"""
Blind and Lame Architecture for KageBunshin

This module implements a two-agent architecture inspired by text-based environments
like ALFWORLD, where LLMs were trained on natural language state descriptions.

The architecture consists of:
- LameAgent: Can see and interact with web pages but has limited reasoning (gpt-5-nano)
- BlindAgent: Can reason and plan but cannot see pages directly (gpt-5 with reasoning)

The BlindAgent issues natural language commands to the LameAgent through the act() tool,
creating a text-based interface that leverages the LLMs' training on similar environments.
"""

from .lame_agent import LameAgent
from .blind_agent import BlindAgent, BlindAgentState

__all__ = [
    "LameAgent",
    "BlindAgent", 
    "BlindAgentState",
]


async def create_blind_and_lame_pair(context):
    """
    Convenience factory function to create a connected Blind-Lame agent pair.
    
    Args:
        context: Playwright BrowserContext for the Lame agent
        
    Returns:
        tuple: (blind_agent, lame_agent) ready to use
        
    Example:
        blind, lame = await create_blind_and_lame_pair(browser_context)
        result = await blind.ainvoke("Search for information about transformers")
    """
    # Create Lame agent first (it owns the browser)
    lame_agent = await LameAgent.create(context)
    
    # Create Blind agent with reference to Lame agent
    blind_agent = BlindAgent(lame_agent)
    
    return blind_agent, lame_agent