"""Formatting utilities for KageBunshinV2 system

This module contains all formatting-related functions for converting various
data structures into human-readable contexts for LLM consumption.
"""

import os
import base64
import asyncio
import logging
from io import BytesIO
from typing import List, Dict, Any
import time

import html2text
import pypdf
from bs4 import BeautifulSoup
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PWTimeout

from ..core.state import BBox, Annotation, FrameStats, TabInfo



# Suppress logging warnings
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# Get the directory of the current file and load JavaScript modules for page marking
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
browser_js_dir = os.path.join(current_dir, "automation", "browser")

# JavaScript module files in dependency order
js_modules = [
    "text_merger.js",      # Text fragment merging (external dependency)
    "constants.js",        # Global variables and constants
    "overlay.js",          # Overlay management functions
    "utils.js",           # Viewport and utility functions
    "element-filtering.js", # Element filtering and visibility detection
    "element-analysis.js", # Hierarchical analysis functions
    "iframe-processing.js", # iframe processing functions
    "element-discovery.js", # Interactive elements discovery
    "main.js"             # Main markPage and unmarkPage functions
]

# Load and combine all JavaScript modules in dependency order
js_scripts = []
for module_file in js_modules:
    module_path = os.path.join(browser_js_dir, module_file)
    try:
        with open(module_path) as f:
            script_content = f.read()
            js_scripts.append(f"// ===== {module_file} =====\n{script_content}")
    except FileNotFoundError:
        logger.error(f"JavaScript module not found: {module_path}")
        raise

# Combine all scripts with separators for debugging
mark_page_script = "\n\n".join(js_scripts)


def html_to_markdown(html_content: str) -> str:
    """Convert visible HTML content to markdown, preserving links."""
    if not html_content:
        return ""

    # Parse and clean HTML using BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove elements that are not visible
    for tag in soup(['style', 'script', 'head', 'title', 'meta', '[document]']):
        tag.decompose()

    # Remove elements with display: none or visibility: hidden
    for el in soup.find_all(style=True):
        style = el['style'].lower()
        if 'display:none' in style or 'visibility:hidden' in style:
            el.decompose()

    # Convert the cleaned HTML to markdown
    h = html2text.HTML2Text()
    h.ignore_links = False  # Set to True if you want to ignore links
    h.ignore_images = True
    h.body_width = 0  # Prevent line wrapping
    return h.handle(str(soup))


def normalize_chat_content(content: Any, include_placeholders: bool = False) -> str:
    """Normalize chat message `content` into a plain string.

    Handles both legacy string content and the newer list-of-parts format
    (e.g., [{"type": "text", "text": "..."}, {"type": "image_url", ...}]).

    - Text parts are concatenated with newlines.
    - Non-text parts (images) are omitted by default, or replaced with
      placeholders when `include_placeholders=True`.
    """
    try:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for part in content:
                try:
                    if isinstance(part, dict):
                        part_type = part.get("type")
                        if part_type == "text":
                            text_val = part.get("text", "")
                            parts.append(str(text_val))
                        elif part_type in {"image_url", "input_image", "image"}:
                            if include_placeholders:
                                url = ""
                                image_url_val = part.get("image_url")
                                if isinstance(image_url_val, dict):
                                    url = image_url_val.get("url", "")
                                elif isinstance(image_url_val, str):
                                    url = image_url_val
                                url = url or part.get("url", "")
                                placeholder = f"[image:{url}]" if url else "[image]"
                                parts.append(placeholder)
                            # else: skip image parts
                        else:
                            # Fallback: try common text-like keys or stringify
                            text_like = part.get("text") or part.get("content")
                            if text_like is not None:
                                parts.append(str(text_like))
                    else:
                        parts.append(str(part))
                except Exception:
                    # Never let a malformed part break normalization
                    continue
            joined = "\n".join(p.strip() for p in parts if str(p).strip())
            return joined.strip()
        if isinstance(content, dict):
            part_type = content.get("type")
            if part_type == "text":
                return str(content.get("text", "")).strip()
            # Fallback to any text-like fields
            text_like = content.get("text") or content.get("content")
            if text_like is not None:
                return str(text_like).strip()
            return str(content).strip()
        return str(content).strip()
    except Exception:
        return str(content)


