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
from .blind_agent import BlindAgent

__all__ = [
    "LameAgent",
    "BlindAgent",
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
    # Create BlindAgent using the new KageBunshinAgent-compatible interface
    # This will internally create the LameAgent
    blind_agent = await BlindAgent.create(context)
    
    # Return the BlindAgent and its internal LameAgent for convenience
    return blind_agent, blind_agent.lame_agent