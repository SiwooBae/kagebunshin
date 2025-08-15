"""
Browser fingerprint randomization and evasion techniques.

This module contains functions that randomize browser fingerprints
and implement evasion techniques to avoid bot detection.
"""

import logging
import random
from playwright.async_api import Page, BrowserContext
from typing import Dict, Any, Optional
from ..config.settings import FINGERPRINT_PROFILES, FINGERPRINT_CUSTOMIZATION, STEALTH_ARGS, HUMAN_BEHAVIOR_SEED

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', filename='fingerprint.log')


async def apply_fingerprint_profile(page: Page, seed=HUMAN_BEHAVIOR_SEED):
    """
    Applies a consistent, randomized browser fingerprint and headers from a profile.
    This includes setting a user agent, HTTP headers, and overriding JavaScript
    properties like screen size, hardware, timezone, and plugins to mimic a
    real user's environment.
    """
    if seed is not None:
        rng = random.Random(seed)
        profile = rng.choice(FINGERPRINT_PROFILES)
    else:
        profile = random.choice(FINGERPRINT_PROFILES)
    logging.info(f"Using fingerprint profile: {profile.get('name', 'Unnamed Profile')}")
    
    # 1. Set HTTP Headers from the profile
    # Base headers that are common across browsers
    base_headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': profile["user_agent"],
    }
    # Merge with profile-specific headers
    final_headers = {**base_headers, **profile.get("headers", {})}
    await page.set_extra_http_headers(final_headers)

    # 2. Prepare JavaScript overrides via add_init_script
    screen_config = profile["screen"]
    hardware = profile["hardware"]
    timezone_offset = profile["timezone_offset"]
    languages = str(profile["language_list"]) # Must be a string representation of a list for JS
    
    # Noise values for canvas/audio from customization config
    canvas_prob = FINGERPRINT_CUSTOMIZATION["canvas_noise_probability"]
    audio_noise = FINGERPRINT_CUSTOMIZATION["audio_noise_range"][1]

    await page.add_init_script(f"""
        // --- Basic Evasion ---
        // Pass the webdriver check
        Object.defineProperty(navigator, 'webdriver', {{
          get: () => false,
        }});

        // --- Spoofing from Profile ---
        // Screen properties
        Object.defineProperty(screen, 'width', {{ get: () => {screen_config['width']} }});
        Object.defineProperty(screen, 'height', {{ get: () => {screen_config['height']} }});
        Object.defineProperty(screen, 'availWidth', {{ get: () => {screen_config['width']} }});
        Object.defineProperty(screen, 'availHeight', {{ get: () => {screen_config.get('height', 1080) - 40} }});
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {screen_config.get('colorDepth', 24)} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {screen_config.get('pixelDepth', 24)} }});
        
        // Navigator properties
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hardware['cores']} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {hardware['memory']} }});
        Object.defineProperty(navigator, 'platform', {{ get: () => '{hardware['platform']}' }});
        Object.defineProperty(navigator, 'language', {{ get: () => '{languages.split(',')[0].strip("[]' ")}' }});
        Object.defineProperty(navigator, 'languages', {{ get: () => {languages} }});

        // Timezone
        Date.prototype.getTimezoneOffset = function() {{ return {timezone_offset}; }};

        // --- Noise-based Evasion ---
        // Canvas fingerprinting protection
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {{
            const originalResult = originalToDataURL.apply(this, arguments);
            return originalResult.slice(0, -10) + Math.random().toString(36).slice(2);
        }};
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function() {{
            const result = originalGetImageData.apply(this, arguments);
            for (let i = 0; i < result.data.length; i += 4) {{
                if (Math.random() < {canvas_prob}) {{
                    result.data[i] = Math.min(255, result.data[i] + (Math.random() - 0.5) * 2);
                }}
            }}
            return result;
        }};
        
        // WebGL fingerprinting protection
        try {{
            const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                // UNMASKED_VENDOR_WEBGL
                if (parameter === 37445) {{ return 'Intel Open Source Technology Center'; }}
                // UNMASKED_RENDERER_WEBGL
                if (parameter === 37446) {{ return 'Mesa DRI Intel(R) Ivybridge Mobile '; }}
                return originalGetParameter.apply(this, arguments);
            }};
        }} catch (e) {{ /* ignore */ }}

        // Audio context fingerprinting protection
        const originalCreateAnalyser = AudioContext.prototype.createAnalyser;
        AudioContext.prototype.createAnalyser = function() {{
            const analyser = originalCreateAnalyser.apply(this, arguments);
            const originalGetFloatFrequencyData = analyser.getFloatFrequencyData;
            analyser.getFloatFrequencyData = function(array) {{
                const result = originalGetFloatFrequencyData.apply(this, arguments);
                for (let i = 0; i < array.length; i++) {{
                    array[i] += (Math.random() - 0.5) * {audio_noise};
                }}
                return result;
            }};
            return analyser;
        }};

        // Plugin array spoofing
        Object.defineProperty(navigator, 'plugins', {{
            get: () => [
                {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' }},
                {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' }},
                {{ name: 'Native Client', filename: 'internal-nacl-plugin' }}
            ],
        }});
    """)