def strip_openai_reasoning_items(content: Any) -> Any:
    """Remove OpenAI Responses API 'reasoning' items from message content.

    Some OpenAI models (e.g., GPT-5 family) may return structured content parts
    including a part with {"type": "reasoning", "id": "rs_*", ...}.
    Those parts are output-only and must NOT be sent back as input on subsequent
    requests. This function removes such parts while preserving other content.

    The function is intentionally tolerant of unknown shapes and will recurse
    into lists/dicts, filtering out any dict with type == "reasoning" and any
    dict that looks like a reasoning artifact (id starting with "rs_").
    """
    try:
        # Drop entire dicts that explicitly mark reasoning
        if isinstance(content, dict):
            ctype = content.get("type")
            cid = content.get("id")
            if ctype == "reasoning":
                return None
            if isinstance(cid, str) and cid.startswith("rs_"):
                return None
            # Recurse into values
            cleaned: Dict[str, Any] = {}
            for k, v in content.items():
                cv = strip_openai_reasoning_items(v)
                if cv is not None:
                    cleaned[k] = cv
            return cleaned
        # For lists, filter out any None entries after recursion
        if isinstance(content, list):
            cleaned_list = []
            for part in content:
                cp = strip_openai_reasoning_items(part)
                if cp is None:
                    continue
                cleaned_list.append(cp)
            return cleaned_list
        # Primitive types are safe
        return content
    except Exception:
        # Fail-open: if anything odd happens, return original content
        return content

def format_text_context(markdown_content: str) -> str:
    """Format markdown text into a human-readable context string with deduplication."""
    if not markdown_content:
        return "Page Content (Markdown):\n\n"
    
    # Remove excessive whitespace and normalize line breaks
    cleaned_content = markdown_content.strip()
    
    # Remove duplicate consecutive lines
    lines = cleaned_content.split('\n')
    deduplicated_lines = []
    prev_line = None
    
    for line in lines:
        line = line.strip()
        # Skip if same as previous line (avoid exact duplicates)
        if line != prev_line or not line:
            deduplicated_lines.append(line)
        prev_line = line
    
    # Remove excessive empty lines (max 2 consecutive empty lines)
    final_lines = []
    empty_count = 0
    for line in deduplicated_lines:
        if not line.strip():
            empty_count += 1
            if empty_count <= 2:
                final_lines.append(line)
        else:
            empty_count = 0
            final_lines.append(line)
    
    cleaned_content = '\n'.join(final_lines).strip()
    return f"Page Content (Markdown):\n\n{cleaned_content}"


