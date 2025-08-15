"""
WebVoyager State Manager - Stateless manager that operates on WebVoyagerState.
"""
import asyncio
import base64
import logging
import time
import hashlib
import platform
from typing import Dict, Any, List, Optional, Tuple

from bs4 import BeautifulSoup
from langchain.chat_models.base import init_chat_model
from langchain_core.tools import tool
from playwright.async_api import Page, BrowserContext

from .models import WebVoyagerState, BBox, TabInfo, Annotation
from .utils import html_to_markdown, annotate_page
from .human_behavior import (
    smart_delay_between_actions,
    human_delay,
    get_random_offset_in_bbox,
    human_mouse_move,
    human_type_text,
    human_scroll,
)
from .fingerprint_evasion import apply_fingerprint_profile
from .config import SUMMARIZER_MODEL, SUMMARIZER_PROVIDER
logger = logging.getLogger(__name__)


class WebVoyagerStateManager:
    """
    Stateless state manager that operates on WebVoyagerState.
    
    This class provides tools and operations but doesn't maintain any state itself.
    All browser state comes from the WebVoyagerState passed to methods.
    All derived data (screenshots, bboxes, etc.) is computed fresh on-demand.
    """

    def __init__(self, context: BrowserContext): 
        """Initialize the stateless state manager."""
        self.current_state = WebVoyagerState(
            input="",
            messages=[],
            context=context
        )
        # Current page data (derived from state)
        self.current_bboxes: List[BBox] = []
        self._action_count: int = 0
        self.prev_snapshot: Optional[Annotation] = None
        self.current_page_index: int = 0
        # Lightweight summarizer LLM for cheap text summaries
        try:
            self.summarizer_llm = init_chat_model(
                model=SUMMARIZER_MODEL,
                model_provider=SUMMARIZER_PROVIDER,
            )
        except Exception:
            self.summarizer_llm = None
        
    @classmethod
    async def create(cls, context: BrowserContext):
        """Factory method to create a WebVoyagerStateManager with async initialization."""
        # if there is no page in the context, create a new one
        if len(context.pages) == 0:
            page = await context.new_page()
            await apply_fingerprint_profile(page)
            await page.goto("https://www.google.com")
        
        # Create instance using regular __init__
        instance = cls(context)
        return instance

    # ===========================================
    # STATE MANAGEMENT METHODS
    # ===========================================

    def set_state(self, state: WebVoyagerState) -> None: 
        """Set the current state to operate on."""
        self.current_state = state
        self.current_bboxes = []  # Reset derived data
        
    def get_current_page(self) -> Page:
        """Get the current active page from state."""
        if not self.current_state:
            raise ValueError("No state set. Call set_state first.")
        
        pages = self.current_state["context"].pages
        current_index = self.current_page_index
        if current_index >= len(pages):
            raise ValueError(f"Invalid page index: {current_index}. Valid range: 0-{len(pages)-1}")
        return pages[current_index]

    def get_context(self) -> BrowserContext:
        """Get the browser context from state."""
        if not self.current_state:
            raise ValueError("No state set. Call set_state first.")
        return self.current_state["context"]

    def increment_action_count(self) -> None:
        """Increment the action count."""
        self._action_count += 1

    # ===========================================
    # PROPERTY GETTERS FOR DERIVED STATE
    # ===========================================

    @property
    def num_actions_done(self) -> int:
        """Get the current action count."""
        return self._action_count

    @property
    def bboxes(self) -> List[BBox]:
        """Get the current page's bounding boxes."""
        return self.current_bboxes.copy()

    async def get_current_page_data(self) -> Annotation:
        """Get current page data (screenshot, bboxes, markdown) fresh."""
        if not self.current_state:
            raise ValueError("No state set. Call set_state first.")
        
        page = self.get_current_page()
        annotation = await annotate_page(page)
        self.prev_snapshot = annotation
        # Update current bboxes
        self.current_bboxes = annotation.bboxes
        
        return annotation

    async def get_tabs(self) -> List[TabInfo]:
        """Get current tab information."""
        if not self.current_state:
            raise ValueError("No state set. Call set_state first.")
            
        tab_info = []
        context = self.current_state["context"]
        current_page = self.get_current_page()
        
        for i, page in enumerate(context.pages):
            try:
                title = await page.title()
                url = page.url
                is_active = (page == current_page)
                
                tab_info.append(TabInfo(
                    page=page,
                    tab_index=i,
                    title=title,
                    url=url,
                    is_active=is_active
                ))
            except Exception as e:
                logger.warning(f"Could not get info for tab {i}: {e}")
                
        return tab_info

    async def get_current_tab_index(self) -> int:
        """Get the index of the currently active tab."""
        if not self.current_state:
            raise ValueError("No state set. Call set_state first.")
        return self.current_page_index

    # ===========================================
    # HELPER METHODS
    # ===========================================

    def _get_bbox_by_id(self, bbox_id: int) -> Optional[BBox]:
        """Get a bounding box by its ID."""
        if 0 <= bbox_id < len(self.current_bboxes):
            return self.current_bboxes[bbox_id]
        return None

    def _get_selector(self, bbox_id: int) -> str:
        """Get CSS selector for a bbox ID."""
        bbox = self._get_bbox_by_id(bbox_id)
        if not bbox:
            raise ValueError(f"Invalid bbox_id: {bbox_id}. Valid range: 0-{len(self.current_bboxes)-1}")
        if bbox.isCaptcha:
            raise ValueError(f"Action failed: Element {bbox_id} is identified as a CAPTCHA.")
        try:
            selector = getattr(bbox, "selector", None)
            if selector:
                return selector
        except Exception:
            pass
        return f'[data-ai-label="{bbox_id}"]'


    def _update_current_page_in_state(self, new_page: Page) -> None:
        """Update the current page index in state when switching tabs."""
        if not self.current_state:
            return
            
        context = self.current_state["context"]
        for i, page in enumerate(context.pages):
            if page == new_page:
                self.current_page_index = i
                break

    async def _check_for_new_tabs(self, before_pages: List[Page]) -> None:
        """Checks for new tabs after an action, and if found, switches to the newest one."""
        after_pages = self.get_context().pages
        if len(after_pages) > len(before_pages):
            new_pages = set(after_pages) - set(before_pages)
            if new_pages:
                # When multiple tabs are opened, this just picks one.
                # This is a reasonable assumption for most web interactions.
                new_page = new_pages.pop()
                await new_page.bring_to_front()
                self._update_current_page_in_state(new_page)
                logger.info(f"Detected a new tab. Switched to tab index {self.current_page_index}.")

    # ===========================================
    # HYBRID ACTION EXECUTION
    # ===========================================

    async def _capture_page_state(self) -> Tuple[str, str, int]:
        """Captures the current page state (URL, DOM hash, and tab count) for verification."""
        page = self.get_current_page()
        context = self.get_context()
        num_tabs = len(context.pages)
        url = page.url
        try:
            content = await page.content()
            dom_hash = hashlib.sha256(content.encode()).hexdigest()
        except Exception:
            # Fallback if page content is not available
            dom_hash = hashlib.sha256(str(time.time()).encode()).hexdigest()
        return url, dom_hash, num_tabs

    # --- Native Actions (Fast, Playwright-based) ---

    async def _click_native(self, bbox_id: int) -> None:
        """Click on an element using Playwright's native click."""
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        await page.click(selector, timeout=5000)

    async def _type_text_native(self, bbox_id: int, text_content: str) -> None:
        """Type text using Playwright's native fill and press."""
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        await page.fill(selector, text_content, timeout=5000)
        await page.keyboard.press("Enter")

    async def _select_option_native(self, bbox_id: int, values: List[str]) -> None:
        """Select an option using Playwright's native select_option."""
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        await page.select_option(selector, values, timeout=5000)

    # --- Human-like Actions (Slower, More Robust) ---

    async def _click_human_like(self, bbox_id: int) -> None:
        """Click on an element using human-like mouse movements."""
        bbox = self._get_bbox_by_id(bbox_id)
        if not bbox:
            raise ValueError(f"Invalid bbox_id {bbox_id}")

        page = self.get_current_page()
        current_pos = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
        start_x, start_y = current_pos.get("x", 0), current_pos.get("y", 0)
        x, y = get_random_offset_in_bbox(bbox)
        
        await smart_delay_between_actions("click")
        await human_mouse_move(page, start_x, start_y, x, y)
        await human_delay(50, 200)
        await page.mouse.click(x, y)

    async def _type_text_human_like(self, bbox_id: int, text_content: str) -> None:
        """Type text using human-like delays and keystrokes."""
        bbox = self._get_bbox_by_id(bbox_id)
        if not bbox:
            raise ValueError(f"Invalid bbox_id {bbox_id}")

        page = self.get_current_page()
        x, y = get_random_offset_in_bbox(bbox)
        
        await smart_delay_between_actions("type")
        current_pos = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
        start_x, start_y = current_pos.get("x", 0), current_pos.get("y", 0)
        
        await human_mouse_move(page, start_x, start_y, x, y)
        await page.mouse.click(x, y)
        await human_delay(100, 300)
        
        select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
        await page.keyboard.press(select_all)
        await human_delay(50, 150)
        await page.keyboard.press("Backspace")
        await human_delay(100, 200)
        
        await human_type_text(page, text_content)
        await human_delay(200, 600)
        await page.keyboard.press("Enter")

    async def _select_option_human_like(self, bbox_id: int, values: List[str]) -> None:
        """Select an option with human-like mouse movement and delays."""
        bbox = self._get_bbox_by_id(bbox_id)
        if not bbox:
            raise ValueError(f"Invalid bbox_id {bbox_id}")
        
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        
        await smart_delay_between_actions("click")
        
        x, y = get_random_offset_in_bbox(bbox)
        current_pos = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
        start_x, start_y = current_pos.get("x", 0), current_pos.get("y", 0)
        
        await human_mouse_move(page, start_x, start_y, x, y)
        await human_delay(100, 300)
        
        await page.select_option(selector, values)
        await human_delay(200, 500)

    # ===========================================
    # BROWSER INTERACTION TOOL METHODS
    # ===========================================

    async def click(self, bbox_id: int) -> str:
        """
        Clicks on an element. Tries a fast native click first, then falls back
        to a human-like click if the native click fails or has no effect.
        Also detects and switches to new tabs if they are opened by the click.
        """
        logger.info(f"Attempting to click element with bbox_id: {bbox_id}")
        before_pages = self.get_context().pages
        before_state = await self._capture_page_state()

        try:
            # Attempt 1: Native Playwright click (fast)
            logger.info("Attempting native click...")
            await self._click_native(bbox_id)
            await asyncio.sleep(1)  # Wait for page to update
            after_state = await self._capture_page_state()

            if before_state != after_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Native click on bbox_id {bbox_id} successful and caused a page change.")
                return f"Successfully clicked element {bbox_id}."
            
            logger.warning(f"Native click on bbox_id {bbox_id} had no effect. Falling back.")

        except Exception as e:
            logger.warning(f"Native click failed for bbox_id {bbox_id}: {e}. Falling back.")

        # Attempt 2: Human-like fallback
        try:
            logger.info("Attempting human-like click...")
            await self._click_human_like(bbox_id)
            await asyncio.sleep(1)  # Wait for page to update
            final_state = await self._capture_page_state()

            if before_state != final_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Human-like fallback click on bbox_id {bbox_id} successful.")
                return f"Successfully clicked element {bbox_id} using fallback."
            else:
                logger.error(f"All click attempts on bbox_id {bbox_id} failed to change the page state.")
                return f"Error: Clicking element {bbox_id} had no effect on the page."

        except Exception as e:
            logger.error(f"Human-like fallback click also failed for bbox_id {bbox_id}: {e}")
            return f"Error: All click attempts failed for element {bbox_id}. Last error: {e}"

    async def type_text(self, bbox_id: int, text_content: str) -> str:
        """
        Types text into an element. Tries a fast native type first, then falls back
        to a human-like method if the native type fails or has no effect.
        Also detects and switches to new tabs if they are opened by the action.
        """
        logger.info(f"Attempting to type '{text_content}' into element with bbox_id: {bbox_id}")
        before_pages = self.get_context().pages
        before_state = await self._capture_page_state()

        try:
            # Attempt 1: Native Playwright type (fast)
            logger.info("Attempting native type...")
            await self._type_text_native(bbox_id, text_content)
            await asyncio.sleep(1)
            after_state = await self._capture_page_state()

            if before_state != after_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Native type on bbox_id {bbox_id} successful.")
                return f"Successfully typed '{text_content}' into element {bbox_id}."
            
            logger.warning(f"Native type on bbox_id {bbox_id} had no effect. Falling back.")

        except Exception as e:
            logger.warning(f"Native type failed for bbox_id {bbox_id}: {e}. Falling back.")

        # Attempt 2: Human-like fallback
        try:
            logger.info("Attempting human-like type...")
            await self._type_text_human_like(bbox_id, text_content)
            await asyncio.sleep(1)
            final_state = await self._capture_page_state()

            if before_state != final_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Human-like fallback type on bbox_id {bbox_id} successful.")
                return f"Successfully typed '{text_content}' into element {bbox_id} using fallback."
            else:
                logger.error(f"All type attempts on bbox_id {bbox_id} failed to change the page state.")
                return f"Error: Typing into element {bbox_id} had no effect on the page."

        except Exception as e:
            logger.error(f"Human-like fallback type also failed for bbox_id {bbox_id}: {e}")
            return f"Error: All type attempts failed for element {bbox_id}. Last error: {e}"

    async def browser_select_option(self, bbox_id: int, values: List[str]) -> str:
        """
        Selects an option in a dropdown. Tries a fast native select first, then falls back
        to a human-like method if the native select fails or has no effect.
        Also detects and switches to new tabs if they are opened by the action.
        """
        logger.info(f"Attempting to select {values} in element with bbox_id: {bbox_id}")
        before_pages = self.get_context().pages
        before_state = await self._capture_page_state()

        try:
            # Attempt 1: Native Playwright select (fast)
            logger.info("Attempting native select...")
            await self._select_option_native(bbox_id, values)
            await asyncio.sleep(1)
            after_state = await self._capture_page_state()

            if before_state != after_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Native select on bbox_id {bbox_id} successful.")
                return f"Successfully selected {values} in element {bbox_id}."
            
            logger.warning(f"Native select on bbox_id {bbox_id} had no effect. Falling back.")

        except Exception as e:
            logger.warning(f"Native select failed for bbox_id {bbox_id}: {e}. Falling back.")

        # Attempt 2: Human-like fallback
        try:
            logger.info("Attempting human-like select...")
            await self._select_option_human_like(bbox_id, values)
            await asyncio.sleep(1)
            final_state = await self._capture_page_state()

            if before_state != final_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Human-like fallback select on bbox_id {bbox_id} successful.")
                return f"Successfully selected {values} in element {bbox_id} using fallback."
            else:
                logger.error(f"All select attempts on bbox_id {bbox_id} failed to change the page state.")
                return f"Error: Selecting in element {bbox_id} had no effect on the page."

        except Exception as e:
            logger.error(f"Human-like fallback select also failed for bbox_id {bbox_id}: {e}")
            return f"Error: All select attempts failed for element {bbox_id}. Last error: {e}"

    async def scroll(self, target: str, direction: str) -> str:
        """Scroll the page or an element."""
        try:
            direction = direction.lower()
            if direction not in ["up", "down"]:
                return "Error: Direction must be 'up' or 'down'"

            page = self.get_current_page()
            await smart_delay_between_actions("scroll")
            
            if target.lower() == "page":
                # Scroll the entire page
                scroll_amount = 500
                await human_scroll(page, 0, 0, direction, scroll_amount)
            else:
                # Try to parse target as bbox_id
                try:
                    bbox_id = int(target)
                    bbox = self._get_bbox_by_id(bbox_id)
                    if not bbox:
                        return f"Error: Invalid bbox_id {bbox_id}"
                    
                    selector = self._get_selector(bbox_id)
                    element = await page.query_selector(selector)
                    if element:
                        element_box = await element.bounding_box()
                        if element_box:
                            scroll_amount = 200
                            await human_scroll(page, element_box['x'], element_box['y'], direction, scroll_amount)
                        else:
                            return f"Error: Could not get bounding box for element {bbox_id}"
                    else:
                        return f"Error: Element with bbox_id {bbox_id} not found"
                except ValueError:
                    return f"Error: Invalid target '{target}'. Use 'page' or a bbox_id number"

            self.increment_action_count()
            
            # Wait for scroll to complete
            await asyncio.sleep(0.3)
            
            return f"Successfully scrolled {direction}"
            
        except Exception as e:
            logger.error(f"Error scrolling: {e}")
            return f"Error scrolling: {str(e)}"

    async def refresh(self) -> str:
        """Refresh the current page."""
        try:
            page = self.get_current_page()
            await page.reload()
            self.increment_action_count()
            await asyncio.sleep(1)  # Wait for reload to settle
            return "Successfully refreshed the page."
        except Exception as e:
            logger.error(f"Error refreshing page: {e}")
            return f"Error refreshing page: {str(e)}"

    async def extract_page_content(self) -> str:
        """Return full visible page content as Markdown, plus a DOM outline, and an optional LLM-parsed Markdown.

        Designed to preserve content so LLMs can "read" articles and long text without hallucinating.
        """
        try:
            page = self.get_current_page()
            url = page.url
            title = await page.title()
            html_content = await page.content()
            
            # Build a full cleaned Markdown representation of the visible HTML
            cleaned_markdown = html_to_markdown(html_content)

            # summary_text = ""
            # if self.summarizer_llm is not None:
            #     try:
            #         prompt = (
            #             "You are a faithful HTML-to-Markdown converter. Given the page's cleaned Markdown text, "
            #             "produce a high-fidelity Markdown of the page content. "
            #             "Preserve headings, paragraphs, lists, tables, code blocks, and hyperlinks. Do not invent content. "
            #             "Prefer the provided cleaned Markdown text over the outline when in doubt."
            #         )
            #         # Cap lengths to keep within budget for the cheap model
            #         # max_clean_md = 12000
            #         # max_outline = 6000
            #         cleaned_md_snippet = cleaned_markdown
            #         dom_snippet = dom_outline
            #         messages = [
            #             SystemMessage(content=prompt),
            #             HumanMessage(content=(
            #                 f"URL: {url}\nTitle: {title}\n\n"
            #                 f"Cleaned Markdown (truncated):\n{cleaned_md_snippet}\n\n"
            #                 # f"DOM Outline (truncated):\n{dom_snippet}\n\n"
            #                 f"Output the final Markdown only."
            #             )),
            #         ]
            #         summary_response = await self.summarizer_llm.ainvoke(messages)
            #         summary_text = str(getattr(summary_response, "content", "")).strip()
            #     except Exception as e:
            #         logger.warning(f"Summarizer failed, returning DOM only: {e}")
            output = f"URL: {url}\nTitle: {title}\n\n{cleaned_markdown}"
            return output

        except Exception as e:
            logger.error(f"Error extracting page content: {e}")
            return f"Error extracting page content: {str(e)}"

    def _build_dom_outline(self, html_content: str, max_depth: int = 4, max_nodes: int = 800) -> str:
        """Create a human-readable DOM outline from raw HTML.

        - Skips non-content tags like script/style/meta/link/svg
        - Shows tag, id, limited classes, and a short text snippet
        - Limits depth and total nodes to keep size reasonable
        """
        soup = BeautifulSoup(html_content or "", "html.parser")
        root = soup.body or soup

        ignored_tags = {"script", "style", "meta", "link", "noscript", "svg", "path"}
        lines: List[str] = []
        nodes_seen = 0

        def text_snippet(node_text: str, limit: int = 80) -> str:
            text = (node_text or "").strip()
            text = " ".join(text.split())
            return (text[:limit] + "…") if len(text) > limit else text

        def format_tag(node) -> str:
            tag = node.name
            id_attr = node.get("id")
            class_attr = node.get("class") or []
            class_part = ("." + ".".join(class_attr[:2])) if class_attr else ""
            id_part = f"#{id_attr}" if id_attr else ""
            return f"<{tag}{id_part}{class_part}>"

        def walk(node, depth: int) -> None:
            nonlocal nodes_seen
            if nodes_seen >= max_nodes or depth > max_depth:
                return
            # Skip strings-only nodes here; bs4 exposes text via .strings when needed
            if getattr(node, "name", None) is None:
                return
            if node.name in ignored_tags:
                return

            indent = "  " * depth
            # Record the element line
            lines.append(f"{indent}{format_tag(node)}")
            nodes_seen += 1
            if nodes_seen >= max_nodes:
                return

            # Include a short text snippet for this node (visible text only)
            direct_texts = [t for t in node.find_all(string=True, recursive=False) if t and t.strip()]
            if direct_texts:
                snippet = text_snippet(" ".join(direct_texts))
                if snippet:
                    lines.append(f"{indent}  └─ text: {snippet}")

            # Recurse into children
            for child in getattr(node, "children", []) or []:
                if nodes_seen >= max_nodes:
                    break
                if getattr(child, "name", None) is None:
                    # For bare strings nested among children, add a short line
                    snippet = text_snippet(str(child))
                    if snippet:
                        lines.append(f"{indent}  └─ text: {snippet}")
                        nodes_seen += 1
                        if nodes_seen >= max_nodes:
                            break
                    continue
                walk(child, depth + 1)

        # Start from body or document root children to avoid duplicating the whole soup
        start_nodes = list(getattr(root, "children", [])) or [root]
        for child in start_nodes:
            if nodes_seen >= max_nodes:
                break
            if getattr(child, "name", None) is None:
                continue
            walk(child, 0)

        if nodes_seen >= max_nodes:
            lines.append("… (truncated) …")
        return "\n".join(lines)

    async def go_back(self) -> str:
        """Navigate back in browser history."""
        try:
            page = self.get_current_page()
            await smart_delay_between_actions("navigate")
            await page.go_back()
            self.increment_action_count()
            
            # Wait for navigation to complete
            await asyncio.sleep(1)
            
            return "Successfully navigated back"
            
        except Exception as e:
            logger.error(f"Error going back: {e}")
            return f"Error going back: {str(e)}"

    async def browser_goto(self, url: str) -> str:
        """Navigate to a specific URL."""
        try:
            if not url.startswith(("http://", "https://")):
                url = 'https://' + url
                
            page = self.get_current_page()
            await smart_delay_between_actions("navigate")
            await page.goto(url)
            self.increment_action_count()
            
            # Wait for page to load
            await asyncio.sleep(2)
            
            return f"Successfully navigated to {url}"
            
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            return f"Error navigating to {url}: {str(e)}"

    async def go_forward(self) -> str:
        """Navigate forward in browser history."""
        try:
            page = self.get_current_page()
            await smart_delay_between_actions("navigate")
            await page.go_forward()
            self.increment_action_count()
            await asyncio.sleep(1)
            return "Successfully navigated forward"
        except Exception as e:
            logger.error(f"Error going forward: {e}")
            return f"Error going forward: {str(e)}"

    async def hover(self, bbox_id: int) -> str:
        """Hover over an element identified by its bounding box ID."""
        try:
            selector = self._get_selector(bbox_id)
            page = self.get_current_page()
            await page.hover(selector, timeout=5000)
            self.increment_action_count()
            return f"Hovered over element {bbox_id}."
        except Exception as e:
            logger.error(f"Error hovering over element {bbox_id}: {e}")
            return f"Error hovering over element {bbox_id}: {str(e)}"

    async def press_key(self, key: str) -> str:
        """Press a keyboard key."""
        try:
            page = self.get_current_page()
            await page.keyboard.press(key)
            self.increment_action_count()
            return f"Pressed key '{key}'."
        except Exception as e:
            logger.error(f"Error pressing key '{key}': {e}")
            return f"Error pressing key '{key}': {str(e)}"

    async def drag(self, start_bbox_id: int, end_bbox_id: int) -> str:
        """Perform drag and drop between two elements."""
        try:
            start_selector = self._get_selector(start_bbox_id)
            end_selector = self._get_selector(end_bbox_id)
            page = self.get_current_page()
            await page.drag_and_drop(start_selector, end_selector)
            self.increment_action_count()
            return f"Dragged element {start_bbox_id} to element {end_bbox_id}."
        except Exception as e:
            logger.error(f"Error dragging from {start_bbox_id} to {end_bbox_id}: {e}")
            return f"Error dragging from {start_bbox_id} to {end_bbox_id}: {str(e)}"

    async def wait_for(
        self,
        time: Optional[float] = None,
        bbox_id: Optional[int] = None,
        state: str = "attached",
    ) -> str:
        """Wait for a specified condition or time to pass."""
        try:
            page = self.get_current_page()
            if time is not None:
                if time > 20:
                    return "Error: Time cannot be greater than 20 seconds"
                if time < 0:
                    return "Error: Time cannot be negative"
                
                await page.wait_for_timeout(int(time * 1000))
                return f"Waited for {time} seconds."

            if bbox_id is not None:
                if state not in ["attached", "detached"]:
                    return "Error: state must be 'attached' or 'detached'"
                
                selector = self._get_selector(bbox_id)
                await page.wait_for_selector(selector, state=state, timeout=5000) # wait for 5 seconds max
                
                state_verb = "appear" if state == "attached" else "disappear"
                return f"Waited for element {bbox_id} to {state_verb}."

            return "No wait condition provided."
        except Exception as e:
            logger.error(f"Error in wait_for: {e}")
            return f"Error in wait_for: {str(e)}"

    # ===========================================
    # TAB MANAGEMENT METHODS
    # ===========================================

    async def list_tabs(self) -> str:
        """List all open browser tabs."""
        try:
            tabs = await self.get_tabs()
            
            if not tabs:
                return "No tabs found."
            
            tab_list = ["Available tabs:"]
            for tab in tabs:
                status = " (ACTIVE)" if tab["is_active"] else ""
                tab_list.append(f"  {tab['tab_index']}: {tab['title'][:50]} - {tab['url'][:60]}{status}")
            
            return "\n".join(tab_list)
            
        except Exception as e:
            logger.error(f"Error listing tabs: {e}")
            return f"Error listing tabs: {str(e)}"

    async def switch_tab(self, tab_index: int) -> str:
        """Switch to a specific tab by index."""
        try:
            context = self.get_context()
            pages = context.pages
            
            if not (0 <= tab_index < len(pages)):
                return f"Error: Invalid tab index {tab_index}. Available tabs: 0-{len(pages)-1}"
            
            target_page = pages[tab_index]
            await target_page.bring_to_front()
            
            title = await target_page.title()
            self.increment_action_count()
            self.current_page_index = tab_index
            return f"Successfully switched to tab {tab_index}: {title}"
            
        except Exception as e:
            logger.error(f"Error switching to tab {tab_index}: {e}")
            return f"Error switching to tab {tab_index}: {str(e)}"

    async def open_new_tab(self, url: Optional[str] = None) -> str:
        """Open a new browser tab."""
        try:
            context = self.get_context()
            new_page = await context.new_page()
            
            if url:
                if not url.startswith(("http://", "https://")):
                    url = 'https://' + url
                await new_page.goto(url)
            
            await new_page.bring_to_front()
            
            # Update current page index in state to point to new tab
            self.current_page_index = len(context.pages) - 1
            self.increment_action_count()
            
            tab_info = f"new tab (index {len(context.pages) - 1})"
            if url:
                tab_info += f" and navigated to {url}"
            
            return f"Successfully opened {tab_info}"
            
        except Exception as e:
            logger.error(f"Error opening new tab: {e}")
            return f"Error opening new tab: {str(e)}"

    async def close_tab(self, tab_index: Optional[int] = None) -> str:
        """Close a browser tab."""
        try:
            context = self.get_context()
            pages = context.pages
            
            if len(pages) <= 1:
                return "Error: Cannot close the last remaining tab."
            
            if tab_index is None:
                # Close current tab
                tab_index = self.current_page_index
            else:
                if not (0 <= tab_index < len(pages)):
                    return f"Error: Invalid tab index {tab_index}. Available tabs: 0-{len(pages)-1}"
            
            page_to_close = pages[tab_index]
            title = await page_to_close.title()
            
            await page_to_close.close()
            
            # If we closed the current page, switch to another one
            if tab_index == self.current_page_index:
                # Switch to first available tab
                remaining_pages = [p for p in context.pages if p != page_to_close]
                if remaining_pages:
                    new_current = remaining_pages[0]
                    await new_current.bring_to_front()
                    self.current_page_index = 0
            
            self.increment_action_count()
            
            return f"Successfully closed tab {tab_index}: {title}"
            
        except Exception as e:
            logger.error(f"Error closing tab: {e}")
            return f"Error closing tab: {str(e)}"

    # ===========================================
    # REASONING AND COMMUNICATION METHODS
    # ===========================================

    def take_note(self, note: str) -> str:
        """Take a note for future reference."""
        logger.info(f"Agent note: {note}")
        return f"Note recorded: {note}"
    
    # ===========================================
    # TOOL CREATION FOR LLM BINDING
    # ===========================================

    def get_tools_for_llm(self):
        """Returns a list of tools that can be bound to the LLM."""
        
        @tool
        async def click(bbox_id: int) -> str:
            """Click on an interactive element identified by its bounding box ID. Use this to click buttons, links, form elements, or any clickable element on the page.

            Args:
                bbox_id (int): The ID number of the bounding box element to click (from the page annotation).
            """
            return await self.click(bbox_id)

        @tool
        async def type_text(bbox_id: int, text_content: str) -> str:
            """Type text into an input field, textarea, or other text input element identified by its bounding box ID.

            Args:
                bbox_id (int): The ID number of the input element to type into.
                text_content (str): The text to type into the element.
            """
            return await self.type_text(bbox_id, text_content)

        @tool
        async def scroll(target: str, direction: str) -> str:
            """Scroll the page or a specific element up or down to reveal more content.

            Args:
                target (str): Either "page" to scroll the entire page, or a bbox_id number to scroll within a specific element.
                direction (str): "up" or "down" to specify scroll direction.
            """
            return await self.scroll(target, direction)

        @tool
        async def refresh() -> str:
            """Refresh the current browser page to get the latest content."""
            return await self.refresh()

        @tool
        async def extract_page_content() -> str:
            """
            "Read" the entire page's content. Use this when you need to understand the whole page, not just the visible part.
            It returns a cleaned-up, Markdown-formatted version of the page content, which is useful for finding specific information.
            """
            return await self.extract_page_content()

        @tool
        async def go_back() -> str:
            """Navigate back to the previous page in the browser history."""
            return await self.go_back()

        @tool
        async def go_forward() -> str:
            """Navigate forward to the next page in the browser history."""
            return await self.go_forward()

        @tool
        async def hover(bbox_id: int) -> str:
            """Hover the mouse over an element to reveal hidden menus or tooltips.

            Args:
                bbox_id (int): The ID of the element to hover over.
            """
            return await self.hover(bbox_id)

        @tool
        async def press_key(key: str) -> str:
            """Simulate a key press on the keyboard.

            Args:
                key (str): The key to press (e.g., 'Enter', 'Escape', 'ArrowDown').
            """
            return await self.press_key(key)

        @tool
        async def drag(start_bbox_id: int, end_bbox_id: int) -> str:
            """Drag an element from a start position to an end position.

            Args:
                start_bbox_id (int): The ID of the element to start dragging.
                end_bbox_id (int): The ID of the element to drop onto.
            """
            return await self.drag(start_bbox_id, end_bbox_id)

        @tool
        async def wait_for(
            time: Optional[float] = None,
            bbox_id: Optional[int] = None,
            state: str = "attached",
        ) -> str:
            """Wait for a specific condition to be met.

            Args:
                time (float, optional): Time to wait in seconds.
                bbox_id (int, optional): The ID of an element to wait for.
                state (str, optional): "attached" to wait for the element to appear, or "detached" to wait for it to disappear. Defaults to "attached".
            """
            return await self.wait_for(time=time, bbox_id=bbox_id, state=state)

        @tool
        async def browser_goto(url: str) -> str:
            """Navigate directly to a specific URL.

            Args:
                url (str): The URL to navigate to (http/https prefix is optional).
            """
            return await self.browser_goto(url)

        @tool
        async def browser_select_option(bbox_id: int, values: List[str]) -> str:
            """Select one or more options from a dropdown/select element.

            Args:
                bbox_id (int): The ID number of the select element.
                values (List[str]): List of option values to select.
            """
            return await self.browser_select_option(bbox_id, values)

        @tool
        async def list_tabs() -> str:
            """List all open browser tabs with their indices, titles, and URLs."""
            return await self.list_tabs()

        @tool
        async def switch_tab(tab_index: int) -> str:
            """Switch to a specific browser tab by its index number.

            Args:
                tab_index (int): The index number of the tab to switch to (from list_tabs).
            """
            return await self.switch_tab(tab_index)

        @tool
        async def open_new_tab(url: str = None) -> str:
            """Open a new browser tab, optionally navigating to a specific URL.

            Args:
                url (str, optional): URL to navigate to in the new tab.
            """
            return await self.open_new_tab(url)

        @tool
        async def close_tab(tab_index: int = None) -> str:
            """Close a browser tab by its index, or close the current tab if no index specified.

            Args:
                tab_index (int, optional): Index of the tab to close. If None, closes current tab.
            """
            return await self.close_tab(tab_index)

        @tool
        def take_note(note: str) -> str:
            """Take a note for future reference during this session.

            Args:
                note (str): The note to record.
            """
            return self.take_note(note)

        return [
            click,
            type_text,
            scroll,
            refresh,
            extract_page_content,
            go_back,
            go_forward,
            hover,
            press_key,
            drag,
            wait_for,
            browser_goto,
            browser_select_option,
            list_tabs,
            switch_tab,
            open_new_tab,
            close_tab,
            take_note
        ]