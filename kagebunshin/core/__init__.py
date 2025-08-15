"""
Core agent functionality.

Contains the main KageBunshin agent orchestrator, state models, and state management.
"""

from .agent import KageBunshinAgent
from .state import KageBunshinState, BBox, TabInfo, Annotation
from .state_manager import KageBunshinStateManager

__all__ = [
    "KageBunshinAgent",
    "KageBunshinState", 
    "BBox",
    "TabInfo",
    "Annotation",
    "KageBunshinStateManager"
]