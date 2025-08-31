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

        // --- JavaScript Environment Hardening ---
        // Override toString for native functions to hide automation
        try {{
            const nativeFunctions = [
                window.chrome,
                navigator.permissions && navigator.permissions.query,
                navigator.webdriver,
                window.RTCPeerConnection
            ];
            nativeFunctions.forEach(func => {{
                if (func && typeof func === 'function') {{
                    const originalToString = func.toString;
                    func.toString = function() {{
                        return originalToString.call(this).replace(/\\{{[^}}]*\\}}/g, '{{ [native code] }}');
                    }};
                }}
            }});
        }} catch (e) {{ /* ignore */ }}

        // Sanitize stack traces to remove automation signatures
        const originalError = Error;
        window.Error = function(...args) {{
            const err = new originalError(...args);
            if (err.stack) {{
                err.stack = err.stack.replace(/phantomjs|selenium|webdriver|puppeteer|playwright|chrome-devtools/gi, 'chrome');
            }}
            return err;
        }};
        Error.prototype = originalError.prototype;
        Error.captureStackTrace = originalError.captureStackTrace;

        // Clean console methods to avoid automation detection
        ['log', 'warn', 'error', 'info', 'debug'].forEach(method => {{
            const original = console[method];
            console[method] = function(...args) {{
                const cleanedArgs = args.filter(arg => {{
                    const str = String(arg);
                    return !str.match(/webdriver|selenium|puppeteer|playwright|chrome-devtools/i);
                }});
                if (cleanedArgs.length > 0) {{
                    original.apply(console, cleanedArgs);
                }}
            }};
        }});

        // --- CDP Detection & Masking ---
        // Block CDP runtime detection
        if (window.chrome && window.chrome.runtime) {{
            Object.defineProperty(window.chrome, 'runtime', {{
                get: () => ({{
                    sendMessage: undefined,
                    connect: undefined,
                    onConnect: undefined
                }})
            }});
        }}

        // Override CDP execution context indicators
        Object.defineProperty(window, '__playwright', {{ get: () => undefined }});
        Object.defineProperty(window, '__puppeteer', {{ get: () => undefined }});

        // Remove automation extensions and CDP artifacts dynamically
        Object.keys(window).forEach(key => {{
            if (key.startsWith('cdc_')) {{
                try {{
                    delete window[key];
                    Object.defineProperty(window, key, {{ get: () => undefined }});
                }} catch (e) {{ /* ignore */ }}
            }}
        }});
        
        // Also prevent new CDP artifacts from being created
        const cdpPatterns = ['cdc_', '__webdriver', '__selenium', '__fxdriver'];
        cdpPatterns.forEach(pattern => {{
            Object.defineProperty(window, pattern + 'blocked', {{ 
                get: () => undefined,
                set: () => {{}} 
            }});
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
                // UNMASKED_VENDOR_WEBGL - randomized vendors
                if (parameter === 37445) {{ 
                    const vendors = ['Intel Open Source Technology Center', 'Google Inc.', 'Mozilla', 'Apple Inc.'];
                    return vendors[Math.floor(Math.random() * vendors.length)];
                }}
                // UNMASKED_RENDERER_WEBGL - randomized renderers
                if (parameter === 37446) {{ 
                    const renderers = [
                        'Intel(R) HD Graphics 620',
                        'Intel(R) UHD Graphics 630', 
                        'Intel(R) Iris(R) Plus Graphics',
                        'NVIDIA GeForce GTX 1060',
                        'AMD Radeon RX 580',
                        'Mesa DRI Intel(R) HD Graphics'
                    ];
                    return renderers[Math.floor(Math.random() * renderers.length)];
                }}
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

        // --- Core Fingerprint Randomization ---
        // WebRTC leak prevention and spoofing
        const originalRTCPeerConnection = window.RTCPeerConnection || window.mozRTCPeerConnection || window.webkitRTCPeerConnection;
        if (originalRTCPeerConnection) {{
            window.RTCPeerConnection = function(...args) {{
                const pc = new originalRTCPeerConnection(...args);
                
                // Override createDataChannel to prevent fingerprinting
                const originalCreateDataChannel = pc.createDataChannel;
                pc.createDataChannel = function() {{
                    return {{
                        close: () => {{}},
                        send: () => {{}},
                        addEventListener: () => {{}}
                    }};
                }};
                
                // Override createOffer to prevent fingerprinting
                const originalCreateOffer = pc.createOffer;
                pc.createOffer = function() {{
                    return Promise.resolve({{
                        type: 'offer',
                        sdp: 'v=0\\r\\no=- 0 0 IN IP4 127.0.0.1\\r\\ns=-\\r\\nt=0 0\\r\\n'
                    }});
                }};
                
                return pc;
            }};
            
            // Copy static properties
            Object.setPrototypeOf(window.RTCPeerConnection, originalRTCPeerConnection);
            window.RTCPeerConnection.prototype = originalRTCPeerConnection.prototype;
        }}

        // Battery API spoofing with randomized values
        if (navigator.getBattery) {{
            Object.defineProperty(navigator, 'getBattery', {{
                get: () => () => Promise.resolve({{
                    charging: Math.random() > 0.5,
                    chargingTime: Math.random() > 0.5 ? 0 : Math.floor(Math.random() * 7200),
                    dischargingTime: Math.random() > 0.5 ? Infinity : Math.floor(Math.random() * 14400),
                    level: Math.random() * 0.4 + 0.6, // 60-100%
                    addEventListener: () => {{}},
                    removeEventListener: () => {{}}
                }})
            }});
        }}

        // Permissions API masking
        if (navigator.permissions && navigator.permissions.query) {{
            const originalQuery = navigator.permissions.query;
            navigator.permissions.query = function(params) {{
                // Return plausible permission states to avoid fingerprinting
                const permission = params && params.name;
                const commonStates = ['granted', 'denied', 'prompt'];
                
                switch (permission) {{
                    case 'notifications':
                        return Promise.resolve({{ state: 'denied', onchange: null }});
                    case 'geolocation':
                        return Promise.resolve({{ state: 'prompt', onchange: null }});
                    case 'camera':
                    case 'microphone':
                        return Promise.resolve({{ state: 'prompt', onchange: null }});
                    case 'midi':
                        return Promise.resolve({{ state: 'denied', onchange: null }});
                    default:
                        // For unknown permissions, return a random but consistent state
                        const state = commonStates[Math.floor(Math.random() * commonStates.length)];
                        return Promise.resolve({{ state, onchange: null }});
                }}
            }};
        }}

        // MediaDevices API spoofing
        if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
            const originalEnumerateDevices = navigator.mediaDevices.enumerateDevices;
            navigator.mediaDevices.enumerateDevices = function() {{
                // Generate randomized but realistic device IDs
                const generateDeviceId = () => 'device_' + Math.random().toString(36).substr(2, 9);
                const generateGroupId = () => 'group_' + Math.random().toString(36).substr(2, 8);
                
                return Promise.resolve([
                    {{
                        deviceId: generateDeviceId(),
                        groupId: generateGroupId(),
                        kind: 'audioinput',
                        label: Math.random() > 0.5 ? '' : 'Built-in Microphone'
                    }},
                    {{
                        deviceId: generateDeviceId(), 
                        groupId: generateGroupId(),
                        kind: 'audiooutput',
                        label: Math.random() > 0.5 ? '' : 'Built-in Output'
                    }}
                ]);
            }};
        }}

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

        // --- JavaScript Environment Hardening ---
        // Override toString for native functions to hide automation
        try {{
            const nativeFunctions = [
                window.chrome,
                navigator.permissions && navigator.permissions.query,
                navigator.webdriver,
                window.RTCPeerConnection
            ];
            nativeFunctions.forEach(func => {{
                if (func && typeof func === 'function') {{
                    const originalToString = func.toString;
                    func.toString = function() {{
                        return originalToString.call(this).replace(/\\{{[^}}]*\\}}/g, '{{ [native code] }}');
                    }};
                }}
            }});
        }} catch (e) {{ /* ignore */ }}

        // Sanitize stack traces to remove automation signatures
        const originalError = Error;
        window.Error = function(...args) {{
            const err = new originalError(...args);
            if (err.stack) {{
                err.stack = err.stack.replace(/phantomjs|selenium|webdriver|puppeteer|playwright|chrome-devtools/gi, 'chrome');
            }}
            return err;
        }};
        Error.prototype = originalError.prototype;
        Error.captureStackTrace = originalError.captureStackTrace;

        // Clean console methods to avoid automation detection
        ['log', 'warn', 'error', 'info', 'debug'].forEach(method => {{
            const original = console[method];
            console[method] = function(...args) {{
                const cleanedArgs = args.filter(arg => {{
                    const str = String(arg);
                    return !str.match(/webdriver|selenium|puppeteer|playwright|chrome-devtools/i);
                }});
                if (cleanedArgs.length > 0) {{
                    original.apply(console, cleanedArgs);
                }}
            }};
        }});

        // --- CDP Detection & Masking ---
        // Block CDP runtime detection
        if (window.chrome && window.chrome.runtime) {{
            Object.defineProperty(window.chrome, 'runtime', {{
                get: () => ({{
                    sendMessage: undefined,
                    connect: undefined,
                    onConnect: undefined
                }})
            }});
        }}

        // Override CDP execution context indicators
        Object.defineProperty(window, '__playwright', {{ get: () => undefined }});
        Object.defineProperty(window, '__puppeteer', {{ get: () => undefined }});

        // Remove automation extensions and CDP artifacts dynamically
        Object.keys(window).forEach(key => {{
            if (key.startsWith('cdc_')) {{
                try {{
                    delete window[key];
                    Object.defineProperty(window, key, {{ get: () => undefined }});
                }} catch (e) {{ /* ignore */ }}
            }}
        }});
        
        // Also prevent new CDP artifacts from being created
        const cdpPatterns = ['cdc_', '__webdriver', '__selenium', '__fxdriver'];
        cdpPatterns.forEach(pattern => {{
            Object.defineProperty(window, pattern + 'blocked', {{ 
                get: () => undefined,
                set: () => {{}} 
            }});
        }});
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

        // --- Core Fingerprint Randomization ---
        // WebRTC leak prevention and spoofing
        const originalRTCPeerConnection = window.RTCPeerConnection || window.mozRTCPeerConnection || window.webkitRTCPeerConnection;
        if (originalRTCPeerConnection) {{
            window.RTCPeerConnection = function(...args) {{
                const pc = new originalRTCPeerConnection(...args);
                
                // Override createDataChannel to prevent fingerprinting
                const originalCreateDataChannel = pc.createDataChannel;
                pc.createDataChannel = function() {{
                    return {{
                        close: () => {{}},
                        send: () => {{}},
                        addEventListener: () => {{}}
                    }};
                }};
                
                // Override createOffer to prevent fingerprinting
                const originalCreateOffer = pc.createOffer;
                pc.createOffer = function() {{
                    return Promise.resolve({{
                        type: 'offer',
                        sdp: 'v=0\\r\\no=- 0 0 IN IP4 127.0.0.1\\r\\ns=-\\r\\nt=0 0\\r\\n'
                    }});
                }};
                
                return pc;
            }};
            
            // Copy static properties
            Object.setPrototypeOf(window.RTCPeerConnection, originalRTCPeerConnection);
            window.RTCPeerConnection.prototype = originalRTCPeerConnection.prototype;
        }}

        // Battery API spoofing with randomized values
        if (navigator.getBattery) {{
            Object.defineProperty(navigator, 'getBattery', {{
                get: () => () => Promise.resolve({{
                    charging: Math.random() > 0.5,
                    chargingTime: Math.random() > 0.5 ? 0 : Math.floor(Math.random() * 7200),
                    dischargingTime: Math.random() > 0.5 ? Infinity : Math.floor(Math.random() * 14400),
                    level: Math.random() * 0.4 + 0.6, // 60-100%
                    addEventListener: () => {{}},
                    removeEventListener: () => {{}}
                }})
            }});
        }}

        // Permissions API masking
        if (navigator.permissions && navigator.permissions.query) {{
            const originalQuery = navigator.permissions.query;
            navigator.permissions.query = function(params) {{
                // Return plausible permission states to avoid fingerprinting
                const permission = params && params.name;
                const commonStates = ['granted', 'denied', 'prompt'];
                
                switch (permission) {{
                    case 'notifications':
                        return Promise.resolve({{ state: 'denied', onchange: null }});
                    case 'geolocation':
                        return Promise.resolve({{ state: 'prompt', onchange: null }});
                    case 'camera':
                    case 'microphone':
                        return Promise.resolve({{ state: 'prompt', onchange: null }});
                    case 'midi':
                        return Promise.resolve({{ state: 'denied', onchange: null }});
                    default:
                        // For unknown permissions, return a random but consistent state
                        const state = commonStates[Math.floor(Math.random() * commonStates.length)];
                        return Promise.resolve({{ state, onchange: null }});
                }}
            }};
        }}

        // MediaDevices API spoofing
        if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
            const originalEnumerateDevices = navigator.mediaDevices.enumerateDevices;
            navigator.mediaDevices.enumerateDevices = function() {{
                // Generate randomized but realistic device IDs
                const generateDeviceId = () => 'device_' + Math.random().toString(36).substr(2, 9);
                const generateGroupId = () => 'group_' + Math.random().toString(36).substr(2, 8);
                
                return Promise.resolve([
                    {{
                        deviceId: generateDeviceId(),
                        groupId: generateGroupId(),
                        kind: 'audioinput',
                        label: Math.random() > 0.5 ? '' : 'Built-in Microphone'
                    }},
                    {{
                        deviceId: generateDeviceId(), 
                        groupId: generateGroupId(),
                        kind: 'audiooutput',
                        label: Math.random() > 0.5 ? '' : 'Built-in Output'
                    }}
                ]);
            }};
        }}

        // Plugin array spoofing
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