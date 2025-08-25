"""
Kagebunshin: AI web automation agent swarm with self-cloning capabilities.

Kagebunshin is a web-browsing, research-focused agent swarm that can clone itself
and navigate multiple branches simultaneously. It features:

- Self-cloning for parallelized execution
- Agent group chat for communication between clones
- Tool-augmented agent loop via LangGraph
- Human-like delays, typing, scrolling
- Browser fingerprint and stealth adjustments
- Tab management and PDF handling

Public API exports the `KageBunshinAgent` orchestrator and `KageBunshinRunner` CLI interface.
"""

from .core.agent import KageBunshinAgent
from .cli.runner import KageBunshinRunner
from .agent import Agent

__all__ = ["Agent", "KageBunshinAgent", "KageBunshinRunner"]
__version__ = "0.1.0"

