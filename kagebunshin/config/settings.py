"""
Configuration settings for KageBunshin.
"""
import os
from pathlib import Path
import dotenv

dotenv.load_dotenv()

# LLM Configuration
LLM_MODEL = "gpt-5-mini"
LLM_PROVIDER = "openai"
LLM_REASONING_EFFORT = "minimal" # "minimal", "low", "medium", "high"
LLM_VERBOSITY = "medium" # "low", "medium", "high"

SUMMARIZER_MODEL = "gpt-5-nano"
SUMMARIZER_PROVIDER = "openai"
SUMMARIZER_REASONING_EFFORT = "minimal" # "minimal", "low", "medium", "high"

LLM_TEMPERATURE = 1
# Enable/disable summarizer node (default off)
ENABLE_SUMMARIZATION = os.environ.get("KAGE_ENABLE_SUMMARIZATION", "0") == "1"

# Filesystem Sandbox Configuration
# Master switch to enable/disable all filesystem operations
FILESYSTEM_ENABLED = os.environ.get("KAGE_FILESYSTEM_ENABLED", "1") == "1"

# Base directory for the filesystem sandbox - all file operations are restricted to this directory
# If None, defaults to ~/.kagebunshin/workspace
FILESYSTEM_SANDBOX_BASE = os.environ.get("KAGE_FILESYSTEM_SANDBOX", None)
if FILESYSTEM_SANDBOX_BASE is None:
    FILESYSTEM_SANDBOX_BASE = str(Path.home() / ".kagebunshin" / "workspace")

# Maximum file size in bytes that can be read or written (default: 10MB)
# This prevents agents from creating or reading extremely large files that could exhaust system resources
FILESYSTEM_MAX_FILE_SIZE = int(os.environ.get("KAGE_FILESYSTEM_MAX_FILE_SIZE", str(10 * 1024 * 1024)))

# Whitelist of allowed file extensions (without dots)
# Only files with these extensions can be created or read for security
# Can be overridden via KAGE_FILESYSTEM_ALLOWED_EXTENSIONS as comma-separated list
FILESYSTEM_ALLOWED_EXTENSIONS = os.environ.get("KAGE_FILESYSTEM_ALLOWED_EXTENSIONS", 
    "txt,md,json,csv,xml,html,css,js,py,yaml,yml,log,rst,ini,cfg,conf").split(",")

# Whether to allow overwriting existing files (default: True)
# Set to False to prevent accidental data loss
FILESYSTEM_ALLOW_OVERWRITE = os.environ.get("KAGE_FILESYSTEM_ALLOW_OVERWRITE", "1") == "1"

# Whether to automatically create the sandbox directory if it doesn't exist (default: True)
FILESYSTEM_CREATE_SANDBOX = os.environ.get("KAGE_FILESYSTEM_CREATE_SANDBOX", "1") == "1"

# Whether to log all filesystem operations for security auditing (default: True)
# Recommended to keep enabled for security monitoring
FILESYSTEM_LOG_OPERATIONS = os.environ.get("KAGE_FILESYSTEM_LOG_OPERATIONS", "1") == "1"

# Filesystem cleanup configuration
# Maximum age in days for agent directories before cleanup (default: 30 days)
FILESYSTEM_CLEANUP_MAX_AGE_DAYS = int(os.environ.get("KAGE_FILESYSTEM_CLEANUP_MAX_AGE_DAYS", "30"))

# Maximum total workspace size in bytes before cleanup (default: 100MB)
FILESYSTEM_CLEANUP_MAX_SIZE = int(os.environ.get("KAGE_FILESYSTEM_CLEANUP_MAX_SIZE", str(100 * 1024 * 1024)))

# Whether to enable automatic cleanup on agent initialization (default: True)
FILESYSTEM_CLEANUP_ENABLED = os.environ.get("KAGE_FILESYSTEM_CLEANUP_ENABLED", "1") == "1"

# Maximum number of concurrent filesystem operations per agent (default: 10)
# Prevents agents from overwhelming the filesystem with too many simultaneous operations
FILESYSTEM_MAX_CONCURRENT_OPERATIONS = int(os.environ.get("KAGE_FILESYSTEM_MAX_CONCURRENT", "10"))

# Browser Configuration
# Set to your Chrome executable path to use a specific installation.
# If None, Playwright will use its bundled browser or the specified channel.
# Example for macOS: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Example for Windows: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# Example for Linux: "/usr/bin/google-chrome"
# BROWSER_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BROWSER_EXECUTABLE_PATH = None

# Viewport Configuration
# Set the actual browser viewport size (different from screen fingerprint)
ACTUAL_VIEWPORT_WIDTH = 1280
ACTUAL_VIEWPORT_HEIGHT = 1280

