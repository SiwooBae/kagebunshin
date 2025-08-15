"""
Logging utilities for KageBunshin.
"""

from datetime import datetime


def log_with_timestamp(message: str) -> None:
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")