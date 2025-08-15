"""
Agent name generation utilities.
"""

import secrets
import petname


def generate_agent_name() -> str:
    """Generate a unique agent name using petname library."""
    try:
        # Generate a 2-word pet name (adjective-animal)
        name = petname.generate(words=2, separator="-").title()
        # suffix = secrets.token_hex(2)  # 4 hex chars
        # return f"{name}-{suffix.upper()}"
        return name
    except Exception:
        # Fallback in case petname fails
        pass
    
    fallback = f"agent-{secrets.token_hex(4)}"
    return fallback.title()