# Path to the user data directory for the browser. Using a persistent directory
# allows the browser to maintain sessions, cookies, and other data.
# If None, a temporary profile will be used.
# Example for macOS (Default profile): "~/Library/Application Support/Google/Chrome/Default"
# Example for Windows: "~/AppData/Local/Google/Chrome/User Data"
# Example for Linux: "~/.config/google-chrome/default"
USER_DATA_DIR = None

# Workflow Configuration
RECURSION_LIMIT = 150
MAX_ITERATIONS = 100
TIMEOUT = 60  # 1 minute

# System Prompts
_current_dir = Path(__file__).parent
_prompt_path = _current_dir / "prompts" / "kagebunshin_system_prompt_v3.md"

with open(_prompt_path, "r") as f:
    SYSTEM_TEMPLATE = f.read()

# Simplified system template for tool-calling chatbot approach

# Human behavior simulation settings
ACTIVATE_HUMAN_BEHAVIOR = True # Master switch for human-like browsing
HUMAN_BEHAVIOR_SEED = 42 # Seed for random number generator, set to None to disable seeding
HUMAN_BEHAVIOR = {
    # Delay ranges in milliseconds
    "min_action_delay": 100,
    "max_action_delay": 500,
    "min_click_delay": 50,
    "max_click_delay": 200,
    "min_type_delay": 100,
    "max_type_delay": 300,
    
    # Typing behavior
    "typing_speed_range": (0.05, 0.15),  # Base delay between characters
    "hesitation_probability": 0.1,      # Chance of longer pause while typing
    "hesitation_delay_range": (0.2, 0.8),
    "rhythm_speedup_factor": 0.8,       # Speed increase after typing a few chars
    "special_char_slowdown": 1.5,       # Slowdown for non-alphanumeric chars
    
    # Mouse movement
    "mouse_steps_range": (3, 7),        # Number of steps in mouse movement
    "mouse_jitter_range": (-2, 2),      # Random jitter in pixels
    "mouse_step_delay_range": (0.01, 0.03),
    
    # Scrolling behavior
    "scroll_increments_range": (3, 8),  # Break scrolls into multiple parts
    "scroll_amount_variation": 0.25,    # ±25% variation in scroll amount
    "scroll_delay_range": (0.05, 0.15),
    
    # Wait behavior
    "wait_time_range": (3, 7),          # Seconds
    "fidget_probability": 0.3,          # Chance of mouse movement during wait
    "fidget_range": (-20, 20),          # Pixel range for fidgeting
}

# Fingerprint evasion settings
FINGERPRINT_PROFILES = [
    {
        "name": "Win_Chrome_1080p",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "headers": {
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Platform': '"Windows"',
        },
        "screen": {"width": 1920, "height": 1080, "colorDepth": 24, "pixelDepth": 24},
        "hardware": {"cores": 8, "memory": 16, "platform": "Win32"},
        "timezone_offset": -300,  # EST
        "language_list": ["en-US", "en"],
    },
    {
        "name": "Mac_Chrome_Large",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "headers": {
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Platform': '"macOS"',
        },
        "screen": {"width": 2560, "height": 1440, "colorDepth": 24, "pixelDepth": 24},
        "hardware": {"cores": 12, "memory": 16, "platform": "MacIntel"},
        "timezone_offset": -420,  # MST
        "language_list": ["en-US", "en"],
    },
    {
        "name": "Win_Firefox_Laptop",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "headers": {
            'Accept-Language': 'en-GB,en;q=0.8',
        },
        "screen": {"width": 1366, "height": 768, "colorDepth": 24, "pixelDepth": 24},
        "hardware": {"cores": 4, "memory": 8, "platform": "Win32"},
        "timezone_offset": 0,  # GMT
        "language_list": ["en-GB", "en"],
    },
    {
        "name": "Win_Edge_Standard",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "headers": {
            'Accept-Language': 'en-US,en;q=0.9,es;q=0.6',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
            'Sec-Ch-Ua-Platform': '"Windows"',
        },
        "screen": {"width": 1536, "height": 864, "colorDepth": 24, "pixelDepth": 24},
        "hardware": {"cores": 6, "memory": 12, "platform": "Win32"},
        "timezone_offset": -360,  # CST
        "language_list": ["en-US", "en", "es"],
    }
]

FINGERPRINT_CUSTOMIZATION = {
    # Canvas noise settings
    "canvas_noise_probability": 0.001,  # Very low to avoid breaking functionality
    "canvas_noise_range": (-0.5, 0.5),
    
    # Audio context noise
    "audio_noise_range": (-0.0001, 0.0001),
}