def get_random_fingerprint_profile(seed: Optional[int] = HUMAN_BEHAVIOR_SEED) -> Dict[str, Any]:
    """Return a random fingerprint profile (optionally seeded for reproducibility)."""
    if seed is not None:
        rng = random.Random(seed)
        return rng.choice(FINGERPRINT_PROFILES)
    return random.choice(FINGERPRINT_PROFILES)


async def apply_fingerprint_profile_to_context(
    context: BrowserContext,
    seed: Optional[int] = HUMAN_BEHAVIOR_SEED,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply a consistent fingerprint profile at the context level so it affects all pages.

    Returns the profile used so callers can optionally align context UA/locale/viewport.
    """
    if profile is None:
        profile = get_random_fingerprint_profile(seed)
    logging.info(f"Using context fingerprint profile: {profile.get('name', 'Unnamed Profile')}")

    # 1) HTTP headers
    base_headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': profile["user_agent"],
    }
    final_headers = {**base_headers, **profile.get("headers", {})}
    await context.set_extra_http_headers(final_headers)

    # 2) JS overrides via add_init_script
    screen_config = profile["screen"]
    hardware = profile["hardware"]
    timezone_offset = profile["timezone_offset"]
    languages = str(profile["language_list"])  # JS needs string representation

    canvas_prob = FINGERPRINT_CUSTOMIZATION["canvas_noise_probability"]
    audio_noise = FINGERPRINT_CUSTOMIZATION["audio_noise_range"][1]

    await context.add_init_script(f"""
        Object.defineProperty(navigator, 'webdriver', {{ get: () => false }});
        Object.defineProperty(screen, 'width', {{ get: () => {screen_config['width']} }});
        Object.defineProperty(screen, 'height', {{ get: () => {screen_config['height']} }});
        Object.defineProperty(screen, 'availWidth', {{ get: () => {screen_config['width']} }});
        Object.defineProperty(screen, 'availHeight', {{ get: () => {screen_config.get('height', 1080) - 40} }});
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {screen_config.get('colorDepth', 24)} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {screen_config.get('pixelDepth', 24)} }});

        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hardware['cores']} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {hardware['memory']} }});
        Object.defineProperty(navigator, 'platform', {{ get: () => '{hardware['platform']}' }});
        Object.defineProperty(navigator, 'language', {{ get: () => '{languages.split(',')[0].strip("[]' ")}' }});
        Object.defineProperty(navigator, 'languages', {{ get: () => {languages} }});

        Date.prototype.getTimezoneOffset = function() {{ return {timezone_offset}; }};

        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {{
            const originalResult = originalToDataURL.apply(this, arguments);
            return originalResult.slice(0, -10) + Math.random().toString(36).slice(2);
        }};
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function() {{
            const result = originalGetImageData.apply(this, arguments);
            for (let i = 0; i < result.data.length; i += 4) {{
                if (Math.random() < {canvas_prob}) {{
                    result.data[i] = Math.min(255, result.data[i] + (Math.random() - 0.5) * 2);
                }}
            }}
            return result;
        }};

        try {{
            const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) {{ return 'Intel Open Source Technology Center'; }}
                if (parameter === 37446) {{ return 'Mesa DRI Intel(R) Ivybridge Mobile '; }}
                return originalGetParameter.apply(this, arguments);
            }};
        }} catch (e) {{}}

        const originalCreateAnalyser = AudioContext.prototype.createAnalyser;
        AudioContext.prototype.createAnalyser = function() {{
            const analyser = originalCreateAnalyser.apply(this, arguments);
            const originalGetFloatFrequencyData = analyser.getFloatFrequencyData;
            analyser.getFloatFrequencyData = function(array) {{
                const result = originalGetFloatFrequencyData.apply(this, arguments);
                for (let i = 0; i < array.length; i++) {{
                    array[i] += (Math.random() - 0.5) * {audio_noise};
                }}
                return result;
            }};
            return analyser;
        }};

        Object.defineProperty(navigator, 'plugins', {{
            get: () => [
                {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' }},
                {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' }},
                {{ name: 'Native Client', filename: 'internal-nacl-plugin' }}
            ],
        }});
    """)

    return profile

def get_stealth_browser_args():
    """Get browser launch arguments for enhanced stealth from config."""
    return STEALTH_ARGS 