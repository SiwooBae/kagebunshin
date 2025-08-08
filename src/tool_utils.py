"""Toolbelt for WebVoyagerV2 system"""
import asyncio
import base64
import logging
import os
import random
import platform
from typing import List, Optional, Dict, Any

from playwright.async_api import Page, BrowserContext
from langchain_core.tools import tool
import pypdf
from io import BytesIO

from .config import ACTIVATE_HUMAN_BEHAVIOR
from .human_behavior import (
    smart_delay_between_actions,
    get_random_offset_in_bbox,
    human_mouse_move,
    human_delay,
    human_type_text,
    human_scroll,
    calculate_reading_time
)
from .models import BBox, TabInfo, Annotation, FrameStats
from .utils import html_to_markdown

logger = logging.getLogger(__name__)

# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Load the JavaScript to mark the page
with open(os.path.join(current_dir, "mark_page.js")) as f:
    mark_page_script = f.read()


async def _process_pdf_page(page: Page) -> Annotation:
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
    await asyncio.sleep(1)  # wait for one second

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
    
    # Just use load state; it is faster

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

        page_html = await page.content()
        # markdown = html_to_markdown(page_html)
        markdown = ""
        screenshot = await page.screenshot()
        await page.evaluate("unmarkPage()")

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
            return await _process_pdf_page(page)
    except Exception as e:
        logger.error(
            "DEBUG: Could not get page content to check for PDF, "
            f"proceeding with normal annotation. Error: {e}"
        )

    return await _annotate_html_page(page)