# Reading time calculation
READING_TIME = {
    "words_per_minute": 225,             # Average reading speed
    "seconds_per_image": (2, 3),         # Time spent viewing images
    "form_extra_time": (5, 15),          # Extra time on form pages
    "human_variation_factor": (0.4, 2.5), # Speed variation between users
    "min_reading_time": 2,               # Minimum seconds
    "max_reading_time": 120,             # Maximum seconds
}

# Smart delay settings
SMART_DELAYS = {
    "base_delays": {
        "click": (0.5, 2.0),
        "type": (1.0, 3.0), 
        "scroll": (0.3, 1.5),
        "navigate": (2.0, 5.0),
        "read": (3.0, 8.0)
    },
    "complexity_multipliers": {
        "simple": 0.7,
        "medium": 1.0,
        "complex": 1.4
    }
}

# Honeypot detection patterns
HONEYPOT_DETECTION = {
    "suspicious_patterns": ['honeypot', 'trap', 'bot', 'hidden', 'invisible'],
    "off_screen_threshold": -1000,  # Pixels off-screen to consider suspicious
}

# Components/features to disable in Chromium for more stealthy automation
CHROME_DISABLED_COMPONENTS = [
    # Playwright defaults and additions
    'AcceptCHFrame',
    'AutoExpandDetailsElement',
    'AvoidUnnecessaryBeforeUnloadCheckSync',
    'CertificateTransparencyComponentUpdater',
    'DestroyProfileOnBrowserClose',
    'DialMediaRouteProvider',
    'ExtensionManifestV2Disabled',
    'GlobalMediaControls',
    'HttpsUpgrades',
    'ImprovedCookieControls',
    'LazyFrameLoading',
    'LensOverlay',
    'MediaRouter',
    'PaintHolding',
    'ThirdPartyStoragePartitioning',
    'Translate',
    # Extra hardening
    'AutomationControlled',
    'BackForwardCache',
    'OptimizationHints',
    'ProcessPerSiteUpToMainFrameThreshold',
    'InterestFeedContentSuggestions',
    'HeavyAdPrivacyMitigations',
    'PrivacySandboxSettings4',
    'AutofillServerCommunication',
    'CrashReporting',
    'OverscrollHistoryNavigation',
    'InfiniteSessionRestore',
    'ExtensionDisableUnsupportedDeveloper',
]

# Default permissions to grant to reduce anti-bot fingerprint surface
DEFAULT_PERMISSIONS = ['clipboard-read', 'clipboard-write', 'notifications']

# Browser launch arguments for stealth
STEALTH_ARGS = [
    '--no-first-run',
    '--no-service-autorun', 
    '--no-default-browser-check',
    '--disable-blink-features=AutomationControlled',
    '--disable-features=VizDisplayCompositor',
    '--disable-ipc-flooding-protection',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--disable-client-side-phishing-detection',
    '--disable-sync',
    '--metrics-recording-only',
    '--no-report-upload',
    '--disable-dev-shm-usage',
    # Keep extensions disabled by default for consistency unless explicitly enabled
    '--disable-extensions',
    '--disable-component-extensions-with-background-pages',
    '--disable-default-apps',
    '--disable-background-networking',
    '--disable-background-timer-throttling',
    '--disable-breakpad',
    '--disable-hang-monitor',
    '--disable-popup-blocking',
    '--disable-prompt-on-repost',
    '--disable-renderer-backgrounding',
    '--disable-search-engine-choice-screen',
    '--disable-domain-reliability',
    '--disable-datasaver-prompt',
    '--disable-speech-synthesis-api',
    '--disable-speech-api',
    '--disable-print-preview',
    '--disable-desktop-notifications',
    '--disable-infobars',
    '--no-default-browser-check',
    '--no-service-autorun',
    '--noerrdialogs',
    '--password-store=basic',
    '--use-mock-keychain',
    '--unsafely-disable-devtools-self-xss-warnings',
    '--enable-features=NetworkService,NetworkServiceInProcess',
    '--log-level=2',
    '--mute-audio',
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-web-security',
    # Disable a wide set of components that are commonly toggled by automation
    f"--disable-features={','.join(CHROME_DISABLED_COMPONENTS)}",
]

# ============================
# Redis Group Chat Settings
# ============================

# Basic Redis connection (local by default)
REDIS_HOST = os.environ.get("KAGE_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("KAGE_REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("KAGE_REDIS_DB", "0"))
REDIS_PASSWORD = os.environ.get("KAGE_REDIS_PASSWORD")
REDIS_USERNAME = os.environ.get("KAGE_REDIS_USERNAME")

