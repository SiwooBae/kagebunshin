"""Utility functions for KageBunshinV2 system"""
from datetime import datetime
from typing import List, Dict
import secrets
import petname
import logging
import html2text
from bs4 import BeautifulSoup
from .models import BBox, Annotation, FrameStats, TabInfo
import os
from io import BytesIO
from playwright.async_api import Page
import base64
import pypdf
import asyncio
import logging

# Suppress logging warnings
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def log_with_timestamp(message: str) -> None:
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Load the JavaScript to mark the page
with open(os.path.join(current_dir, "mark_page.js")) as f:
    mark_page_script = f.read()


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

        # Truncate to 5000 words as requested
        words = text.split()
        markdown = " ".join(words[:5000])

        screenshot = await page.screenshot()
        await page.evaluate("unmarkPage()")

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


async def _annotate_html_page(page: Page) -> Annotation:
    """Annotate an HTML page with bounding boxes and take a screenshot."""
    # await asyncio.sleep(0.5)  # wait for half second

    try:
        await page.wait_for_load_state("networkidle", timeout=3000)
    except Exception as e:
        logger.warning(f"DEBUG: 'networkidle' failed: {e}. Trying 'load' state.")
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except Exception as e2:
            logger.warning(f"DEBUG: Both 'networkidle' and 'load' failed: {e2}")
            return Annotation(
                img="",
                bboxes=[],
                markdown=f"Failed to stabilize page load. Error: {e2}",
                viewportCategories={},
                frameStats={"totalFrames": 0, "accessibleFrames": 0, "maxDepth": 0},
                totalElements=0
            )
    
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

        markdown = ""
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


def format_text_context(markdown_content: str) -> str:
    """Format markdown text into a human-readable context string."""
    return f"Page Content (Markdown):\n\n{markdown_content}"


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
        captcha_indicator = " [CAPTCHA]" if bbox.isCaptcha else ""
        
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
        
        main_content = f'{hierarchy_info}bbox_id: {index} (<{el_type}/>{captcha_indicator}): "{text}"{frame_info}'
        
        # Add children information if available
        children_info = ""
        if include_hierarchy and hasattr(bbox, 'hierarchy') and bbox.hierarchy:
            hierarchy = bbox.hierarchy
            if hasattr(hierarchy, 'interactiveChildrenCount') and hierarchy.interactiveChildrenCount > 0:
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


def format_enhanced_page_context(bboxes: List[BBox], markdown_content: str = "", frame_stats=None, viewport_categories: Dict[str, int] = None) -> str:
    """Format complete page context with enhanced bbox information and page content."""
    sections = []
    
    # Add page content if available
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
    
    # Add enhanced bbox context
    sections.append("🎯 INTERACTIVE ELEMENTS:")
    bbox_context = format_bbox_context(bboxes, include_hierarchy=True, include_viewport_context=True)
    sections.append(bbox_context)
    
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
    tab_descriptions.append("💡 Use list_tabs() to see detailed tab information or switch_tab(index) to change tabs")
    
    return "\n".join(tab_descriptions)


def format_img_context(img_base64: str) -> dict:
    """Format a base64 image into a content block for multimodal models."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
    }

# =============================
# Agent identity helpers
# =============================
_ASSIGNED_AGENT_NAMES: set[str] = set()


def generate_agent_name() -> str:
    """Generate a likely-unique, human-friendly agent name.

    Uses petname plus a short random suffix to avoid collisions, and ensures
    uniqueness within the current process.
    """
    for _ in range(100):
        base = petname.generate(2, separator="-")
        # suffix = secrets.token_hex(2)  # 4 hex chars
        # candidate = f"{base}-{suffix}"
        candidate = base
        if candidate not in _ASSIGNED_AGENT_NAMES:
            _ASSIGNED_AGENT_NAMES.add(candidate)
            return candidate
    # Fallback: extremely unlikely to hit
    fallback = f"agent-{secrets.token_hex(4)}"
    _ASSIGNED_AGENT_NAMES.add(fallback)
    return fallback