def format_bbox_context(bboxes: List[BBox], include_hierarchy: bool = True, include_viewport_context: bool = True) -> str:
    """Format bounding boxes into a hierarchical, human-readable context string with viewport information."""
    if not bboxes:
        return "No interactive elements found on this page."
    
    # Group elements by viewport position
    viewport_groups = {
        'in-viewport': [],
        'above-viewport': [],
        'below-viewport': [],
        'left-of-viewport': [],
        'right-of-viewport': []
    } if include_viewport_context else {'in-viewport': bboxes}
    
    # Categorize elements by viewport position
    if include_viewport_context:
        for i, bbox in enumerate(bboxes):
            position = getattr(bbox, 'viewportPosition', 'in-viewport')
            if position in viewport_groups:
                viewport_groups[position].append((i, bbox))
            else:
                viewport_groups['in-viewport'].append((i, bbox))
    else:
        viewport_groups['in-viewport'] = [(i, bbox) for i, bbox in enumerate(bboxes)]
    
    # Build hierarchical structure for each group
    sections = []
    
    # Function to format a single element with hierarchical indentation
    def format_element(index: int, bbox: BBox, base_indent: str = "") -> str:
        text = bbox.ariaLabel or ""
        if not text.strip():
            text = bbox.text[:100] + ("..." if len(bbox.text) > 100 else "")
        
        el_type = bbox.type
        # We don't need to show LLM the captcha indicator.
        # captcha_indicator = " [CAPTCHA]" if bbox.isCaptcha else ""
        captcha_indicator = ""
        
        # Frame context
        frame_info = ""
        if hasattr(bbox, 'frameContext') and bbox.frameContext != "main":
            frame_info = f" [Frame: {bbox.frameContext}]"
        
        # Distance information for out-of-viewport elements
        # distance_info = ""
        # if hasattr(bbox, 'distanceFromViewport') and bbox.distanceFromViewport > 0:
        #     distance_info = f" (distance: {int(bbox.distanceFromViewport)}px)"
        
        # Class information for important classes
        # class_info = ""
        # if bbox.className and any(
        #     keyword in bbox.className.lower() for keyword in ["captcha", "recaptcha", "hcaptcha", "btn", "button", "nav", "menu"]
        # ):
        #     class_info = f" class='{bbox.className[:30]}'"
        
        # ID information
        # id_info = ""
        # if bbox.elementId:
        #     id_info = f" id='{bbox.elementId[:20]}'"
        
        # Hierarchical information
        hierarchy_info = ""
        if include_hierarchy and hasattr(bbox, 'hierarchy') and bbox.hierarchy:
            hierarchy = bbox.hierarchy
            if hasattr(hierarchy, 'depth') and hierarchy.depth > 0:
                # Calculate indentation based on hierarchy depth
                indent_level = min(hierarchy.depth, 4)  # Cap at 4 levels for readability
                hierarchy_indent = "\t" * indent_level
                
                # Add sibling context
                # sibling_context = ""
                # if hasattr(hierarchy, 'siblingIndex') and hasattr(hierarchy, 'totalSiblings'):
                #     if hierarchy.totalSiblings > 1:
                #         sibling_context = f" [{hierarchy.siblingIndex + 1}/{hierarchy.totalSiblings}]"
                
                # Add semantic role if different from tag
                # semantic_info = ""
                # if hasattr(hierarchy, 'semanticRole') and hierarchy.semanticRole != el_type:
                #     semantic_info = f" role='{hierarchy.semanticRole}'"
                
                hierarchy_info = f"{hierarchy_indent}└─ "
                base_indent = hierarchy_indent
        
        focus_indicator = " [FOCUSED]" if hasattr(bbox, 'focused') and bbox.focused else ""
        main_content = f'{hierarchy_info}bbox_id: {index}{focus_indicator} (<{el_type}/>{captcha_indicator}): "{text}"{frame_info}'
        
        # Add children information if available
        children_info = ""
        if include_hierarchy and hasattr(bbox, 'hierarchy') and bbox.hierarchy:
            hierarchy = bbox.hierarchy
            if hasattr(hierarchy, 'childrenTypeBreakdown') and hierarchy.childrenTypeBreakdown:
                breakdown = hierarchy.childrenTypeBreakdown
                if hasattr(breakdown, 'summary') and breakdown.summary:
                    children_info = f"\n{base_indent}\t├─ Contains: {breakdown.summary}"
            elif hasattr(hierarchy, 'interactiveChildrenCount') and hierarchy.interactiveChildrenCount > 0:
                children_info = f"\n{base_indent}\t├─ Contains {hierarchy.interactiveChildrenCount} interactive children"
        
        return main_content + children_info
    
    # Build viewport sections
    viewport_labels = {
        'in-viewport': '🟢 CURRENT VIEWPORT',
        'above-viewport': '⬆️  ABOVE VIEWPORT',
        'below-viewport': '⬇️  BELOW VIEWPORT', 
        'left-of-viewport': '⬅️  LEFT OF VIEWPORT',
        'right-of-viewport': '➡️  RIGHT OF VIEWPORT'
    }
    
    for position, label in viewport_labels.items():
        elements = viewport_groups.get(position, [])
        
        if not elements:
            section_lines = [f"\n{label}: No elements"]
            sections.extend(section_lines)
            continue
            
        section_lines = [f"\n{label} ({len(elements)} elements):"]
        
        if include_hierarchy:
            # Group by frame context first
            frame_groups = {}
            for index, bbox in elements:
                frame_context = getattr(bbox, 'frameContext', 'main')
                if frame_context not in frame_groups:
                    frame_groups[frame_context] = []
                frame_groups[frame_context].append((index, bbox))
            
            # Format each frame group
            for frame_context, frame_elements in frame_groups.items():
                if frame_context != 'main':
                    section_lines.append(f"\t📦 {frame_context}:")
                    frame_indent = "\t"
                else:
                    frame_indent = ""
                
                # Sort by hierarchy depth for better readability
                frame_elements.sort(key=lambda x: getattr(x[1].hierarchy, 'depth', 0) if hasattr(x[1], 'hierarchy') and x[1].hierarchy else 0)
                
                for index, bbox in frame_elements:
                    # if it is outside of viewport, index should be "N/A"
                    if position != 'in-viewport':
                        index = "N/A"
                    formatted_element = format_element(index, bbox, frame_indent)
                    section_lines.append(f"{frame_indent}{formatted_element}")
        else:
            # Simple flat list without hierarchy
            for index, bbox in elements:
                formatted_element = format_element(index, bbox)
                section_lines.append(f"\t{formatted_element}")
        
        sections.extend(section_lines)
    
    # Add frame statistics if available
    if include_hierarchy and bboxes:
        frame_contexts = set()
        max_depth = 0
        for bbox in bboxes:
            if hasattr(bbox, 'frameContext'):
                frame_contexts.add(bbox.frameContext)
            if hasattr(bbox, 'hierarchy') and bbox.hierarchy and hasattr(bbox.hierarchy, 'depth'):
                max_depth = max(max_depth, bbox.hierarchy.depth)
    return "\n".join(sections)


