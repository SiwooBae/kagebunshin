/**
 * Constants and styling for KageBunshin page annotation system
 * 
 * This module provides:
 * - Custom CSS styling for scrollbars
 * - Global state variables for annotation tracking
 * - Color palette for element type visualization
 * - Color utility functions
 */
const customCSS = `
    ::-webkit-scrollbar {
        width: 10px;
    }
    ::-webkit-scrollbar-track {
        background: #27272a;
    }
    ::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 0.375rem;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
`;

// Apply custom CSS styling to the page
const styleTag = document.createElement("style");
styleTag.textContent = customCSS;
document.head.append(styleTag);

/**
 * Global variables for page annotation state management
 * These variables maintain state across annotation operations
 */
let labels = []; // Array to store element labels
let globalElementIndex = 0; // Incremental index for unique element identification
let overlaySvg = null; // Main SVG overlay element for annotations
let overlayLayer = null; // Layer group within the SVG overlay
let redrawTimeoutId = null; // Timeout ID for debounced redraw operations
let autoUpdateHandlersAttached = false; // Flag to track event listener attachment
let lastMarkPageOptions = null; // Cache last options for redraw operations
let attachedIframeWindows = []; // Array of iframe windows with attached listeners

/**
 * Color-blind friendly palette based on Okabe & Ito research
 * Provides accessible colors for different element types
 */
const TYPE_COLORS = {
  button: "#E69F00", // orange - buttons and clickable elements
  a: "#0072B2", // blue - links and navigation
  input: "#009E73", // green - input fields and forms
  textarea: "#009E73", // green - text areas
  select: "#009E73", // green - select dropdowns
  label: "#CC79A7", // purple - form labels
  iframe: "#D55E00", // vermillion - embedded content
  video: "#56B4E9", // sky blue - media elements
  generic: "#BBBBBB", // grey - fallback for unknown types
  captcha: "#F0E442" // yellow - CAPTCHA elements
};

/**
 * Determines the appropriate color for an element based on its type and properties
 * @param {Object} item - Element item with type and metadata
 * @returns {string} Hex color code
 */
function getColorForItem(item) {
  if (item.isCaptcha) return TYPE_COLORS.captcha;
  const tag = (item.type || "").toLowerCase();
  if (TYPE_COLORS[tag]) return TYPE_COLORS[tag];
  // Role-based mapping for semantic elements
  const role = (item.hierarchy && item.hierarchy.semanticRole) || "";
  if (role === "button") return TYPE_COLORS.button;
  return TYPE_COLORS.generic;
}

/**
 * Generates a random hex color code
 * @returns {string} Random hex color (e.g., "#A1B2C3")
 */
function getRandomColor() {
    var letters = "0123456789ABCDEF";
    var color = "#";
    for (var i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
    }
    return color;
}