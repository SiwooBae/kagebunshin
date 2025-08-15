"""
Kagebunshin: AI web automation agent.

Public API exports the `KageBunshinAgent` orchestrator.
"""

from .kagebunshin_agent import KageBunshinAgent
from .cli_runner import KageBunshinRunner
__all__ = ["KageBunshinAgent"]
__version__ = "0.1.0"

