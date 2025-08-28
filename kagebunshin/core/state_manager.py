"""
KageBunshin State Manager - Stateless manager that operates on KageBunshinState.
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

from .state import KageBunshinState, BBox, TabInfo, Annotation
from ..utils import html_to_markdown, annotate_page
from ..automation.behavior import (
    smart_delay_between_actions,
    human_delay,
    get_random_offset_in_bbox,
    human_mouse_move,
    human_type_text,
    human_scroll,
)
from ..automation.fingerprinting import apply_fingerprint_profile
from ..automation.performance_optimizer import PerformanceOptimizer
from ..config.settings import (
    SUMMARIZER_MODEL, 
    SUMMARIZER_PROVIDER, 
    PERFORMANCE_MODE, 
    PERFORMANCE_PROFILES,
    ENABLE_PERFORMANCE_LEARNING
)
logger = logging.getLogger(__name__)


class KageBunshinStateManager:
    """
    Stateless state manager that operates on KageBunshinState.
    
    This class provides tools and operations but doesn't maintain any state itself.
    All browser state comes from the KageBunshinState passed to methods.
    All derived data (screenshots, bboxes, etc.) is computed fresh on-demand.
    """

    def __init__(self, context: BrowserContext): 
        """Initialize the stateless state manager."""
        self.current_state = KageBunshinState(
            input="",
            messages=[],
            context=context
        )
        # Current page data (derived from state)
        self.current_bboxes: List[BBox] = []
        self._action_count: int = 0
        self.prev_snapshot: Optional[Annotation] = None
        self.current_page_index: int = 0
        
        # Performance optimization
        self.performance_optimizer = PerformanceOptimizer(speed_mode=PERFORMANCE_MODE)
        self.performance_enabled = ENABLE_PERFORMANCE_LEARNING
        self.performance_profile = PERFORMANCE_PROFILES.get(PERFORMANCE_MODE, PERFORMANCE_PROFILES["balanced"])
        
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
        """Factory method to create a KageBunshinStateManager with async initialization."""
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

    def set_state(self, state: KageBunshinState) -> None: 
        """Set the current state to operate on."""
        if not state:
            raise ValueError("State cannot be None or empty.")
        
        context = state.get("context")
        if context is None:
            raise ValueError("State must contain a valid browser context. Context cannot be None.")
            
        self.current_state = state
        self.current_bboxes = []  # Reset derived data
        
    def get_current_page(self) -> Page:
        """Get the current active page from state."""
        if not self.current_state:
            raise ValueError("No state set. Call set_state first.")
        
        context = self.current_state.get("context")
        if context is None:
            raise ValueError("Browser context is None. State may be corrupted or browser context was closed.")
            
        pages = context.pages
        if not pages:
            raise ValueError("No pages available in browser context. Browser may have been closed.")
            
        current_index = self.current_page_index
        if current_index >= len(pages):
            raise ValueError(f"Invalid page index: {current_index}. Valid range: 0-{len(pages)-1}")
        return pages[current_index]

    def get_context(self) -> BrowserContext:
        """Get the browser context from state."""
        if not self.current_state:
            raise ValueError("No state set. Call set_state first.")
        
        context = self.current_state.get("context")
        if context is None:
            raise ValueError("Browser context is None. State may be corrupted or browser context was closed.")
            
        return context

    def increment_action_count(self) -> None:
        """Increment the action count."""
        self._action_count += 1
        
    def get_current_url(self) -> str:
        """Get the current page URL."""
        try:
            page = self.get_current_page()
            return page.url
        except Exception:
            return "about:blank"
            
    def get_delay_profile(self) -> str:
        """Get the appropriate delay profile for current context."""
        if not self.performance_enabled:
            return "normal"
            
        try:
            url = self.get_current_url()
            return self.performance_optimizer.get_optimal_delay_profile(url, "general")
        except Exception:
            return self.performance_profile.get("delay_profile", "normal")

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
        """Get CSS selector for a bbox ID with caching support."""
        bbox = self._get_bbox_by_id(bbox_id)
        if not bbox:
            raise ValueError(f"Invalid bbox_id: {bbox_id}. Valid range: 0-{len(self.current_bboxes)-1}")
        # if bbox.isCaptcha:
        #     raise ValueError(f"Action failed: Element {bbox_id} is identified as a CAPTCHA.")
        
        # Try to get cached selector first
        if self.performance_enabled:
            cached_info = self.performance_optimizer.get_cached_element_info(f"bbox_{bbox_id}")
            if cached_info and "selector" in cached_info:
                return cached_info["selector"]
        
        # Get selector from bbox
        try:
            selector = getattr(bbox, "selector", None)
            if selector:
                # Cache the selector
                if self.performance_enabled:
                    self.performance_optimizer.cache_element_info(f"bbox_{bbox_id}", {
                        "selector": selector,
                        "element_type": bbox.type,
                        "aria_label": bbox.ariaLabel,
                        "text": bbox.text
                    })
                return selector
        except Exception:
            pass
            
        # Fallback selector
        fallback_selector = f'[data-ai-label="{bbox_id}"]'
        
        # Cache the fallback selector
        if self.performance_enabled:
            self.performance_optimizer.cache_element_info(f"bbox_{bbox_id}", {
                "selector": fallback_selector,
                "element_type": bbox.type,
                "aria_label": bbox.ariaLabel,
                "text": bbox.text
            })
            
        return fallback_selector


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

    async def _wait_for_load_state(self, state: str = "load") -> None:
        """Waits for the page to be in the given state.
        state: 'load', 'domcontentloaded', 'networkidle'
        """
        page = self.get_current_page()
        await page.wait_for_load_state(state, timeout=3000)

    # ===========================================
    # HYBRID ACTION EXECUTION
    # ===========================================

    async def _capture_page_state(self, lightweight: bool = False) -> Tuple[str, str, int]:
        """Captures the current page state (URL, DOM hash, and tab count) for verification."""
        page = self.get_current_page()
        context = self.get_context()
        num_tabs = len(context.pages)
        url = page.url
        
        # For performance optimization, use lightweight verification when enabled
        if lightweight and self.performance_enabled:
            # Use a simpler hash based on URL and tab count
            simple_state = f"{url}_{num_tabs}_{time.time()}"
            dom_hash = hashlib.sha256(simple_state.encode()).hexdigest()[:16]  # Shortened hash
        else:
            try:
                content = await page.content()
                dom_hash = hashlib.sha256(content.encode()).hexdigest()
            except Exception:
                # Fallback if page content is not available
                dom_hash = hashlib.sha256(str(time.time()).encode()).hexdigest()
        
        return url, dom_hash, num_tabs
        
    async def _verify_page_changed_async(self, before_state: Tuple[str, str, int], lightweight: bool = False) -> bool:
        """Asynchronously verify if page state changed."""
        try:
            after_state = await self._capture_page_state(lightweight=lightweight)
            return before_state != after_state
        except Exception:
            return False  # Assume no change if verification fails

    # --- Native Actions (Fast, Playwright-based) ---

    async def _click_native(self, bbox_id: int) -> None:
        """Click on an element using Playwright's native click."""
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        await page.click(selector, timeout=3000)

    async def _type_text_native(self, bbox_id: int, text_content: str, press_enter: bool = False) -> None:
        """Type text using Playwright's native fill and press."""
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        await page.fill(selector, text_content, timeout=3000)
        if press_enter:
            await page.keyboard.press("Enter")

    async def _select_option_native(self, bbox_id: int, values: List[str]) -> None:
        """Select an option using Playwright's native select_option."""
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        await page.select_option(selector, values, timeout=3000)

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
        
        delay_profile = self.get_delay_profile()
        await smart_delay_between_actions("click", profile=delay_profile)
        await human_mouse_move(page, start_x, start_y, x, y, profile=delay_profile)
        await human_delay(50, 200, profile=delay_profile)
        await page.mouse.click(x, y)

    async def _type_text_human_like(self, bbox_id: int, text_content: str, press_enter: bool = False) -> None:
        """Type text using human-like delays and keystrokes."""
        bbox = self._get_bbox_by_id(bbox_id)
        if not bbox:
            raise ValueError(f"Invalid bbox_id {bbox_id}")

        page = self.get_current_page()
        x, y = get_random_offset_in_bbox(bbox)
        
        delay_profile = self.get_delay_profile()
        await smart_delay_between_actions("type", profile=delay_profile)
        current_pos = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
        start_x, start_y = current_pos.get("x", 0), current_pos.get("y", 0)
        
        await human_mouse_move(page, start_x, start_y, x, y, profile=delay_profile)
        await page.mouse.click(x, y)
        await human_delay(100, 300, profile=delay_profile)
        
        select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
        await page.keyboard.press(select_all)
        await human_delay(50, 150, profile=delay_profile)
        await page.keyboard.press("Backspace")
        await human_delay(100, 200, profile=delay_profile)
        
        await human_type_text(page, text_content, profile=delay_profile)
        await human_delay(200, 600, profile=delay_profile)
        if press_enter:
            await page.keyboard.press("Enter")

    async def _select_option_human_like(self, bbox_id: int, values: List[str]) -> None:
        """Select an option with human-like mouse movement and delays."""
        bbox = self._get_bbox_by_id(bbox_id)
        if not bbox:
            raise ValueError(f"Invalid bbox_id {bbox_id}")
        
        selector = self._get_selector(bbox_id)
        page = self.get_current_page()
        
        delay_profile = self.get_delay_profile()
        await smart_delay_between_actions("click", profile=delay_profile)
        
        x, y = get_random_offset_in_bbox(bbox)
        current_pos = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
        start_x, start_y = current_pos.get("x", 0), current_pos.get("y", 0)
        
        await human_mouse_move(page, start_x, start_y, x, y, profile=delay_profile)
        await human_delay(100, 300, profile=delay_profile)
        
        await page.select_option(selector, values)
        await human_delay(200, 500, profile=delay_profile)

    # ===========================================
    # BROWSER INTERACTION TOOL METHODS
    # ===========================================

    async def click(self, bbox_id: int) -> str:
        """
        Clicks on an element. Uses intelligent fallback strategy based on performance optimization.
        May skip native attempt and go straight to human-like if the optimizer suggests it.
        Also detects and switches to new tabs if they are opened by the click.
        """
        start_time = time.time()
        logger.info(f"Attempting to click element with bbox_id: {bbox_id}")
        
        url = self.get_current_url()
        selector = self._get_selector(bbox_id)
        before_pages = self.get_context().pages
        before_state = await self._capture_page_state()
        
        native_success = False
        fallback_needed = False
        
        # Check if we should skip native attempt
        should_skip_native = (
            self.performance_enabled and 
            self.performance_optimizer.should_skip_native_attempt(url, selector, "click")
        )
        
        if not should_skip_native:
            try:
                # Attempt 1: Native Playwright click (fast)
                logger.info("Attempting native click...")
                await self._click_native(bbox_id)
                await self._wait_for_load_state()
                
                # Additional delay for dynamic content when performance optimization is enabled
                if self.performance_enabled:
                    await asyncio.sleep(0.5)  # Allow DOM changes to settle
                    
                after_state = await self._capture_page_state()

                if before_state != after_state:
                    native_success = True
                    self.increment_action_count()
                    await self._check_for_new_tabs(before_pages)
                    logger.info(f"Native click on bbox_id {bbox_id} successful and caused a page change.")
                    
                    # Record successful interaction
                    if self.performance_enabled:
                        response_time = time.time() - start_time
                        self.performance_optimizer.record_interaction(
                            url, selector, "click", True, False, response_time
                        )
                    
                    return f"Successfully clicked element {bbox_id}."
                
                logger.warning(f"Native click on bbox_id {bbox_id} had no effect. Falling back.")

            except Exception as e:
                logger.warning(f"Native click failed for bbox_id {bbox_id}: {e}. Falling back.")
        else:
            logger.info(f"Skipping native click for {bbox_id} based on performance optimizer recommendation.")

        # Attempt 2: Human-like fallback
        fallback_needed = True
        try:
            logger.info("Attempting human-like click...")
            await self._click_human_like(bbox_id)
            await self._wait_for_load_state()
            final_state = await self._capture_page_state()

            if before_state != final_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Human-like fallback click on bbox_id {bbox_id} successful.")
                
                # Record interaction outcome
                if self.performance_enabled:
                    response_time = time.time() - start_time
                    self.performance_optimizer.record_interaction(
                        url, selector, "click", native_success, fallback_needed, response_time
                    )
                
                return f"Successfully clicked element {bbox_id} using fallback."
            else:
                logger.error(f"All click attempts on bbox_id {bbox_id} failed to change the page state.")
                
                # Record failed interaction
                if self.performance_enabled:
                    response_time = time.time() - start_time
                    self.performance_optimizer.record_interaction(
                        url, selector, "click", False, True, response_time
                    )
                
                return f"Error: Clicking element {bbox_id} had no effect on the page."

        except Exception as e:
            logger.error(f"Human-like fallback click also failed for bbox_id {bbox_id}: {e}")
            
            # Record failed interaction
            if self.performance_enabled:
                response_time = time.time() - start_time
                self.performance_optimizer.record_interaction(
                    url, selector, "click", False, True, response_time
                )
            
            return f"Error: All click attempts failed for element {bbox_id}. Last error: {e}"

    async def type_text(self, bbox_id: int, text_content: str, press_enter: bool = False) -> str:
        """
        Types text into an element. Uses intelligent fallback strategy based on performance optimization.
        May skip native attempt and go straight to human-like if the optimizer suggests it.
        Also detects and switches to new tabs if they are opened by the action.
        """
        start_time = time.time()
        logger.info(f"Attempting to type '{text_content}' into element with bbox_id: {bbox_id}")
        
        url = self.get_current_url()
        selector = self._get_selector(bbox_id)
        before_pages = self.get_context().pages
        before_state = await self._capture_page_state()
        
        native_success = False
        fallback_needed = False
        
        # Check if we should skip native attempt
        should_skip_native = (
            self.performance_enabled and 
            self.performance_optimizer.should_skip_native_attempt(url, selector, "type")
        )

        if not should_skip_native:
            try:
                # Attempt 1: Native Playwright type (fast)
                logger.info("Attempting native type...")
                await self._type_text_native(bbox_id, text_content, press_enter)
                await self._wait_for_load_state()
                after_state = await self._capture_page_state()

                if before_state != after_state:
                    native_success = True
                    self.increment_action_count()
                    await self._check_for_new_tabs(before_pages)
                    logger.info(f"Native type on bbox_id {bbox_id} successful and caused a page change.")
                    
                    # Record successful interaction
                    if self.performance_enabled:
                        response_time = time.time() - start_time
                        self.performance_optimizer.record_interaction(
                            url, selector, "type", True, False, response_time
                        )
                    
                    return f"Successfully typed '{text_content}' into element {bbox_id}."
                
                logger.warning(f"Native type on bbox_id {bbox_id} had no effect. Falling back.")

            except Exception as e:
                logger.warning(f"Native type failed for bbox_id {bbox_id}: {e}. Falling back.")
        else:
            logger.info(f"Skipping native type for {bbox_id} based on performance optimizer recommendation.")

        # Attempt 2: Human-like fallback
        fallback_needed = True
        try:
            logger.info("Attempting human-like type...")
            await self._type_text_human_like(bbox_id, text_content, press_enter)
            await self._wait_for_load_state()
            final_state = await self._capture_page_state()

            if before_state != final_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Human-like fallback type on bbox_id {bbox_id} successful.")
                
                # Record interaction outcome
                if self.performance_enabled:
                    response_time = time.time() - start_time
                    self.performance_optimizer.record_interaction(
                        url, selector, "type", native_success, fallback_needed, response_time
                    )
                
                return f"Successfully typed '{text_content}' into element {bbox_id} using fallback."
            else:
                logger.error(f"All type attempts on bbox_id {bbox_id} failed to change the page state.")
                
                # Record failed interaction
                if self.performance_enabled:
                    response_time = time.time() - start_time
                    self.performance_optimizer.record_interaction(
                        url, selector, "type", False, True, response_time
                    )
                
                return f"Error: Typing into element {bbox_id} had no effect on the page."

        except Exception as e:
            logger.error(f"Human-like fallback type also failed for bbox_id {bbox_id}: {e}")
            
            # Record failed interaction
            if self.performance_enabled:
                response_time = time.time() - start_time
                self.performance_optimizer.record_interaction(
                    url, selector, "type", False, True, response_time
                )
            
            return f"Error: All type attempts failed for element {bbox_id}. Last error: {e}"

    async def browser_select_option(self, bbox_id: int, values: List[str]) -> str:
        """
        Selects an option in a dropdown. Uses intelligent fallback strategy based on performance optimization.
        May skip native attempt and go straight to human-like if the optimizer suggests it.
        Also detects and switches to new tabs if they are opened by the action.
        """
        start_time = time.time()
        logger.info(f"Attempting to select {values} in element with bbox_id: {bbox_id}")
        
        url = self.get_current_url()
        selector = self._get_selector(bbox_id)
        before_pages = self.get_context().pages
        before_state = await self._capture_page_state()
        
        native_success = False
        fallback_needed = False
        
        # Check if we should skip native attempt
        should_skip_native = (
            self.performance_enabled and 
            self.performance_optimizer.should_skip_native_attempt(url, selector, "select")
        )

        if not should_skip_native:
            try:
                # Attempt 1: Native Playwright select (fast)
                logger.info("Attempting native select...")
                await self._select_option_native(bbox_id, values)
                await self._wait_for_load_state()
                after_state = await self._capture_page_state()

                if before_state != after_state:
                    native_success = True
                    self.increment_action_count()
                    await self._check_for_new_tabs(before_pages)
                    logger.info(f"Native select on bbox_id {bbox_id} successful and caused a page change.")
                    
                    # Record successful interaction
                    if self.performance_enabled:
                        response_time = time.time() - start_time
                        self.performance_optimizer.record_interaction(
                            url, selector, "select", True, False, response_time
                        )
                    
                    return f"Successfully selected {values} in element {bbox_id}."
                
                logger.warning(f"Native select on bbox_id {bbox_id} had no effect. Falling back.")

            except Exception as e:
                logger.warning(f"Native select failed for bbox_id {bbox_id}: {e}. Falling back.")
        else:
            logger.info(f"Skipping native select for {bbox_id} based on performance optimizer recommendation.")

        # Attempt 2: Human-like fallback
        fallback_needed = True
        try:
            logger.info("Attempting human-like select...")
            await self._select_option_human_like(bbox_id, values)
            await self._wait_for_load_state()
            final_state = await self._capture_page_state()

            if before_state != final_state:
                self.increment_action_count()
                await self._check_for_new_tabs(before_pages)
                logger.info(f"Human-like fallback select on bbox_id {bbox_id} successful.")
                
                # Record interaction outcome
                if self.performance_enabled:
                    response_time = time.time() - start_time
                    self.performance_optimizer.record_interaction(
                        url, selector, "select", native_success, fallback_needed, response_time
                    )
                
                return f"Successfully selected {values} in element {bbox_id} using fallback."
            else:
                logger.error(f"All select attempts on bbox_id {bbox_id} failed to change the page state.")
                
                # Record failed interaction
                if self.performance_enabled:
                    response_time = time.time() - start_time
                    self.performance_optimizer.record_interaction(
                        url, selector, "select", False, True, response_time
                    )
                
                return f"Error: Selecting in element {bbox_id} had no effect on the page."

        except Exception as e:
            logger.error(f"Human-like fallback select also failed for bbox_id {bbox_id}: {e}")
            
            # Record failed interaction
            if self.performance_enabled:
                response_time = time.time() - start_time
                self.performance_optimizer.record_interaction(
                    url, selector, "select", False, True, response_time
                )
            
            return f"Error: All select attempts failed for element {bbox_id}. Last error: {e}"

    async def scroll(self, target: str, direction: str) -> str:
        """Scroll the page or an element."""
        try:
            direction = direction.lower()
            if direction not in ["up", "down"]:
                return "Error: Direction must be 'up' or 'down'"

            page = self.get_current_page()
            delay_profile = self.get_delay_profile()
            await smart_delay_between_actions("scroll", profile=delay_profile)
            
            if target.lower() == "page":
                # Scroll the entire page
                scroll_amount = 500
                await human_scroll(page, 0, 0, direction, scroll_amount, profile=delay_profile)
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
                            await human_scroll(page, element_box['x'], element_box['y'], direction, scroll_amount, profile=delay_profile)
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
            await self._wait_for_load_state()
            return "Successfully refreshed the page."
        except Exception as e:
            logger.error(f"Error refreshing page: {e}")
            return f"Error refreshing page: {str(e)}"

    async def extract_page_content(self) -> str:
        """Return full visible page content as Markdown, plus a DOM outline, and an optional LLM-parsed Markdown.

        Designed to preserve content so LLMs can "read" articles and long text without hallucinating.
        Supports both HTML pages and PDF documents.
        """
        try:
            # This will now provide specific error messages if context or page is None
            page = self.get_current_page()
            
            # Additional validation to ensure page is accessible
            if not hasattr(page, 'url') or not hasattr(page, 'title') or not hasattr(page, 'content'):
                raise ValueError("Page object is invalid or corrupted.")
            
            url = page.url
            if url is None:
                url = "about:blank"
                logger.warning("Page URL is None, using placeholder")
                
            title = await page.title()
            if title is None:
                title = "Untitled"
                logger.warning("Page title is None, using placeholder")
                
            html_content = await page.content()
            if html_content is None:
                logger.error("Page content is None, cannot extract content")
                return "Error: Unable to extract page content - page content is None"
            
            # Check if this is a PDF page using the same logic as annotate_page
            is_pdf = 'type="application/pdf"' in html_content or 'class="pdf' in html_content
            
            if is_pdf:
                # Handle PDF content extraction
                try:
                    logger.info("PDF page detected. Extracting text content.")
                    api_request_context = page.context.request
                    response = await api_request_context.get(page.url)
                    pdf_bytes = await response.body()

                    # Extract text from PDF using pypdf
                    from io import BytesIO
                    import pypdf
                    
                    pdf_file = BytesIO(pdf_bytes)
                    reader = pypdf.PdfReader(pdf_file)
                    pdf_text = ""
                    for p in reader.pages:
                        pdf_text += p.extract_text() or ""
                    
                    # Format the output for PDF content
                    output = f"URL: {url}\nTitle: {title}\nContent Type: PDF Document\n\n{pdf_text.strip()}"
                    return output
                    
                except Exception as pdf_error:
                    logger.error(f"Failed to extract PDF content: {pdf_error}")
                    return f"URL: {url}\nTitle: {title}\nContent Type: PDF Document\n\nError: Failed to extract text from PDF. {str(pdf_error)}"
            else:
                # Handle regular HTML content
                cleaned_markdown = html_to_markdown(html_content)
                if cleaned_markdown is None:
                    logger.warning("html_to_markdown returned None, using empty string")
                    cleaned_markdown = ""

                output = f"URL: {url}\nTitle: {title}\n\n{cleaned_markdown}"
                return output

        except ValueError as e:
            # These are our specific validation errors - log and re-raise with context
            logger.error(f"State validation error in extract_page_content: {e}")
            return f"Error extracting page content: {str(e)}"
        except Exception as e:
            # Log the full exception for debugging
            logger.error(f"Error extracting page content: {e}", exc_info=True)
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
            delay_profile = self.get_delay_profile()
            await smart_delay_between_actions("navigate", profile=delay_profile)
            await page.go_back()
            self.increment_action_count()
            
            # Wait for navigation to complete
            await self._wait_for_load_state()
            
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
            delay_profile = self.get_delay_profile()
            await smart_delay_between_actions("navigate", profile=delay_profile)
            await page.goto(url)
            self.increment_action_count()
            
            # Wait for page to load
            await self._wait_for_load_state()
            
            return f"Successfully navigated to {url}"
            
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            return f"Error navigating to {url}: {str(e)}"

    async def go_forward(self) -> str:
        """Navigate forward in browser history."""
        try:
            page = self.get_current_page()
            delay_profile = self.get_delay_profile()
            await smart_delay_between_actions("navigate", profile=delay_profile)
            await page.go_forward()
            self.increment_action_count()
            await self._wait_for_load_state()
            return "Successfully navigated forward"
        except Exception as e:
            logger.error(f"Error going forward: {e}")
            return f"Error going forward: {str(e)}"

    async def hover(self, bbox_id: int) -> str:
        """Hover over an element identified by its bounding box ID."""
        try:
            selector = self._get_selector(bbox_id)
            page = self.get_current_page()
            await page.hover(selector, timeout=3000)
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
                await page.wait_for_selector(selector, state=state, timeout=3000) # wait for 5 seconds max
                
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
                tab_list.append(f"  {tab['tab_index']}: {tab['title']} - {tab['url']}{status}")
            
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
        return f"Note recorded."
        
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance optimization statistics."""
        if not self.performance_enabled:
            return {"performance_optimization": "disabled"}
            
        try:
            stats = self.performance_optimizer.get_performance_stats()
            stats.update({
                "current_performance_mode": PERFORMANCE_MODE,
                "performance_profile": self.performance_profile,
                "total_actions": self._action_count
            })
            return stats
        except Exception as e:
            # Return basic stats on error
            return {
                "performance_optimization": "error",
                "error": str(e),
                "current_performance_mode": PERFORMANCE_MODE,
                "total_actions": self._action_count
            }
        
    def reset_performance_cache(self) -> str:
        """Clear performance optimization cache."""
        if not self.performance_enabled:
            return "Performance optimization is disabled."
            
        self.performance_optimizer.clear_cache()
        return "Performance cache cleared successfully."
    
    # ===========================================
    # TOOL CREATION FOR LLM BINDING
    # ===========================================

    def get_tools_for_llm(self):
        """Returns a list of tools that can be bound to the LLM."""
        
        @tool
        async def click(bbox_id: int) -> str:
            """Click on an interactive element identified by its bounding box ID.

            This is Kagebunshin's core interaction tool that uses a sophisticated hybrid execution strategy
            for maximum reliability. It first attempts fast native Playwright clicks, then automatically 
            falls back to human-like mouse movements if needed. Essential for all user interface interactions.

            ## Purpose & Use Cases

            **Primary Interactions:**
            - Click buttons, links, and interactive elements
            - Submit forms and trigger form actions
            - Navigate through websites and applications
            - Activate dropdown menus and select options
            - Trigger JavaScript events and dynamic content loading
            - Interact with modal dialogs and popups
            - Activate image galleries, carousels, and media players

            **Advanced Scenarios:**
            - Handle anti-bot detection systems with human-like fallback
            - Interact with complex single-page applications
            - Trigger AJAX requests and dynamic page updates
            - Navigate through multi-step workflows and wizards
            - Activate hover-dependent elements that require precise clicking

            ## Arguments

            **bbox_id** (int, required):
            - The ID number of the bounding box element from the page annotation
            - Must correspond to a currently visible interactive element
            - Invalid IDs will raise ValueError with valid range information

            ## Returns

            **Success responses:**
            - `"Successfully clicked element {bbox_id}."` - Native click succeeded
            - `"Successfully clicked element {bbox_id} using fallback."` - Human-like fallback succeeded

            **Error responses:**
            - `"Error: Clicking element {bbox_id} had no effect on the page."` - Click registered but no page change
            - `"Error: All click attempts failed for element {bbox_id}. Last error: {details}"` - Complete failure

            ## Behavior Details

            **Hybrid Execution Strategy:**
            1. **Native Click Attempt**: Fast Playwright click with 5-second timeout
            2. **Page State Verification**: Compares URL, DOM hash, and tab count before/after
            3. **Human-like Fallback**: If native click fails or has no effect:
               - Calculates random offset within element bounds
               - Performs realistic mouse movement from current position
               - Adds human-like delays (50-200ms) before clicking
               - Uses random click coordinates to avoid bot detection patterns

            **New Tab Detection:**
            - Automatically detects if click opened new tabs
            - Switches to newest tab if new tabs are opened
            - Updates internal page tracking for seamless continuation
            - Logs tab switches for user awareness

            **Action Verification:**
            - Captures page state (URL, DOM hash, tab count) before clicking
            - Waits 1 second after click for page updates to complete
            - Compares before/after state to confirm click had effect
            - Only increments action counter if page state actually changed

            ## Important Notes

            **Element Validation:**
            - Invalid bbox_id values trigger immediate error with valid range
            - Elements must be currently visible and accessible on the page
            - Some elements may require hovering first to become clickable

            **Timing and Delays:**
            - Native clicks execute immediately for maximum speed
            - Human-like fallback includes realistic delays and mouse movement
            - 1-second wait after clicking allows page updates to complete
            - Smart delays between actions help maintain human-like behavior

            **Success Criteria:**
            - Click is considered successful only if page state changes
            - Page changes include URL changes, DOM updates, or new tabs opening
            - Clicks that don't change page state are reported as having "no effect"
            - This prevents false positives from non-functional elements

            ## Troubleshooting

            **"Clicking element had no effect":**
            - Element may not be functional (decorative or disabled)
            - Element may require hover() activation before clicking
            - Page may need scrolling to properly load the element

            **"All click attempts failed":**
            - Element may not be clickable (covered by another element)
            - Element selector may be invalid or element removed from page
            - Page may have changed, requiring fresh page annotation
            - Network issues may be preventing interaction

            **New tabs not switching correctly:**
            - Kagebunshin automatically switches to new tabs when detected
            - If tab switching seems wrong, use list_tabs() and switch_tab() manually
            - Some sites open tabs in background - check tab status with list_tabs()

            ## Best Practices

            **Reliable Clicking:**
            - Always verify click success by checking return messages
            - Use extract_page_content() or take_note() to confirm expected results
            - If clicks fail, try hover() first to activate hover-dependent elements
            - Consider scroll() if element might be partially off-screen

            **Form Interactions:**
            - Click form elements in logical order (top to bottom)
            - Verify form submission success before proceeding
            - Use press_enter parameter in type_text() as alternative to clicking submit buttons
            - Take notes after successful form submissions for tracking

            **Error Recovery:**
            - If native click fails, the human-like fallback runs automatically
            - For persistent failures, try refresh()
            - Use browser_goto() to restart if page becomes unresponsive

            ## Integration with Kagebunshin Features

            **Stealth and Anti-Detection:**
            - Human-like fallback uses realistic mouse movement patterns
            - Random click coordinates within element bounds avoid detection
            - Variable delays and movements simulate natural human behavior
            - Automatic fallback ensures maximum success rate across different sites

            **Multi-Tab Management:**
            - Automatically handles new tabs opened by clicks
            - Maintains context across tab switches
            - Updates internal page tracking seamlessly
            - Enables complex multi-tab workflows without manual management
            """
            return await self.click(bbox_id)

        @tool
        async def type_text(bbox_id: int, text_content: str, press_enter: bool = False) -> str:
            """Type text into input fields, textareas, and other text input elements.
            ## Purpose & Use Cases

            **Form Interactions:**
            - Fill out login forms (username, password fields)
            - Complete registration and contact forms
            - Enter search queries and filter criteria
            - Input personal information, addresses, phone numbers
            - Fill textarea elements with longer content (comments, descriptions)
            - Enter payment information and checkout details

            **Advanced Text Input:**
            - Handle complex input validation and real-time formatting
            - Work with auto-completing search fields
            - Input structured data (dates, numbers, codes)
            - Fill multi-step form wizards
            - Handle input fields with character limits or special requirements
            - Work with rich text editors and formatted input areas

            ## Arguments

            **bbox_id** (int, required):
            - The ID number of the input element from the page annotation
            - Must correspond to a text input element (input, textarea, contenteditable)
            - Valid range is 0 to (number of detected elements - 1)
            - Invalid IDs will raise ValueError with valid range information

            **text_content** (str, required):
            - The text to input into the element
            - Can be any string including special characters, numbers, symbols
            - Supports Unicode characters for international text
            - Empty strings are allowed (useful for clearing fields)
            - Line breaks (\\n) are supported for textarea elements

            **press_enter** (bool, optional):
            - Whether to press Enter key after typing text
            - Defaults to False (no Enter key press)
            - Set to True for search fields and single-line forms
            - Useful for submitting forms without clicking submit buttons
            - Alternative to clicking submit buttons in many workflows
            - **WARNING:** If the search field is likely to be a dropdown, set press_enter=False

            ## Returns

            **Success responses:**
            - `"Successfully typed '{text_content}' into element {bbox_id}."` - Native input succeeded
            - `"Successfully typed '{text_content}' into element {bbox_id} using fallback."` - Human-like fallback succeeded

            **Error responses:**
            - `"Error: Typing into element {bbox_id} had no effect on the page."` - Input registered but no page change
            - `"Error: All type attempts failed for element {bbox_id}. Last error: {details}"` - Complete failure

            ## Behavior Details

            **Form Submission Options:**
            - press_enter=True sends Enter key after typing
            - Useful for search forms and single-field submissions
            - Alternative to clicking submit buttons
            - Works with both native and human-like input modes

            ## Important Notes

            **Field Clearing:**
            - Both native and human-like modes clear existing content first
            - Native mode uses Playwright's fill() which replaces content
            - Human-like mode uses Select All + Backspace for natural behavior
            - Essential for fields that may have placeholder or existing text

            **Input Validation Handling:**
            - Some forms validate input in real-time during typing
            - Human-like typing may trigger validation at each character
            - Native input may bypass some client-side validation
            - Both modes wait for page state changes to complete

            **Focus and Interaction:**
            - Human-like mode clicks the element to ensure proper focus
            - Uses random click coordinates within element bounds
            - Handles focus-dependent elements and input activation
            - Maintains natural interaction patterns for anti-detection

            ## Troubleshooting

            **"Typing had no effect":**
            - Element may not be a valid input field
            - Element may be disabled or read-only
            - JavaScript may be preventing input
            - Try click() on the element first to activate it

            **Text not appearing correctly:**
            - Some fields have input formatting that changes appearance
            - Rich text editors may modify content during input
            - Auto-completion may alter or complete text
            - Special characters may need escaping or alternative input methods

            ## Best Practices

            **Form Filling Strategy:**
            - Fill fields in logical top-to-bottom order
            - Use take_note() to track successful form submissions
            - Verify field content with extract_page_content() for critical data
            - Test both native and fallback approaches for problematic fields

            **Text Input Optimization:**
            - Use press_enter=True for single-field forms (search boxes)
            - Clear understanding of field requirements (length, format, validation)
            - Handle special characters carefully - test with simple text first
            - Consider scroll() if input field is not fully visible

            **Error Recovery:**
            - If native input fails, human-like fallback runs automatically
            - For persistent failures, try refresh() and re-annotate the page
            - Use hover() before typing if element requires activation
            - Consider click() to focus problematic input elements

            ## Advanced Features

            **Platform-Specific Behavior:**
            - Uses Command key on macOS, Control key on other platforms
            - Adapts keyboard shortcuts to operating system conventions
            - Handles different input method editors and international keyboards
            - Maintains natural typing patterns across different systems

            **Anti-Detection Integration:**
            - Human-like fallback uses realistic typing rhythms and patterns
            - Variable delays and natural hesitations avoid bot detection
            - Random click positioning within input elements
            - Maintains consistent timing patterns throughout sessions
            """
            return await self.type_text(bbox_id, text_content, press_enter)

        @tool
        async def scroll(target: str, direction: str) -> str:
            """Scroll the page or specific elements to reveal more content with human-like scrolling patterns.

            This tool provides realistic scrolling functionality that mimics natural human scrolling behavior,
            breaking scroll actions into multiple smaller increments with variable timing. Essential for 
            navigating long pages, infinite scroll content, and accessing off-screen elements.

            ## Purpose & Use Cases

            **Page Navigation:**
            - Navigate through long articles and documentation
            - Access content below the fold on landing pages
            - Browse through product listings and catalogs
            - Explore social media feeds and infinite scroll content
            - Navigate through search results and listings
            - Access footer information and additional page sections

            **Dynamic Content Loading:**
            - Trigger lazy-loaded images and content sections
            - Activate infinite scroll mechanisms for more results
            - Load additional product recommendations and suggestions
            - Reveal sticky navigation and scroll-triggered elements
            - Access content that appears only after scrolling
            - Trigger scroll-based animations and interactions

            **Element-Specific Scrolling:**
            - Scroll within dropdown menus and select lists
            - Navigate through scrollable tables and data grids
            - Browse content within modal dialogs and sidebars
            - Scroll through textarea content and code blocks
            - Navigate within embedded frames and widgets

            ## Arguments

            **target** (str, required):
            - `"page"` - Scroll the entire page/window (most common usage)
            - `"{bbox_id}"` - Scroll within a specific scrollable element (e.g., "5", "12")
            - Target must be either literal "page" string or valid bbox_id number as string
            - For element scrolling, bbox_id must correspond to a scrollable container
            - Invalid bbox_id values will result in clear error messages

            **direction** (str, required):
            - `"up"` - Scroll upward to reveal content above current viewport
            - `"down"` - Scroll downward to reveal content below current viewport  
            - Case-insensitive ("UP", "Down", "DOWN" all work)
            - Only these two directions are supported

            ## Returns
            **Success response:** `"Successfully scrolled {direction}"`
            **Error responses:**
            - `"Error: Direction must be 'up' or 'down'"` - Invalid direction parameter
            - `"Error: Invalid bbox_id {target}"` - Element target not found
            - `"Error: Could not get bounding box for element {target}"` - Element not accessible
            - `"Error: Element with bbox_id {target} not found"` - Element no longer exists
            - `"Error scrolling: {details}"` - General scrolling failure

            ## Behavior Details

            **Page Scrolling:**
            - Default scroll amount: 500 pixels per action
            - Automatically adapts to page height and content
            - Maintains smooth scrolling performance across different page types
            - Handles both short pages and very long content effectively
            - Works with sticky headers, fixed navigation, and complex layouts

            **Element Scrolling:**
            - Default scroll amount: 200 pixels for contained elements
            - Works with scrollable divs, tables, dropdown lists, and containers
            - Automatically detects element boundaries and scroll limits
            - Handles nested scrollable elements correctly
            - Maintains element focus and visibility during scrolling

            ## Important Notes

            **Scroll Target Selection:**
            - Page scrolling works on all websites and is the most reliable option
            - Element scrolling requires the target to be a scrollable container
            - Not all elements with content overflow support programmatic scrolling
            - Some custom scrollable elements may not respond to standard scroll events

            **Content Loading Considerations:**
            - Many modern sites use lazy loading triggered by scrolling
            - Infinite scroll mechanisms often require specific scroll positions
            - Some content may take time to load after scrolling (images, ads, widgets)
            - Dynamic content may change page height and available scroll space

            **Timing and Performance:**
            - Human-like scrolling is slower than instant scrolling but more reliable
            - Multiple increments help trigger scroll-based events and animations
            - Proper timing prevents overwhelming servers with rapid scroll requests
            - Realistic patterns help avoid scroll-based bot detection

            ## Troubleshooting

            **Scrolling has no visible effect:**
            - Page may already be at scroll limit (top/bottom)
            - Check if page actually has scrollable content
            - Some single-page applications may override scroll behavior
            - Try scrolling in opposite direction to confirm functionality

            **Element scrolling not working:**
            - Verify the element is actually scrollable (has overflow content)
            - Element may be a display container rather than scrollable element
            - Try page scrolling instead if element scrolling fails
            - Some custom elements use different scroll implementations

            **Content not loading after scroll:**
            - Use wait_for() with time delay to allow content loading
            - Some lazy-loading requires multiple scroll actions to trigger
            - Check network connectivity if external content isn't loading
            - Consider refresh() if scrolling seems to break page functionality

            ## Best Practices

            **Efficient Content Discovery:**
            - Scroll incrementally and check content with extract_page_content()
            - Use take_note() to track your position and findings during exploration
            - Plan scroll strategy based on expected page layout and content structure
            - Combine scrolling with targeted element searching for efficiency

            **Infinite Scroll Management:**
            - Always include wait_for() delays after scrolling on infinite scroll pages
            - Monitor for duplicate content that indicates you've reached the end
            - Set reasonable limits to avoid infinite scrolling loops
            - Use take_note() to track total items loaded or progress made

            **Element Interaction Preparation:**
            - Scroll elements into view before attempting to interact with them
            - Some elements become clickable only when fully visible
            - Use scroll() before hover() or click() on partially visible elements
            - Consider page scrolling if element scrolling doesn't provide needed visibility

            ## Integration with Kagebunshin Features

            **Human-like Behavior Simulation:**
            - Multiple small scrolls mimic natural human scrolling patterns
            - Variable timing and amounts avoid mechanical scroll signatures
            - Works seamlessly with other human-like interaction tools
            - Maintains consistent behavioral patterns across browser sessions

            **Dynamic Content Support:**
            - Handles modern single-page applications and dynamic content loading
            - Compatible with JavaScript-heavy sites that modify content on scroll
            - Works with Progressive Web Apps and complex web applications
            - Supports both traditional page layouts and modern app interfaces
            """
            return await self.scroll(target, direction)

        @tool
        async def refresh() -> str:
            """Refresh the current browser page to get the latest content.
            
            This tool reloads the current page completely, discarding any unsaved
            form data and resetting the page to its initial state. It's equivalent
            to pressing F5 or clicking the browser's refresh button.
            
            Use refresh when:
            - Page content appears stale or outdated
            - JavaScript errors have broken page functionality
            - Dynamic content failed to load properly
            - You need to reset form state or clear temporary data
            - Page became unresponsive or partially loaded
            - Implementing retry logic after failed operations
            
            Returns:
                str: Success message "Successfully refreshed the page" or error message
                     with details if the refresh operation failed.
            
            Important Notes:
            - All unsaved form data will be lost
            - Page scroll position resets to top
            - Any temporary JavaScript state is cleared
            - Action count is incremented after successful refresh
            - Tool waits 1 second after refresh for page to settle
            - Some pages may redirect after refresh
            
            Cautions:
            - Don't refresh if user has entered important data that isn't saved
            - Some single-page applications may not handle refresh gracefully
            - Authentication state may be lost on some sites
            - Page may take longer to load after refresh
            """
            return await self.refresh()

        @tool
        async def extract_page_content() -> str:
            """
            Extract and "read" the entire page's content for evidence gathering. This is ESSENTIAL for fact verification.
            
            Use this tool to:
            - Verify information you need to report to users
            - Extract specific data, prices, specifications, etc.
            - Confirm details before making any claims
            - Get the full context of a webpage beyond what's visible
            
            Returns a cleaned-up, Markdown-formatted version of the page content. Always use this BEFORE stating facts from a website.
            
            IMPORTANT: Never make claims about page content without first using this tool to actually read the page.
            """
            return await self.extract_page_content()

        @tool
        async def go_back() -> str:
            """Navigate back to the previous page in the browser history.
            
            This tool simulates clicking the browser's back button, returning to
            the previously visited page within the current tab. It's essential for
            navigation workflows and correcting navigation mistakes.
            
            Use go_back when:
            - You navigated to the wrong page and need to return
            - Implementing breadcrumb-style navigation patterns
            - Returning to search results after viewing a specific item
            - Backing out of forms or workflows you don't want to complete
            - Returning to a parent page after exploring sub-pages
            - Correcting accidental clicks or navigation errors
            - Implementing multi-step comparison workflows
            
            Returns:
                str: Success message "Successfully navigated back" or error message
                     if the back navigation failed (e.g., no previous page exists).
            
            Important Notes:
            - Will fail if you're already at the first page visited in the tab
            - Some single-page applications may not support browser back properly
            - Dynamic content may have changed since you were last on the page
            - Form data from previous page may be restored or lost depending on site
            - JavaScript-heavy sites may intercept back navigation
            
            Limitations:
            - Cannot go back if no previous page exists in history
            - Some sites prevent back navigation for security reasons
            - Single-page applications may not maintain proper history
            - Very old history entries may have expired
            - Some forms clear data when you navigate back
            
            Alternative Navigation:
            - If go_back() fails, try browser_goto() with a known URL
            - Use breadcrumb links or navigation menus instead
            - Some sites provide "Return to..." links that work better than back
            
            **Best Practices:**
            - Always check if back navigation was successful
            - Consider whether form data needs to be preserved
            - Use go_back() for temporary exploration, browser_goto() for deliberate navigation
            - Keep track of your navigation path in complex workflows
            """
            return await self.go_back()

        @tool
        async def go_forward() -> str:
            """Navigate forward to the next page in the browser history.
            
            This tool simulates clicking the browser's forward button, advancing to
            the next page in the history stack. Only works if you've previously used
            the back button and there's a forward page available.
            
            Use go_forward when:
            - You went back too far and need to return to a more recent page
            - Implementing complex navigation workflows with back/forward patterns
            - Returning to a page after backing out temporarily
            - Navigating through a sequence of previously visited pages
            - Correcting over-navigation with the back button
            
            Returns:
                str: Success message "Successfully navigated forward" or error message
                     if forward navigation failed (e.g., no forward page exists).
            
            Important Notes:
            - Will fail if you're already at the most recent page in history
            - Forward history is cleared when you navigate to a new URL after going back
            - Some single-page applications may not support browser forward properly
            - Dynamic content may have changed since your last visit
            
            Limitations:
            - Cannot go forward if no forward history exists
            - Forward history is cleared when you navigate to new URLs after going back
            - Some sites prevent forward navigation for security reasons
            - Single-page applications may not maintain proper history
            - JavaScript can interfere with normal browser history behavior
            """
            return await self.go_forward()

        @tool
        async def hover(bbox_id: int) -> str:
            """Hover the mouse over an element to reveal hidden menus, tooltips, or trigger hover effects.
            
            Hovering simulates placing the mouse cursor over an element without clicking,
            which can trigger various visual and functional changes on modern websites.
            This is essential for interacting with hover-activated UI components.
            
            Use hover to:
            - Reveal dropdown menus that appear on mouseover
            - Show tooltips with additional information
            - Trigger image galleries or preview overlays
            - Activate navigation submenus
            - Display interactive buttons or controls
            - Preview content before clicking
            - Activate hover effects that reveal clickable areas
            
            Args:
                bbox_id (int): The ID number of the element to hover over from page annotation.
                              Must correspond to a valid interactive element on the current page.
                              Valid range is 0 to (number of detected elements - 1).
            
            Returns:
                str: Success message "Hovered over element {bbox_id}" or error message
                     with details if the hover operation failed.
            
            Behavior Details:
            - Uses native Playwright hover() with 5-second timeout
            - Hover state persists until mouse moves elsewhere
            
            Important Notes:
            - Invalid bbox_id values will raise ValueError with valid range
            - Hover effects vary greatly between websites and elements
            - Some elements may require hover before becoming clickable
            - Mobile-responsive sites may not support hover interactions
            - Hover state is lost if you perform other mouse actions
            
            Common Patterns:
            1. **Navigation menus**: Hover over main menu items to reveal submenus
            2. **Image galleries**: Hover to show zoom or preview options
            3. **Tooltips**: Hover to read additional information
            4. **Interactive cards**: Hover to reveal action buttons
            5. **Form validation**: Some fields show help text on hover
            
            Troubleshooting:
            - If hover seems to have no effect, the element may not have hover styles
            - Some sites use click instead of hover for mobile compatibility
            - Hover effects may be disabled on touch devices
            - Complex hover interactions may require multiple hover calls
            """
            return await self.hover(bbox_id)

        @tool
        async def press_key(key: str) -> str:
            """Simulate a keyboard key press for navigation and interaction.
            
            This tool sends keyboard events directly to the browser, enabling
            keyboard-based navigation and interaction with web pages. It's essential
            for accessibility, form navigation, and triggering keyboard shortcuts.
            
            Use press_key for:
            - Form navigation (Tab, Shift+Tab to move between fields)
            - Submitting forms (Enter key)
            - Cancelling dialogs or modals (Escape key)
            - Page navigation (Page Up, Page Down, Home, End)
            - Arrow key navigation in menus, galleries, or lists
            - Triggering keyboard shortcuts and hotkeys
            - Accessibility navigation for screen readers
            
            Args:
                key (str): The key to press. Supports a wide range of keys:
                          
                          **Navigation Keys:**
                          - "Tab", "Shift+Tab" (move between focusable elements)
                          - "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"
                          - "Home", "End", "PageUp", "PageDown"
                          
                          **Action Keys:**
                          - "Enter" (submit forms, activate buttons)
                          - "Escape" (close modals, cancel operations)
                          - "Space" (activate checkboxes, scroll page)
                          
                          **Editing Keys:**
                          - "Backspace", "Delete"
                          - "Control+A" (select all), "Control+C" (copy), "Control+V" (paste)
                          - "Meta+A", "Meta+C", "Meta+V" (Mac equivalents)
                          
                          **Function Keys:**
                          - "F1" through "F12"
                          
                          **Character Keys:**
                          - Any single character: "a", "A", "1", "!", etc.
            
            Returns:
                str: Success message "Pressed key '{key}'" or error message
                     with details if the key press failed.
            
            Behavior Details:
            - Key press is sent to the currently focused element
            - If no element has focus, key press affects the page/window
            - Action count is incremented after successful key press
            - Key names are case-sensitive and must match Playwright conventions
            
            Important Notes:
            - Some key combinations may be intercepted by the browser
            - Certain keys may trigger page navigation (F5 for refresh)
            - Focus must be on appropriate element for keys to have effect
            - Modifier keys (Control, Shift, Alt) can be combined with other keys
            - Key behavior depends on the currently focused element type
            
            Troubleshooting:
            - If key has no effect, check if correct element has focus
            - Some keys may require specific focus context to work
            - Browser security may block certain key combinations
            - Custom JavaScript may override default key behavior
            """
            return await self.press_key(key)

        @tool
        async def drag(start_bbox_id: int, end_bbox_id: int) -> str:
            """Perform drag and drop operation between two elements.
            
            This tool simulates clicking and holding on one element, dragging it to
            another location, and releasing it. This is essential for interacting
            with drag-and-drop interfaces, reordering lists, and moving content.
            
            Use drag and drop for:
            - Reordering items in sortable lists
            - Moving files between folders in file managers
            - Rearranging dashboard widgets or panels
            - Dragging items into shopping carts
            - Organizing content in kanban boards or project tools
            - Adjusting sliders or range controls
            - Moving elements in design interfaces
            - Drag-to-select operations
            
            Args:
                start_bbox_id (int): The ID of the element to start dragging from.
                                   Must correspond to a draggable element on the current page.
                                   Valid range is 0 to (number of detected elements - 1).
                end_bbox_id (int): The ID of the element to drop onto (drop target).
                                 Must correspond to a valid drop zone or target element.
                                 Valid range is 0 to (number of detected elements - 1).
            
            Returns:
                str: Success message "Dragged element {start_bbox_id} to element {end_bbox_id}"
                     or error message with details if the drag operation failed.
            
            Behavior Details:
            - Uses native Playwright drag_and_drop() method
            - Automatically handles mouse down, move, and up events
            - Action count is incremented after successful drag operation
            - Both source and target elements must be valid and accessible
            
            Important Notes:
            - Invalid bbox_id values will raise ValueError with valid range
            - Both elements must exist and be visible on the page
            - Some drag operations may trigger page updates or animations
            - Not all elements support drag and drop (depends on implementation)
            - Source element must have draggable properties enabled
            - Target element must be a valid drop zone
            
            Drag and Drop Requirements:
            - **Source element** must be draggable (draggable="true" or CSS draggable)
            - **Target element** must accept drops (proper drop event handlers)
            - **JavaScript handlers** must be present to process the drop
            - **Browser support** for HTML5 drag and drop API
            
            Troubleshooting:
            - If drag fails, check if elements actually support drag/drop
            - Some interfaces use custom drag implementations that may not work
            - Try hover() on source element first to activate drag handles
            - Verify both source and target elements are currently visible
            - Some drag operations require specific mouse positions within elements
            
            Alternative Approaches:
            - For simple reordering, look for up/down arrow buttons
            - Some interfaces use context menus instead of drag/drop
            - Touch-based interfaces may use different interaction patterns
            """
            return await self.drag(start_bbox_id, end_bbox_id)

        @tool
        async def wait_for(
            time: Optional[float] = None,
            bbox_id: Optional[int] = None,
            state: str = "attached",
        ) -> str:
            """Wait for specific conditions to be met before proceeding with automation tasks.

            This tool provides flexible waiting mechanisms essential for handling dynamic content,
            slow-loading pages, and asynchronous operations. It supports both time-based delays
            and element state monitoring for robust automation workflows.

            ## Purpose & Use Cases

            **Dynamic Content Loading:**
            - Wait for AJAX requests and API calls to complete
            - Allow lazy-loaded images and content to appear
            - Wait for JavaScript-rendered content to become available
            - Handle progressive loading and content streaming
            - Wait for advertising and analytics scripts to finish loading

            **Element State Management:**
            - Wait for buttons and interactive elements to become clickable
            - Monitor for modal dialogs and popups to appear or disappear
            - Wait for form validation messages and error states
            - Track loading spinners and progress indicators
            - Monitor for content updates and state changes

            **Timing and Synchronization:**
            - Add strategic delays between rapid actions
            - Allow page transitions and animations to complete
            - Synchronize with external systems and services
            - Handle rate limiting and throttling requirements
            - Provide breathing room for complex page interactions

            ## Arguments

            **time** (float, optional):
            - Number of seconds to wait (supports decimals like 1.5, 2.3)
            - Valid range: 0.1 to 20.0 seconds (20 second maximum for safety)
            - Use for simple time-based delays and loading periods
            - Essential for allowing content to load after actions
            - If None, element-based waiting is used instead

            **bbox_id** (int, optional):
            - The ID number of the element to monitor from page annotation
            - Must correspond to a valid element detected on the page
            - Used with state parameter to wait for element changes
            - If None, time-based waiting is used instead

            **state** (str, optional):
            - `"attached"` (default): Wait for element to appear in the DOM
            - `"detached"`: Wait for element to disappear from the DOM
            - Only relevant when bbox_id is provided
            - Case-sensitive - must use exact strings
            - Timeout of 5 seconds maximum for element state changes

            ## Returns

            **Success responses:**
            - `"Waited for {time} seconds."` - Time-based wait completed
            - `"Waited for element {bbox_id} to appear."` - Element appeared successfully
            - `"Waited for element {bbox_id} to disappear."` - Element disappeared successfully

            **Error responses:**
            - `"Error: Time cannot be greater than 20 seconds"` - Time limit exceeded
            - `"Error: Time cannot be negative"` - Invalid negative time
            - `"Error: state must be 'attached' or 'detached'"` - Invalid state parameter
            - `"No wait condition provided."` - Neither time nor bbox_id specified
            - `"Error in wait_for: {details}"` - Element wait timeout or other failure

            ## Behavior Details

            **Time-Based Waiting:**
            - Converts time to milliseconds for precise Playwright timeout
            - Blocks execution for exactly the specified duration
            - Supports fractional seconds for fine-grained control

            **Element State Waiting:**
            - Uses Playwright's selector waiting with 5-second timeout
            - "attached" waits for element to become present in DOM
            - "detached" waits for element to be removed from DOM
            - Automatically handles dynamic element creation and removal
            - Fails gracefully if timeout exceeded

            **Wait Strategy Selection:**
            - If both time and bbox_id provided, time takes precedence
            - If neither provided, returns error message
            - Element waiting is more reliable for dynamic content
            - Time waiting is simpler but less adaptive

            ## Important Notes

            **Time Limits and Safety:**
            - 20-second maximum prevents infinite hangs
            - Consider shorter waits (1-5 seconds) for most use cases
            - Very long waits may indicate architectural problems
            - Use element waiting instead of long time waits when possible

            **Element State Monitoring:**
            - 5-second timeout prevents indefinite waiting for elements
            - Elements must be detectable by page annotation system
            - Some dynamically created elements may not be immediately detectable
            - State changes are detected through DOM monitoring

            **Performance Considerations:**
            - Time-based waits block all activity during wait period
            - Element waits are more efficient and responsive
            - Use shortest practical wait times to maintain performance
            - Consider async loading patterns when designing wait strategies

            ## Best Practices

            **Strategic Wait Placement:**
            - Add waits after actions that trigger loading (click, scroll, navigation)
            - Wait before accessing content that may not be immediately available
            - Use shorter waits (0.5-2 seconds) for most interactive elements
            - Reserve longer waits (3+ seconds) for major page changes

            **Choosing Wait Types:**
            - Use element waiting for predictable state changes
            - Use time waiting for general loading delays
            - Combine both types for robust handling of complex scenarios
            - Monitor actual page behavior to optimize wait strategies

            **Performance Optimization:**
            - Start with shorter waits and increase only if needed
            - Use element waiting to avoid unnecessary delays
            - Batch related actions to minimize total wait time
            - Monitor automation speed vs. reliability balance
            """
            return await self.wait_for(time=time, bbox_id=bbox_id, state=state)

        @tool
        async def browser_goto(url: str) -> str:
            """Navigate directly to a specific URL.
            
            It loads a completely new page, replacing the current content. Use this as your starting point for any web-based task.
            
            Navigation Features:
            - Automatic URL formatting (adds https:// if missing)
            - Human-like delays to appear natural (2-5 seconds)
            - Automatic page load waiting (2 second settle time)
            
            Use browser_goto for:
            - **Research and fact-checking**: Visit sources to verify information
            - **Starting new tasks**: Navigate to target websites or applications
            - **Following links**: Go to specific URLs found in content
            - **Accessing services**: Navigate to login pages, dashboards, tools
            - **Comparative analysis**: Visit multiple sites for comparison
            - **Direct access**: Navigate to known URLs without searching
            
            Args:
                url (str): The URL to navigate to. Supports various formats:
                          - Full URLs: "https://example.com/page"
                          - URLs without protocol: "example.com" (https:// added automatically)
                          - URLs with paths: "site.com/products/category"
                          - URLs with parameters: "site.com/search?q=term"
                          - Subdomains: "api.example.com", "shop.example.com"
                          
            Returns:
                str: Success message "Successfully navigated to {url}" or error message
                     with details if navigation failed.
            
            Important Notes:
            - Navigation replaces current page content completely
            - All previous page state (scroll position, form data) is lost
            - Some sites may redirect to different URLs after navigation
            - Authentication may be required for restricted content
            - Page loading time varies based on content size and complexity
            - JavaScript-heavy sites may need additional time to fully load
            
            Common Navigation Scenarios:
            - **Product research**: Navigate to e-commerce sites for pricing
            - **News verification**: Visit news sources for current information
            - **Documentation**: Access API docs, manuals, guides
            - **Service access**: Navigate to web applications and tools
            - **Comparative analysis**: Visit competitor sites for analysis
            - **Contact information**: Navigate to official contact/about pages
            
            Error Conditions:
            - Network connectivity issues
            - Invalid or malformed URLs
            - Sites that block automated access
            - SSL certificate problems
            - Timeouts on slow-loading pages
            - Geographic restrictions or IP blocking
            
            **Remember: This tool is essential for credible information gathering.
            Always navigate to verify facts rather than relying on assumptions.**
            """
            return await self.browser_goto(url)

        @tool
        async def browser_select_option(bbox_id: int, values: List[str]) -> str:
            """Select options from dropdown menus and select elements with hybrid execution strategy.

            This tool handles dropdown selection using Kagebunshin's dual-approach system, attempting 
            fast native Playwright selection first, then falling back to human-like mouse interactions 
            if needed. Essential for form completion, filtering, and configuration selections.

            ## Purpose & Use Cases

            **Form Completion:**
            - Select country, state, or region from dropdown lists
            - Choose categories, departments, or classifications
            - Pick dates, times, or time zones from select elements
            - Select payment methods, shipping options, or preferences
            - Choose file types, formats, or export options

            **Filtering and Search:**
            - Apply filters by category, price range, or attributes
            - Select sorting options (newest, oldest, price, rating)
            - Choose display options (list view, grid view, per page)
            - Apply search refinements and advanced criteria
            - Select report parameters and data ranges

            **Configuration and Settings:**
            - Choose application settings and preferences
            - Select themes, languages, or display options
            - Pick notification settings and privacy levels
            - Configure account settings and profile options
            - Choose integration and connection options

            ## Arguments

            **bbox_id** (int, required):
            - The ID number of the select/dropdown element from page annotation
            - Must correspond to a `<select>` element or dropdown component
            - Valid range is 0 to (number of detected elements - 1)
            - Invalid IDs will raise ValueError with valid range information

            **values** (List[str], required):
            - List of option values to select (supports single or multiple selections)
            - Values should match the HTML `value` attributes of `<option>` elements
            - For single-select dropdowns: provide list with one value `["option1"]`
            - For multi-select elements: provide multiple values `["option1", "option2"]`
            - Empty list `[]` will clear all selections
            - Case-sensitive - must match exact option values

            ## Returns

            **Success responses:**
            - `"Successfully selected {values} in element {bbox_id}."` - Native selection succeeded
            - `"Successfully selected {values} in element {bbox_id} using fallback."` - Human-like fallback succeeded

            **Error responses:**
            - `"Error: Selecting in element {bbox_id} had no effect on the page."` - Selection registered but no page change
            - `"Error: All select attempts failed for element {bbox_id}. Last error: {details}"` - Complete failure

            ## Behavior Details

            **Multi-Select Support:**
            - Handles both single-select (`<select>`) and multi-select (`<select multiple>`) elements
            - For multi-select: all specified values are selected simultaneously
            - Previous selections may be cleared or maintained depending on element behavior
            - Native method handles multi-select efficiently in single operation

            **Option Value Matching:**
            - Values must match HTML `value` attributes exactly (case-sensitive)
            - If option has no explicit value, uses the visible text as value
            - Some dropdowns use numeric IDs or codes as values
            - Custom dropdown components may have non-standard value formats

            ## Important Notes
            **State Change Detection:**
            - Selection is considered successful only if page state changes
            - Some dropdowns trigger immediate form submission or page updates
            - Others may require additional action (button click) to apply selection
            - Changes include DOM updates, AJAX requests, or visual state changes

            ## Troubleshooting

            **"Selection had no effect":**
            - Selected values may not exist in the dropdown options
            - Dropdown may require additional action (Apply button) after selection
            - Some dropdowns are disabled or read-only
            - JavaScript may prevent selection or override the choice

            **Values not found or invalid:**
            - Use extract_page_content() to inspect available option values
            - Check HTML source to find exact `value` attributes
            - Some options may be dynamically loaded after opening dropdown
            - Custom dropdowns may use different value formats

            **Multiple selection issues:**
            - Verify the element supports multiple selections (`<select multiple>`)
            - Some elements clear previous selections when new ones are made
            - Order of values in list may matter for some implementations
            - Try selecting options individually if batch selection fails

            ## Best Practices

            **Value Discovery:**
            - Use extract_page_content() or hover() to reveal available options
            - Inspect element HTML to find correct value attributes
            - Test with simple, common values first (like "1", "yes", "true")
            - Watch for dynamic loading of dropdown options

            **Form Workflow:**
            - Select dropdown options before filling related text fields
            - Some dropdowns may affect what other fields are available
            - Complete dropdowns in logical order (country → state → city)
            - Verify selection success before proceeding to dependent fields

            **Error Recovery:**
            - If native selection fails, human-like fallback runs automatically
            - For persistent failures, try clicking dropdown first with click()
            - Consider using hover() to activate dropdown before selection
            - Use refresh() if dropdown seems broken or unresponsive

            ## Advanced Features

            **Dynamic Dropdown Handling:**
            - Handles dropdowns that load options via AJAX
            - Works with cascading dropdowns that update based on previous selections
            - Supports dropdowns that filter or search as you type
            - Compatible with modern framework dropdown components

            **Anti-Detection Integration:**
            - Human-like fallback uses realistic mouse movement and timing
            - Variable delays and natural interaction patterns
            - Random click positioning within dropdown bounds
            - Maintains consistent behavioral patterns with other tools

            **Multi-Framework Support:**
            - Works with standard HTML select elements
            - Compatible with popular frameworks (Bootstrap, Material UI)
            - Handles custom styled dropdowns when they follow standard patterns
            - Adapts to different dropdown implementations automatically
            """
            return await self.browser_select_option(bbox_id, values)

        @tool
        async def list_tabs() -> str:
            """Get detailed browser tab information when basic tab overview is insufficient.
            
            ⚠️  **IMPORTANT**: Basic tab information is already included in your context window! 
            Only use this tool when you need MORE DETAILED tab information than what's already available.
            
            **When to use this tool:**
            - Need full URLs for specific tabs (not shown in basic context)
            - Need to search for tabs by specific URL patterns or domains
            - Debugging complex multi-tab issues or missing tabs
            - Need comprehensive tab audit for cleanup operations
            - Investigating tab-related problems or unexpected behavior
            
            Returns:
                str: Formatted list of all tabs showing:
                     - Tab index (0-based, used with other tab tools)
                     - Page title
                     - Full URL
                     - "(ACTIVE)" marker for the currently focused tab
                     
                     Format example:
                     "Available tabs:
                       0: Search Results - Google Search - https://google.com/search?q=... (ACTIVE)
                       1: Product Details - Amazon.com - https://amazon.com/dp/product-id
                       2: Pricing Comparison - Best Buy - https://bestbuy.com/product/..."
                     
                     Or "No tabs found." if no tabs are available.
            
            Tab Information Details:
            - **Tab Index**: 0-based numbering for use with other tab tools
            - **Title**: Page title as reported by the browser
            - **URL**: Full URL of the page
            - **Active Status**: Shows which tab is currently focused and receiving actions
            
            Important Notes:
            - Tab indices start at 0 (first tab is index 0)
            - Active tab receives all browser actions (click, type, etc.)
            - Tab order may change as tabs are opened and closed
            
            Best Practices:
            - Call list_tabs() in order to get detailed tab information
            - Use tab titles and URLs to identify the correct tab
            - Note the active tab before switching to ensure you can return
            
            Common Tab States:
            - **Single tab**: Normal browsing, all actions go to one page
            - **Multiple tabs**: Need to track which tab is active
            - **New tabs from clicks**: Links may open in new tabs automatically
            - **Background tabs**: Tabs that loaded but aren't currently active
            """
            return await self.list_tabs()

        @tool
        async def switch_tab(tab_index: int) -> str:
            """Switch to a specific browser tab by its index number.
            
            This tool changes the active tab, directing all subsequent browser actions
            (click, type, scroll, etc.) to the specified tab. Essential for multi-tab
            workflows and parallel browsing tasks.
            
            Use switch_tab when:
            - Working with multiple tabs simultaneously
            - Comparing information across different pages
            - Returning to a previously opened tab
            - Managing parallel browsing workflows
            - Accessing background tabs that were opened earlier
            - Organizing multi-step research across different sources
            
            Args:
                tab_index (int): The 0-based index number of the tab to switch to.
                                Use list_tabs() first to see available tabs and their indices.
                                Valid range is 0 to (number of tabs - 1).
                                
            Returns:
                str: Success message "Successfully switched to tab {index}: {title}" or 
                     error message if the switch failed or tab index is invalid.
            
            Tab Switching Behavior:
            - **Focus change**: The specified tab becomes the active tab
            - **Action redirection**: All subsequent tools operate on the new active tab
            - **Visual activation**: The tab is brought to the front (becomes visible)
            - **State preservation**: Previous tab remains loaded in background
            - **Action counting**: Tab switches increment the action counter
            
            Important Notes:
            - Invalid tab indices will return an error with valid range information
            - The active tab receives all browser actions after switching
            - Background tabs remain loaded and maintain their state
            - Some tabs may take time to fully re-render when switching
            
            Error Conditions:
            - Tab index out of range (negative or >= number of tabs)
            - Tab has been closed since list_tabs() was called
            - Browser context has been destroyed
            - Network issues preventing tab activation
            
            **Common Multi-Tab Scenarios:**
            - **Price comparison**: Multiple store tabs for comparison
            - **Research verification**: Multiple source tabs for fact-checking
            - **Form management**: Multiple application forms in parallel
            - **Documentation**: One tab for research, one for note-taking
            - **Workflow coordination**: Main task tab plus reference tabs
            """
            return await self.switch_tab(tab_index)

        @tool
        async def open_new_tab(url: str = None) -> str:
            """Open a new browser tab, optionally navigating to a specific URL.
            
            This tool creates a fresh browser tab and optionally loads a specific page.
            The new tab becomes the active tab automatically, directing all subsequent
            browser actions to it. Essential for parallel browsing and multi-tab workflows.
            
            Use open_new_tab for:
            - **Parallel research**: Open multiple sources for comparison
            - **Background loading**: Load pages while working on current tab
            - **Workflow separation**: Keep different tasks in separate tabs
            - **Reference keeping**: Open documentation or help pages
            - **Comparison shopping**: Open multiple product/service pages
            - **Multi-step processes**: Separate form filling or application processes
            - **Backup navigation**: Keep original page while exploring links
            
            Args:
                url (str, optional): URL to navigate to in the new tab. If provided:
                                   - Supports same URL formats as browser_goto()
                                   - Automatically adds https:// if missing
                                   - Can be full URLs, domains, or paths
                                   - Examples: "google.com", "https://example.com/page"
                                   
                                   If None or not provided:
                                   - Creates blank tab (about:blank or similar)
                                   - You can navigate later using browser_goto()
                                   - Useful for preparing tabs before navigation
                                   
            Returns:
                str: Success message indicating the new tab was created:
                     - "Successfully opened new tab (index {N})" (no URL provided)
                     - "Successfully opened new tab (index {N}) and navigated to {url}" (with URL)
                     - Error message if tab creation or navigation failed
            
            New Tab Behavior:
            - **Automatic activation**: New tab becomes the active tab immediately
            - **Fresh context**: New tab starts with clean state (no history, cookies isolated)
            - **Index assignment**: New tab gets the highest index number
            - **Action redirection**: All subsequent tools operate on the new tab
            - **Resource allocation**: New tab consumes browser memory and resources
            
            Important Notes:
            - New tab automatically becomes active (no need to call switch_tab)
            - If URL is provided, navigation happens automatically
            - URL navigation follows same rules as browser_goto() (timeouts, redirects, etc.)
            - Tab receives fingerprint evasion and stealth settings
            - Action count is incremented after successful tab creation
            - Too many tabs can impact browser performance
            
            Best Practices:
            - Plan your multi-tab strategy before opening many tabs
            - Use descriptive take_note() calls to track tab purposes
            - Close tabs when no longer needed to free resources
            - Consider whether you need the tab immediately or can open it later
            
            Error Conditions:
            - Browser context limit reached (too many tabs)
            - Invalid URL format (when URL provided)
            - Network issues preventing navigation
            - Memory limitations preventing new tab creation
            - Security restrictions blocking tab creation
            """
            return await self.open_new_tab(url)

        @tool
        async def close_tab(tab_index: int = None) -> str:
            """Close a browser tab by its index, or close the current tab if no index specified.
            
            This tool removes a tab from the browser, freeing up resources and cleaning up
            the browsing session. Essential for managing multi-tab workflows and preventing
            resource exhaustion from too many open tabs.
            
            Use close_tab to:
            - **Clean up workflow**: Remove tabs no longer needed
            - **Free resources**: Reduce browser memory and CPU usage
            - **Organize session**: Keep only relevant tabs open
            - **End parallel tasks**: Close completed comparison or research tabs
            - **Manage tab overflow**: Prevent too many tabs from slowing browser
            - **Complete workflows**: Close temporary or single-use tabs
            - **Error recovery**: Close problematic tabs that aren't working
            
            Args:
                tab_index (int, optional): The 0-based index of the tab to close.
                                         Use list_tabs() first to see available tabs.
                                         If None or not provided, closes the currently active tab.
                                         Must be a valid tab index (0 to number of tabs - 1).
                                         
            Returns:
                str: Success message "Successfully closed tab {index}: {title}" or
                     error message if closing failed or tab index is invalid.
            
            Tab Closing Behavior:
            - **Resource cleanup**: Tab memory and processes are freed
            - **Automatic switching**: If current tab is closed, switches to first available tab
            - **Index adjustment**: Remaining tabs may have their indices renumbered
            - **State preservation**: Other tabs remain unaffected
            - **Action counting**: Tab closure increments the action counter
            - **Safety protection**: Cannot close the last remaining tab
            
            Important Notes:
            - Cannot close the last remaining tab (browser must have at least one tab)
            - If closing the current tab, automatically switches to another tab
            - Tab indices may change after closing a tab (tabs get renumbered)
            - Any unsaved data in the closed tab will be lost
            - Background processes in the closed tab are terminated
            
            **Best Practices for Tab Management:**
            
            **Strategic Closing:**
            - Close tabs immediately after extracting needed information
            - Don't accumulate many tabs - close as you go
            - Keep only essential tabs open at any time
            - Close tabs in reverse order to avoid index confusion
            
            **Remember:** Closing tabs is permanent - any unsaved data will be lost.
            Always extract needed information before closing tabs.
            """
            return await self.close_tab(tab_index)

        @tool
        def take_note(note: str) -> str:
            """Record important information or observations for future reference.
            
            This tool provides a way to maintain context and memory throughout
            a browsing session by recording key findings, progress updates,
            and important observations that may be useful later.
            
            Use take_note to:
            - Record important findings or data discovered during browsing
            - Track progress through multi-step tasks or workflows
            - Note down URLs, contact information, or reference data
            - Record error conditions or issues encountered
            - Mark successful completion of subtasks or milestones
            - Document patterns or insights discovered during research
            - Create reminders for follow-up actions
            - Log decision points and reasoning
            
            Args:
                note (str): The note content to record. Can include:
                          - Factual observations ("Found price: $29.99")
                          - Progress updates ("Completed login successfully")
                          - Reference information ("Contact email: support@example.com")
                          - Error details ("Submit button not working, trying alternative")
                          - Strategy notes ("Need to scroll down to load more products")
                          - Timestamps or sequence information
                          - Any other contextual information
            
            Returns:
                str: Confirmation message "Note recorded." indicating the note
                     has been successfully logged.
            
            Note Behavior:
            - Notes persist for the duration of the current session
            - Notes help maintain context across long browsing sessions
            
            Best Practices:
            - Use clear, descriptive language in notes
            - Include relevant context (page URLs, element descriptions)
            - Note both successes and failures for complete picture
            - Use consistent formatting for similar types of notes
            - Record timestamps or sequence information when relevant
            - Include specific data values when discovered
            
            Note Categories:
            - **Progress**: "Completed login process", "Navigated to products page"
            - **Findings**: "Price: $29.99", "Contact: support@example.com"
            - **Issues**: "Button not responsive", "Page loading slowly"
            - **Strategy**: "Will try alternative search approach"
            - **Context**: "This is the checkout page", "User logged in successfully"
            """
            return self.take_note(note)

        @tool
        def get_performance_stats() -> str:
            """Get performance optimization statistics and insights.
            
            Returns detailed information about the performance optimizer's current state,
            including site-specific performance profiles, success rates, and optimization
            statistics. Useful for debugging performance issues and understanding
            how the system is learning from interactions.
            
            Returns:
                str: JSON-formatted performance statistics including:
                     - Current performance mode (stealth/balanced/fast)
                     - Overall native success rates
                     - Site-specific performance profiles
                     - Cache statistics
                     - Total actions performed
            """
            stats = self.get_performance_stats()
            return f"Performance Statistics:\n{stats}"

        @tool
        def reset_performance_cache() -> str:
            """Clear all performance optimization cache and learning data.
            
            Resets the performance optimizer to its initial state by clearing:
            - Element selector cache
            - Site-specific performance profiles
            - Interaction history and statistics
            
            This can be useful when:
            - Performance optimization seems to be making poor decisions
            - You want to start fresh with performance learning
            - Testing different optimization strategies
            - Site behavior has changed significantly
            
            Returns:
                str: Confirmation message of cache reset operation
            """
            return self.reset_performance_cache()

        @tool
        async def complete_task(status: str, result: str, confidence: Optional[float] = None) -> str:
            """Complete the current task with structured output and terminate the agent workflow.
            
            This tool provides explicit, intentional task completion with structured output.
            Use this tool when you have finished your mission, encountered an insurmountable obstacle,
            or need to provide a final answer to the user. This will be the final message shown to the user.
            
            ## Purpose & Use Cases
            
            **Primary Completion Scenarios:**
            - Successfully completed the user's request
            - Task partially completed with clear limitations
            - Unable to continue due to technical barriers
            - Blocked by authentication, permissions, or access issues
            
            ## Arguments
            
            **status** (str, required):
            - "success": Task completed successfully as requested.
            - "partial": Task partially completed with limitations.
            - "failure": Task failed due to technical issues.
            - "blocked": Unable to proceed due to external constraints.
            
            **result** (str, required):
            - Final answer, explanation, or summary of outcomes in **markdown format**.
            - This can be AS LONG AS YOU WANT! Do not truncate/summarize the result.
            - Should be comprehensive and user-facing.
            - Include relevant data, findings, or completed actions.
            - Explain any limitations or next steps if applicable.
            
            **confidence** (float, optional):
            - Confidence score between 0.0 (low) and 1.0 (high).
            - Only provide if you can meaningfully assess certainty.
            - Consider factors like data completeness, verification level.
            - Omit if confidence assessment isn't applicable.
            
            ## Note: there is no length limit for **result**. If you need to provide a long answer, provide a long answer.
            
            ## Returns
            
            **Confirmation message** and terminates the agent workflow.
            The structured completion data is stored in the conversation state
            for extraction by the orchestrator and downstream systems.
            """
            # Validate status
            valid_statuses = {"success", "partial", "failure", "blocked"}
            if status not in valid_statuses:
                return f"Error: status must be one of {valid_statuses}, got '{status}'"
            
            # Validate confidence if provided
            if confidence is not None:
                if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                    return f"Error: confidence must be a number between 0.0 and 1.0, got {confidence}"
            
            # Store completion data in state for extraction
            self.completion_data = {
                "status": status,
                "result": result,
                "confidence": confidence,
                "completed_at": time.time()
            }
            
            # Format confirmation message
            confidence_text = f" (confidence: {confidence:.0%})" if confidence is not None else ""
            return f"Task completed with status '{status}'{confidence_text}. Result: {result}"

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
            take_note,
            get_performance_stats,
            reset_performance_cache,
            complete_task
        ]