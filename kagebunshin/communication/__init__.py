"""
Agent-to-agent communication systems.

Contains Redis-based group chat for agent coordination.
"""

from .group_chat import GroupChatClient, ChatRecord

__all__ = [
    "GroupChatClient",
    "ChatRecord",
]