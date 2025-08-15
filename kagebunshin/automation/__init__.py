"""
Browser automation and stealth functionality.

Contains human behavior simulation, fingerprint evasion, and browser utilities.
"""

from .behavior import (
    human_delay,
    get_random_offset_in_bbox,
    human_mouse_move,
    human_type_text,
    human_scroll,
    smart_delay_between_actions,
)

from .fingerprinting import (
    apply_fingerprint_profile,
    apply_fingerprint_profile_to_context,
    get_random_fingerprint_profile,
    get_stealth_browser_args,
)

__all__ = [
    "human_delay",
    "get_random_offset_in_bbox", 
    "human_mouse_move",
    "human_type_text",
    "human_scroll",
    "smart_delay_between_actions",
    "apply_fingerprint_profile",
    "apply_fingerprint_profile_to_context",
    "get_random_fingerprint_profile",
    "get_stealth_browser_args",
]