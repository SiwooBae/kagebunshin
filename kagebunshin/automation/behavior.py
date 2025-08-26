"""
Human-like behavior simulation for web automation.

This module contains functions that simulate realistic human interactions
to avoid bot detection in web automation scenarios.
"""

import random
import asyncio
from playwright.async_api import Page


from ..config.settings import ACTIVATE_HUMAN_BEHAVIOR, DELAY_PROFILES


async def human_delay(min_ms: int = 100, max_ms: int = 500, profile: str = "normal"):
    """Add random delay to simulate human thinking/reaction time"""
    if not ACTIVATE_HUMAN_BEHAVIOR:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        return
        
    # Use profile-specific delay if provided
    if profile in DELAY_PROFILES:
        profile_config = DELAY_PROFILES[profile]
        if "action_delay_range" in profile_config:
            min_sec, max_sec = profile_config["action_delay_range"]
            delay = random.uniform(min_sec, max_sec)
            await asyncio.sleep(delay)
            return
    
    # Fallback to provided parameters
    delay = random.uniform(min_ms / 1000, max_ms / 1000)
    await asyncio.sleep(delay)


def get_random_offset_in_bbox(bbox, padding: int = 5):
    """Get random coordinates within a bounding box, avoiding exact center"""
    # Add some padding to avoid clicking too close to edges
    # Calculate width and height from bbox coordinates
    width = max(20, 40)  # Use default width
    height = max(20, 20)  # Use default height
    
    # Calculate random offsets within the bbox
    offset_x = random.randint(-width//4, width//4)
    offset_y = random.randint(-height//4, height//4)
    
    return bbox.x + offset_x, bbox.y + offset_y


async def human_mouse_move(page: Page, start_x: float, start_y: float, end_x: float, end_y: float, profile: str = "normal"):
    """Move mouse in a more human-like path with slight curves"""
    if not ACTIVATE_HUMAN_BEHAVIOR:
        await page.mouse.move(end_x, end_y)
        return
        
    # Use profile-specific settings
    steps = random.randint(3, 7)
    step_delay_range = (0.01, 0.03)
    
    if profile in DELAY_PROFILES:
        profile_config = DELAY_PROFILES[profile]
        if "click_delay_range" in profile_config:
            step_delay_range = (
                profile_config["click_delay_range"][0] * 0.5,
                profile_config["click_delay_range"][1] * 0.5
            )
    
    for i in range(steps):
        progress = (i + 1) / steps
        # Add slight curve/jitter to movement
        jitter_x = random.uniform(-2, 2) if i < steps - 1 else 0
        jitter_y = random.uniform(-2, 2) if i < steps - 1 else 0
        
        current_x = start_x + (end_x - start_x) * progress + jitter_x
        current_y = start_y + (end_y - start_y) * progress + jitter_y
        
        await page.mouse.move(current_x, current_y)
        await asyncio.sleep(random.uniform(step_delay_range[0], step_delay_range[1]))


async def human_type_text(page: Page, text: str, profile: str = "normal"):
    """Type text character by character with human-like timing variations"""
    if not ACTIVATE_HUMAN_BEHAVIOR:
        await page.keyboard.insert_text(text)
        return
        
    # Check if profile disables human typing
    if profile in DELAY_PROFILES:
        profile_config = DELAY_PROFILES[profile]
        if not profile_config.get("use_human_typing", True):
            await page.keyboard.insert_text(text)
            return
        
        # Use profile-specific typing delay range
        if "type_delay_range" in profile_config:
            base_delay_range = profile_config["type_delay_range"]
        else:
            base_delay_range = (0.05, 0.15)
    else:
        base_delay_range = (0.05, 0.15)
    
    for i, char in enumerate(text):
        # Vary typing speed - faster for common letter combinations, slower for complex ones
        base_delay = random.uniform(base_delay_range[0], base_delay_range[1])
        
        # Add occasional longer pauses (thinking/hesitation) for human profiles
        if profile in ["normal", "human", "adaptive"] and random.random() < 0.1:  # 10% chance of longer pause
            base_delay += random.uniform(0.2, 0.8)
        
        # Slightly faster after getting into rhythm
        if i > 3:
            base_delay *= 0.8
            
        # Slower for special characters
        if not char.isalnum() and char != ' ':
            base_delay *= 1.5
            
        await page.keyboard.type(char)
        await asyncio.sleep(base_delay)


async def human_scroll(page: Page, x: float, y: float, direction: str, amount: int, profile: str = "normal"):
    """Perform human-like scrolling with multiple small increments"""
    if not ACTIVATE_HUMAN_BEHAVIOR:
        scroll_direction = -amount if direction.lower() == "up" else amount
        await page.mouse.wheel(0, scroll_direction)
        return
    
    # Check if profile disables human scrolling
    if profile in DELAY_PROFILES:
        profile_config = DELAY_PROFILES[profile]
        if not profile_config.get("use_human_scrolling", True):
            scroll_direction = -amount if direction.lower() == "up" else amount
            await page.mouse.wheel(0, scroll_direction)
            return
        
        # Use profile-specific scroll delay range
        if "scroll_delay_range" in profile_config:
            scroll_delay_range = profile_config["scroll_delay_range"]
        else:
            scroll_delay_range = (0.05, 0.15)
    else:
        scroll_delay_range = (0.05, 0.15)
        
    total_amount = amount + random.randint(-amount//4, amount//4)  # Add variation
    increments = random.randint(3, 8)  # Break into multiple scroll actions
    
    # Faster profiles use fewer increments
    if profile in ["minimal", "fast"]:
        increments = random.randint(2, 4)
    
    for i in range(increments):
        increment_amount = total_amount // increments
        if i == increments - 1:  # Last increment gets any remainder
            increment_amount = total_amount - (increment_amount * (increments - 1))
        
        scroll_direction = -increment_amount if direction.lower() == "up" else increment_amount
        await page.mouse.wheel(0, scroll_direction)
        
        # Random delay between scroll increments
        await asyncio.sleep(random.uniform(scroll_delay_range[0], scroll_delay_range[1]))


async def calculate_reading_time(page: Page):
    """Calculate realistic reading time based on page content"""
    if not ACTIVATE_HUMAN_BEHAVIOR:
        return 0.1
    
    content_analysis = await page.evaluate("""
        (() => {
            const textContent = document.body.innerText || '';
            const wordCount = textContent.split(/\\s+/).filter(word => word.length > 0).length;
            const imageCount = document.querySelectorAll('img').length;
            const linkCount = document.querySelectorAll('a').length;
            const isFormPage = document.querySelectorAll('form, input, textarea, select').length > 0;
            
            return {
                wordCount,
                imageCount, 
                linkCount,
                isFormPage,
                textLength: textContent.length
            };
        })()
    """)
    
    word_count = content_analysis.get('wordCount', 0)
    image_count = content_analysis.get('imageCount', 0)
    is_form_page = content_analysis.get('isFormPage', False)
    
    # Base reading time (average 225 words per minute)
    base_reading_time = max(2, word_count / 225 * 60)  # seconds
    
    # Add time for images (2-3 seconds per image)
    image_time = image_count * random.uniform(2, 3)
    
    # Add extra time for form pages (people spend more time on forms)
    form_time = random.uniform(5, 15) if is_form_page else 0
    
    # Add human variation (some people read faster/slower)
    human_factor = random.uniform(0.4, 2.5)
    
    total_time = (base_reading_time + image_time + form_time) * human_factor
    
    # Reasonable bounds (2 seconds to 2 minutes)
    return max(2, min(120, total_time))


async def smart_delay_between_actions(action_type: str, page_complexity: str = "medium", profile: str = "normal"):
    """Calculate smart delays based on action type, page complexity, and performance profile"""
    if not ACTIVATE_HUMAN_BEHAVIOR:
        await asyncio.sleep(random.uniform(0.05, 0.1))
        return
    
    # Use profile-specific delays if available
    if profile in DELAY_PROFILES:
        profile_config = DELAY_PROFILES[profile]
        
        # Map action types to profile delay ranges
        delay_key_mapping = {
            "click": "click_delay_range",
            "type": "type_delay_range",
            "scroll": "scroll_delay_range", 
            "navigate": "navigate_delay_range",
            "read": "action_delay_range"  # Generic fallback
        }
        
        delay_key = delay_key_mapping.get(action_type, "action_delay_range")
        
        # For adaptive profile, use base ranges
        if profile == "adaptive":
            delay_key = f"base_{delay_key}"
        
        if delay_key in profile_config:
            min_delay, max_delay = profile_config[delay_key]
        else:
            # Fallback to default ranges
            base_delays = {
                "click": (0.5, 2.0),
                "type": (1.0, 3.0), 
                "scroll": (0.3, 1.5),
                "navigate": (2.0, 5.0),
                "read": (3.0, 8.0)
            }
            min_delay, max_delay = base_delays.get(action_type, (0.5, 2.0))
    else:
        # Fallback to original logic
        base_delays = {
            "click": (0.5, 2.0),
            "type": (1.0, 3.0), 
            "scroll": (0.3, 1.5),
            "navigate": (2.0, 5.0),
            "read": (3.0, 8.0)
        }
        min_delay, max_delay = base_delays.get(action_type, (0.5, 2.0))
    
    # Apply complexity multipliers
    complexity_multipliers = {
        "simple": 0.7,
        "medium": 1.0,
        "complex": 1.4
    }
    
    multiplier = complexity_multipliers.get(page_complexity, 1.0)
    
    # Fast profiles get reduced complexity impact
    if profile in ["minimal", "fast"]:
        multiplier = 1.0 + (multiplier - 1.0) * 0.5
    
    delay = random.uniform(min_delay, max_delay) * multiplier
    await asyncio.sleep(delay) 