def format_bbox_context_simple(bboxes: List[BBox]) -> str:
    """Legacy function for backward compatibility - simple flat format."""
    return format_bbox_context(bboxes, include_hierarchy=False, include_viewport_context=False)


def format_unified_context(bboxes: List[BBox], detail_level: str = "full_hierarchy", include_viewport_context: bool = True) -> str:
    """Format complete page context with unified representation (interactive + content elements).
    
    Args:
        bboxes: List of BBox elements (both interactive and content)
        detail_level: Level of detail to show:
            - "full_hierarchy": Complete DOM structure with content + interactive (default)
            - "interactive_only": Only interactive elements (backward compatibility)
            - "content_focus": Content elements with minimal interactive elements
        include_viewport_context: Whether to categorize by viewport position
    """
    if not bboxes:
        return "No elements found on this page."
    
    # Backward compatibility: filter to interactive only
    if detail_level == "interactive_only":
        interactive_bboxes = [b for b in bboxes if b.isInteractive]
        return format_bbox_context(interactive_bboxes, include_hierarchy=True, include_viewport_context=include_viewport_context)
    
    # Group elements by semantic sections first
    sections = {
        'header': [],
        'nav': [],
        'main': [],
        'aside': [],
        'footer': [],
        'unsectioned': []
    }
    
    # Group by viewport position if requested
    viewport_groups = {
        'in-viewport': [],
        'above-viewport': [],
        'below-viewport': [],
        'left-of-viewport': [],
        'right-of-viewport': []
    } if include_viewport_context else {'in-viewport': bboxes}
    
    # Categorize elements
    for i, bbox in enumerate(bboxes):
        # Group by semantic section
        section_key = bbox.semanticSection if bbox.semanticSection in sections else 'unsectioned'
        sections[section_key].append((i, bbox))
        
        # Group by viewport position
        if include_viewport_context:
            position = getattr(bbox, 'viewportPosition', 'in-viewport')
            if position in viewport_groups:
                viewport_groups[position].append((i, bbox))
            else:
                viewport_groups['in-viewport'].append((i, bbox))
        else:
            viewport_groups['in-viewport'].append((i, bbox))
    
    # Build output sections
    output_sections = []
    
    # Function to format a single element in unified style
    def format_unified_element(index: int, bbox: BBox, base_indent: str = "") -> str:
        # Get display text (may be truncated)
        text = bbox.text[:100] + ("..." if len(bbox.text) > 100 else "") if bbox.text else ""
        
        # Element type and role indicator
        type_info = f"<{bbox.type}/>"
        if not bbox.isInteractive:
            role_indicator = "📄" if bbox.elementRole == "content" else "🏗️" if bbox.elementRole == "structural" else "🧭" if bbox.elementRole == "navigation" else ""
        else:
            role_indicator = "🎯"
        
        # Interactive elements show bbox_id, content elements show "N/A"
        element_id = index if bbox.isInteractive else "N/A"
        
        # Build main element description with focus indicator
        focus_indicator = " [FOCUSED]" if hasattr(bbox, 'focused') and bbox.focused else ""
        main_desc = f'{role_indicator} bbox_id: {element_id}{focus_indicator} {type_info}'
        
        # Add content type for non-interactive elements
        if not bbox.isInteractive and bbox.contentType:
            if bbox.contentType == "heading" and bbox.headingLevel:
                main_desc += f" [H{bbox.headingLevel}]"
            else:
                main_desc += f" [{bbox.contentType}]"
        
        # Add text content
        if text.strip():
            if bbox.wordCount and bbox.wordCount > 0:
                word_info = f" ({bbox.wordCount} words)" if bbox.wordCount > 10 else ""
                if bbox.truncated:
                    word_info += " [truncated]"
                main_desc += f': "{text}"{word_info}'
            else:
                main_desc += f': "{text}"'
        
        # Add frame context if not main
        if hasattr(bbox, 'frameContext') and bbox.frameContext != "main":
            main_desc += f" [Frame: {bbox.frameContext}]"
        
        # Add container info for structural elements
        if bbox.isContainer and hasattr(bbox, 'hierarchy') and bbox.hierarchy:
            hierarchy = bbox.hierarchy
            if hasattr(hierarchy, 'childrenTypeBreakdown') and hierarchy.childrenTypeBreakdown:
                breakdown = hierarchy.childrenTypeBreakdown
                if hasattr(breakdown, 'summary') and breakdown.summary:
                    main_desc += f" [contains: {breakdown.summary}]"
            elif hasattr(hierarchy, 'childrenCount') and hierarchy.childrenCount > 0:
                main_desc += f" [contains {hierarchy.childrenCount} children]"
        
        return main_desc
    
    # Build viewport sections if requested
    if include_viewport_context:
        viewport_labels = {
            'in-viewport': '🟢 CURRENT VIEWPORT',
            'above-viewport': '⬆️  ABOVE VIEWPORT',
            'below-viewport': '⬇️  BELOW VIEWPORT', 
            'left-of-viewport': '⬅️  LEFT OF VIEWPORT',
            'right-of-viewport': '➡️  RIGHT OF VIEWPORT'
        }
        
        for position, label in viewport_labels.items():
            elements = viewport_groups.get(position, [])
            
            if not elements:
                continue
                
            section_lines = [f"\n{label} ({len(elements)} elements):"]
            
            # Group by semantic sections within viewport
            viewport_sections = {}
            for index, bbox in elements:
                section_key = bbox.semanticSection if bbox.semanticSection in sections else 'unsectioned'
                if section_key not in viewport_sections:
                    viewport_sections[section_key] = []
                viewport_sections[section_key].append((index, bbox))
            
            # Format each semantic section
            for section_name in ['header', 'nav', 'main', 'aside', 'footer', 'unsectioned']:
                section_elements = viewport_sections.get(section_name, [])
                if not section_elements:
                    continue
                
                if section_name != 'unsectioned':
                    section_lines.append(f"\t📍 {section_name.upper()} SECTION:")
                    section_indent = "\t\t"
                else:
                    section_indent = "\t"
                
                # Sort by interactive first, then by element role, then by hierarchy depth
                section_elements.sort(key=lambda x: (
                    not x[1].isInteractive,  # Interactive elements first
                    x[1].elementRole,
                    getattr(x[1].hierarchy, 'depth', 0) if hasattr(x[1], 'hierarchy') and x[1].hierarchy else 0
                ))
                
                for index, bbox in section_elements:
                    # For out-of-viewport elements, use N/A as index
                    display_index = index if position == 'in-viewport' else "N/A"
                    # change: now out of viewport elements don't include interactive elements
                    if position == 'in-viewport' or bbox.isInteractive == False:
                        formatted_element = format_unified_element(display_index, bbox, section_indent)
                        section_lines.append(f"{section_indent}{formatted_element}")
            
            output_sections.extend(section_lines)
    
    else:
        # Simple hierarchical view without viewport categories
        output_sections.append("🎯 PAGE ELEMENTS (Unified View):")
        
        # Group by semantic sections
        for section_name in ['header', 'nav', 'main', 'aside', 'footer', 'unsectioned']:
            section_elements = sections.get(section_name, [])
            if not section_elements:
                continue
            
            if section_name != 'unsectioned':
                output_sections.append(f"\n📍 {section_name.upper()} SECTION:")
                section_indent = "\t"
            else:
                section_indent = ""
            
            # Sort elements within section
            section_elements.sort(key=lambda x: (
                not x[1].isInteractive,  # Interactive elements first
                x[1].elementRole,
                getattr(x[1].hierarchy, 'depth', 0) if hasattr(x[1], 'hierarchy') and x[1].hierarchy else 0
            ))
            
            for index, bbox in section_elements:
                formatted_element = format_unified_element(index, bbox, section_indent)
                output_sections.append(f"{section_indent}{formatted_element}")
    
    # Add summary stats
    interactive_count = len([b for b in bboxes if b.isInteractive])
    content_count = len([b for b in bboxes if not b.isInteractive])
    
    stats = [
        f"\n📊 SUMMARY: {len(bboxes)} total elements",
        f"   • 🎯 Interactive: {interactive_count}",
        f"   • 📄 Content: {content_count}",
        f"   • 💡 Use bbox_id for interactive elements, extract_page_content() for full text"
    ]
    
    output_sections.extend(stats)
    
    return "\n".join(output_sections)


