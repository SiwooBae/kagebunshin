"""
Kagebunshin: AI web automation agent (formerly webvoyager_v2).

Public API exports the `WebVoyagerV2` orchestrator.
"""

from .webvoyager_v2 import WebVoyagerV2
from .cli_runner import WebVoyagerRunner
__all__ = ["WebVoyagerV2"]
__version__ = "0.1.0"

