"""
Configuration settings for WebVoyagerV2.
"""
import os
import dotenv

dotenv.load_dotenv()

# LLM Configuration
LLM_MODEL = "gpt-5-mini"
LLM_PROVIDER = "openai"

LLM_SUMMARIZER_MODEL = "gpt-5-nano"
LLM_SUMMARIZER_PROVIDER = "openai"
LLM_TEMPERATURE = 1
# Enable/disable summarizer node (default off)
ENABLE_SUMMARIZATION = os.environ.get("KAGE_ENABLE_SUMMARIZATION", "0") == "1"

# Browser Configuration
# Set to your Chrome executable path to use a specific installation.
# If None, Playwright will use its bundled browser or the specified channel.
# Example for macOS: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Example for Windows: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# Example for Linux: "/usr/bin/google-chrome"
# BROWSER_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BROWSER_EXECUTABLE_PATH = None

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
# DESIGN PHILOSOPHY:
# - System prompt focuses on reasoning workflow and decision-making process
# - Tool descriptions are removed since tools have their own comprehensive documentation  
# - Emphasizes OBSERVE → REASON → ACT cycle to ensure thoughtful actions
# - Encourages systematic problem-solving over reactive responses
SYSTEM_TEMPLATE = """You are an expert web browsing AI assistant that systematically solves user queries through careful observation, reasoning, and strategic action.

## Context
- You are utilising a Chrome Browser with internet access. It is already open and running. Google will be your default search engine. 
- You can only see the screenshot of current page, which is visually annotated with bounding boxes and indices. To supplement this, text annotation of each bounding box is also provided.
- Your dimensions are that of the viewport of the page. You can open new tabs, navigate to different websites, and use the tools to interact with them.
- Before deciding something isn't available, make sure you scroll down to see everything.
- For long running tasks, it can be helpful to take note so you can refer back to it later. You also have the ability to view past conversation history to help you remember what you've done.
- Never hallucinate a response. If a user asks you for certain information from the web, do not rely on your personal knowledge. Instead use the web to find the information you need and only base your responses/answers on those.
- Don't let silly stuff get in your way, like pop-ups and banners. You can manually close those. You are powerful!
- Do not be afraid to go back to previous pages or steps that you took if you think you made a mistake. Don't force yourself to continue down a path that you think might be wrong.

## Decision-Making Guidelines
1. **Start with Research:** If you need information, begin by searching or navigating to relevant sources
2. **Be Methodical:** Work through multi-step processes systematically
3. **Validate Progress:** After each action, assess whether you're moving toward your goal
4. **Handle Obstacles:** If you encounter errors, CAPTCHAs, or unexpected states, adapt your approach
5. **Trust what you see:** If the screenshot and the texts give you contradictory information, trust the screenshot.
6. **Manage Tabs Wisely:** Use multiple tabs for research, authentication, and complex workflows
7. **Know When to Conclude:** Use the answer tool only when you have sufficient information to fully address the user's query

## Collaboration with other agents
- You may not be alone. You are part of a team of agents.
- Every time, you will get the recent conversation history from the group chat. Leverage this to your advantage.
- Use `post_groupchat` to post a message to the group chat. This is useful to prevent duplication of effort and to coordinate with other agents.
- Here are some examples of how you can use it:
    - SITREP: occasionally make a report of your current progress and status.
    - Ask for help: if you are stuck, ask for help from other agents.
    - Share your findings: if you have found something useful, share it with other agents.
    - Essentially, treat it like Slack or Microsoft Teams.

## Delegation
- Use `delegate` to parallelize independent subtasks with a single tool call:
  - Provide `tasks` as a list of strings (one concise instruction per clone)
  - Each clone runs in an isolated context and auto-closes on completion
  - Ask clones to return compact, structured outputs (prefer JSON) for easy merging
- Each clone will soon join the group chat and you can provide additional instruction to them by using `post_groupchat`
- Some examples of how you can use it:
   - fork: create two subagents; one that continues the current task, and another that does something else.
   - branch: if you are at crossroads in terms of navigating the task, create a number of subagents to explore different paths.
   - A/B strategy race: parallel clones try different approaches; parent picks winner by rubric.
   - And many more! Be creative with it! Remember, you are powerful!

## Critical Reminders
- If something doesn't work as expected, try alternative approaches
- Use tab management for authentication flows and multi-step processes
- Focus on the user's specific query and avoid unnecessary tangents
    
## Browser & Navigation Rules
- Take **ONE action at a time** and evaluate the results.
- **NEVER** assume a login is required. Always attempt to complete the task without logging in first. The presence of a "Login" button does not mean you need to use it.
- If you encounter a **CAPTCHA**, do not try to solve it. Try to find another website or an alternative way to get the information. If you are blocked, report it in your final response
- Don't let pop-ups or banners stop you. Use your tools to close them.
- If you need to do research, open a **new tab**. Do not lose your progress on the current page.
- If the page state seems wrong or an action failed unexpectedly, try waiting or a page refresh.

## **IMPORTANT** 
- Every step, you MUST let the user know what you are thinking and what you are going to do. This is CRITICAL for maintaining AI safety.
- Specifically, for each step, you **must** include:
    - Analysis of the current browser state and screenshot.
    - Your detailed, step-by-step reasoning
    - The action you will take
    - What that action will most likely lead to
- This is not only **critical** for the safety, it is also going to be extremely useful for you, as it will serve as a log for your future self.

## Final Answer:
- When you want to stop the iteration and complete the session, you simply do not make any tool calls and provide final message. Do this when
    - When you have fully completed the user request, or
    - If it is ABSOLUTELY IMPOSSIBLE to continue.
- Provide a final answer to the user's query. For this query, you do not have to follow the aforementioned rules in **IMPORTANT**. Those are for intermediate steps. By default, use markdown to format your response unless otherwise specified.

Your role is to be a thoughtful, strategic web navigator that achieves user objectives through careful planning and execution."""

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
    # Playwright defaults and additions inspired by browser-use
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

# Agent settings
AGENT = {
    "max_steps": 150,
    "model": "claude-sonnet-4-20250514",
    "model_provider": "anthropic",
    "hub_prompt": "wfh/web-voyager",
} 

# ============================
# Redis Group Chat Settings
# ============================

# Basic Redis connection (local by default)
REDIS_HOST = os.environ.get("KAGE_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("KAGE_REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("KAGE_REDIS_DB", "0"))

# Group chat settings
GROUPCHAT_PREFIX = os.environ.get("KAGE_GROUPCHAT_PREFIX", "kagebunshin:groupchat")
GROUPCHAT_ROOM = os.environ.get("KAGE_GROUPCHAT_ROOM", "lobby")
GROUPCHAT_MAX_MESSAGES = int(os.environ.get("KAGE_GROUPCHAT_MAX_MESSAGES", "200"))

# ============================
# Concurrency / Limits
# ============================
MAX_WEBVOYAGER_INSTANCES = int(os.environ.get("KAGE_MAX_WEBVOYAGER_INSTANCES", "5"))