def format_enhanced_page_context(bboxes: List[BBox], markdown_content: str = "", frame_stats=None, viewport_categories: Dict[str, int] = None) -> str:
    """Format complete page context with enhanced bbox information and page content.
    
    Updated to use the new unified context approach while maintaining backward compatibility.
    """
    sections = []
    
    # Add page content overview if available
    if markdown_content:
        sections.append("📄 PAGE CONTENT OVERVIEW:")
        sections.append(markdown_content[:500] + ("..." if len(markdown_content) > 500 else ""))
        sections.append("")
    
    # Add frame statistics if available
    if frame_stats:
        sections.append("🖼️  FRAME ANALYSIS:")
        if hasattr(frame_stats, 'totalFrames'):
            sections.append(f"   • Total frames: {frame_stats.totalFrames}")
            sections.append(f"   • Accessible frames: {frame_stats.accessibleFrames}")
            sections.append(f"   • Maximum nesting depth: {frame_stats.maxDepth}")
        else:
            sections.append(f"   • Total frames: {frame_stats.get('totalFrames', 0)}")
            sections.append(f"   • Accessible frames: {frame_stats.get('accessibleFrames', 0)}")
            sections.append(f"   • Maximum nesting depth: {frame_stats.get('maxDepth', 0)}")
        sections.append("")
    
    # Add viewport distribution if available
    if viewport_categories:
        sections.append("📍 VIEWPORT DISTRIBUTION:")
        viewport_labels = {
            'in-viewport': '🟢 Current viewport',
            'above-viewport': '⬆️  Above viewport',
            'below-viewport': '⬇️  Below viewport',
            'left-of-viewport': '⬅️  Left of viewport',
            'right-of-viewport': '➡️  Right of viewport'
        }
        for position, count in viewport_categories.items():
            if count > 0:
                label = viewport_labels.get(position, position)
                sections.append(f"   • {label}: {count} elements")
        sections.append("")
    
    # Use new unified context by default, but maintain the enhanced structure
    unified_context = format_unified_context(bboxes, detail_level="full_hierarchy", include_viewport_context=True)
    sections.append(unified_context)
    
    return "\n".join(sections)