# Group chat settings
GROUPCHAT_PREFIX = os.environ.get("KAGE_GROUPCHAT_PREFIX", "kagebunshin:groupchat")
GROUPCHAT_ROOM = os.environ.get("KAGE_GROUPCHAT_ROOM", "lobby")
GROUPCHAT_MAX_MESSAGES = int(os.environ.get("KAGE_GROUPCHAT_MAX_MESSAGES", "200"))

# ============================
# Performance Optimization Settings
# ============================

# Speed mode: "stealth" (maximum reliability), "balanced" (default), "fast" (maximum speed)
PERFORMANCE_MODE = os.environ.get("KAGE_PERFORMANCE_MODE", "balanced")

# Performance mode configurations
PERFORMANCE_PROFILES = {
    "stealth": {
        "description": "Maximum reliability, minimal speed optimization",
        "enable_intelligent_fallback": False,
        "enable_element_caching": False, 
        "enable_parallel_verification": False,
        "confidence_threshold": 0.9,
        "force_human_behavior": True,
        "delay_profile": "human",
        "learning_enabled": False
    },
    "balanced": {
        "description": "Balance between speed and reliability",
        "enable_intelligent_fallback": True,
        "enable_element_caching": True,
        "enable_parallel_verification": True, 
        "confidence_threshold": 0.7,
        "force_human_behavior": False,
        "delay_profile": "adaptive",
        "learning_enabled": True
    },
    "fast": {
        "description": "Maximum speed with acceptable reliability",
        "enable_intelligent_fallback": True,
        "enable_element_caching": True,
        "enable_parallel_verification": True,
        "confidence_threshold": 0.4,
        "force_human_behavior": False, 
        "delay_profile": "minimal",
        "learning_enabled": True
    }
}

# Delay profiles for different performance modes
DELAY_PROFILES = {
    "minimal": {
        "action_delay_range": (0.05, 0.1),
        "click_delay_range": (0.02, 0.05), 
        "type_delay_range": (0.01, 0.03),
        "scroll_delay_range": (0.1, 0.2),
        "navigate_delay_range": (0.5, 1.0),
        "use_human_typing": False,
        "use_human_scrolling": False
    },
    "fast": {
        "action_delay_range": (0.1, 0.3),
        "click_delay_range": (0.05, 0.1),
        "type_delay_range": (0.02, 0.08), 
        "scroll_delay_range": (0.2, 0.5),
        "navigate_delay_range": (0.8, 1.5),
        "use_human_typing": False,
        "use_human_scrolling": True
    },
    "normal": {
        "action_delay_range": (0.3, 1.0),
        "click_delay_range": (0.1, 0.3),
        "type_delay_range": (0.05, 0.15),
        "scroll_delay_range": (0.3, 1.0), 
        "navigate_delay_range": (1.0, 3.0),
        "use_human_typing": True,
        "use_human_scrolling": True
    },
    "human": {
        "action_delay_range": (0.5, 2.0),
        "click_delay_range": (0.1, 0.4),
        "type_delay_range": (0.05, 0.2),
        "scroll_delay_range": (0.5, 2.0),
        "navigate_delay_range": (2.0, 5.0),
        "use_human_typing": True,
        "use_human_scrolling": True
    },
    "adaptive": {
        # Dynamic profile - delays are determined by performance optimizer
        "base_action_delay_range": (0.1, 0.8),
        "base_click_delay_range": (0.05, 0.2),
        "base_type_delay_range": (0.02, 0.1),
        "base_scroll_delay_range": (0.2, 1.0),
        "base_navigate_delay_range": (1.0, 3.0),
        "use_human_typing": True,  # Can be overridden by optimizer
        "use_human_scrolling": True  # Can be overridden by optimizer
    }
}

# Site-specific overrides (domain -> performance settings)
SITE_PERFORMANCE_OVERRIDES = {
    # Example overrides for known problematic sites
    "recaptcha.net": {"force_mode": "stealth"},
    "cloudflare.com": {"force_mode": "stealth"},
    "amazon.com": {"preferred_mode": "balanced"},
    "google.com": {"preferred_mode": "fast"},
    # Add more as needed
}

# Performance optimization flags
ENABLE_PERFORMANCE_LEARNING = os.environ.get("KAGE_ENABLE_PERFORMANCE_LEARNING", "1") == "1"
PERFORMANCE_CACHE_TTL = int(os.environ.get("KAGE_PERFORMANCE_CACHE_TTL", "300"))  # 5 minutes
MAX_PERFORMANCE_HISTORY = int(os.environ.get("KAGE_MAX_PERFORMANCE_HISTORY", "1000"))

# ============================
# Concurrency / Limits  
# ============================
MAX_KAGEBUNSHIN_INSTANCES = int(os.environ.get("KAGE_MAX_KAGEBUNSHIN_INSTANCES", "20"))