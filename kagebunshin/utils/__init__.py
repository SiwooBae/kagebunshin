"""
Shared utilities.

Contains formatting, logging, and naming utilities used across the project.
"""

from .formatting import (
    html_to_markdown,
    format_text_context,
    format_bbox_context,
    format_tab_context,
    format_img_context,
    format_enhanced_page_context,
    annotate_page,
)

from .naming import generate_agent_name

from .logging import log_with_timestamp

__all__ = [
    "html_to_markdown",
    "format_text_context",
    "format_bbox_context", 
    "format_tab_context",
    "format_img_context",
    "format_enhanced_page_context",
    "annotate_page",
    "generate_agent_name",
    "log_with_timestamp",
]