def format_tab_context(tabs: List[TabInfo], current_tab_index: int) -> str:
    """Format tab information into a human-readable context string."""
    if not tabs:
        return "Browser Tabs: No tabs available"
    
    tab_descriptions = ["📑 Browser Tabs:"]
    for tab in tabs:
        status = "🟢 [CURRENT]" if tab["is_active"] else "⚪"
        title = tab["title"]
        tab_descriptions.append(f"  {status} Tab [index={tab['tab_index']}]: {title}")
        # tab_descriptions.append(f"      URL: {tab['url']}")
    
    tab_descriptions.append(f"\nCurrently viewing Tab {current_tab_index}")
    tab_descriptions.append("💡 Use switch_tab(index) to change tabs (avoid list_tabs() unless you need full URLs)")
    
    return "\n".join(tab_descriptions)


def format_img_context(img_base64: str) -> dict:
    """Format a base64 image into a content block for multimodal models."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
    }


async def _annotate_pdf_page(page: Page) -> Annotation:
    """Process a PDF page to extract text and take a screenshot."""
    logger.info("DEBUG: PDF page detected. Extracting text content.")
    try:
        api_request_context = page.context.request
        response = await api_request_context.get(page.url)
        pdf_bytes = await response.body()

        # Extract text from PDF
        pdf_file = BytesIO(pdf_bytes)
        reader = pypdf.PdfReader(pdf_file)
        text = ""
        for p in reader.pages:
            text += p.extract_text() or ""

        # Truncate to the first 1000 words
        words = text.split()
        markdown = " ".join(words[:1000])+"...\n\n **Note:** This is a truncated version of the PDF content. Extract page content if you need the full text."

        screenshot = await page.screenshot()
        # Safely attempt cleanup only if injected scripts defined it
        await page.evaluate("typeof unmarkPage === 'function' && unmarkPage();")

        return Annotation(
            img=base64.b64encode(screenshot).decode(),
            bboxes=[],
            markdown=markdown,
            viewportCategories={},
            frameStats=FrameStats(totalFrames=0, accessibleFrames=0, maxDepth=0),
            totalElements=0
        )
    except Exception as e:
        logger.error(f"DEBUG: Failed to process PDF page: {e}")
        return Annotation(
            img="",
            bboxes=[],
            markdown=f"Failed to extract text from PDF at {page.url}. Error: {e}",
            viewportCategories={},
            frameStats=FrameStats(totalFrames=0, accessibleFrames=0, maxDepth=0),
            totalElements=0
        )

async def wait_until_stable(page: Page,
                            per_state_timeout_ms: int = 3000,
                            states: List[str] = ["load", "domcontentloaded"]):
    t0 = time.perf_counter()
    last_exc = None
    for state in states:
        try:
            await page.wait_for_load_state(state, timeout=per_state_timeout_ms)
            return state, int((time.perf_counter() - t0) * 1000), None
        except PWTimeout as e:
            last_exc = e
    return None, int((time.perf_counter() - t0) * 1000), last_exc

async def _annotate_html_page(page: Page) -> Annotation:
    """Annotate an HTML page with bounding boxes and take a screenshot."""
    # await asyncio.sleep(0.5)  # wait for half second
    markdown = ""
    state, elapsed_ms, err = await wait_until_stable(page)
    if state:
        markdown = f"Page stabilized at '{state}' in {elapsed_ms} ms."
    else:
        markdown = f"WARNING: No stable load state reached after {elapsed_ms} ms. Proceeding anyway. Last error: {err}"
    
    try:
        await page.evaluate(mark_page_script)
        for _ in range(10):
            try:
                mark_result = await page.evaluate("markPage()")
                break
            except Exception:
                logger.warning("DEBUG: Marking page failed. Retrying...")
                await asyncio.sleep(0.5)
        else:
            mark_result = {"coordinates": [], "viewportCategories": {}, "frameStats": {"totalFrames": 0, "accessibleFrames": 0, "maxDepth": 0}}

        # Extract the coordinates (bboxes) from the enhanced result
        bboxes = mark_result.get("coordinates", []) if isinstance(mark_result, dict) else mark_result or []
        viewport_categories_raw = mark_result.get("viewportCategories", {}) if isinstance(mark_result, dict) else {}
        frame_stats_dict = mark_result.get("frameStats", {"totalFrames": 0, "accessibleFrames": 0, "maxDepth": 0}) if isinstance(mark_result, dict) else {"totalFrames": 0, "accessibleFrames": 0, "maxDepth": 0}
        frame_stats = FrameStats(**frame_stats_dict)
        
        # Convert viewport categories to counts
        viewport_categories = {
            position: len(elements) for position, elements in viewport_categories_raw.items()
        } if viewport_categories_raw else {}

        
        screenshot = await page.screenshot()

        return Annotation(
            img=base64.b64encode(screenshot).decode(),
            bboxes=bboxes,
            markdown=markdown,
            viewportCategories=viewport_categories,
            frameStats=frame_stats,
            totalElements=len(bboxes)
        )
    except Exception as e:
        logger.error(f"DEBUG: Failed to annotate page after stabilizing: {e}")
        return Annotation(
            img="",
            bboxes=[],
            markdown=f"Failed to annotate page. Error: {e}",
            viewportCategories={},
            frameStats=FrameStats(totalFrames=0, accessibleFrames=0, maxDepth=0),
            totalElements=0
        )


async def annotate_page(page: Page) -> Annotation:
    """Annotate the page with bounding boxes and take a screenshot."""
    try:
        content = await page.content()
        if 'type="application/pdf"' in content or 'class="pdf' in content:
            return await _annotate_pdf_page(page)
    except Exception as e:
        logger.error(
            "DEBUG: Could not get page content to check for PDF, "
            f"proceeding with normal annotation. Error: {e}"
        )

    return await _annotate_html_page(page)