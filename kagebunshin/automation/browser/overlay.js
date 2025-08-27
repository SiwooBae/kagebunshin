/**
 * Overlay Management System for KageBunshin Page Annotations
 * 
 * This module handles the creation, management, and cleanup of SVG overlays
 * used for annotating page elements. It provides:
 * - SVG overlay creation and removal
 * - Event listener management for dynamic updates
 * - Cleanup utilities for annotation removal
 */

/**
 * Removes the SVG overlay from the page and cleans up any stray overlays
 * This function performs comprehensive cleanup across the main document and iframes
 */
function removeOverlay() {
  try {
    // Remove the main overlay if it exists
    if (overlaySvg && overlaySvg.parentElement) {
      overlaySvg.parentElement.removeChild(overlaySvg);
    }
  } catch (_) {}
  
  // Reset overlay references
  overlaySvg = null;
  overlayLayer = null;
  
  // Fallback cleanup: remove any stray overlays by ID in document and accessible iframes
  try {
    function removeByIdInDoc(doc) {
      try {
        const nodes = doc.querySelectorAll('#ai-annotation-overlay');
        nodes.forEach((n) => { 
          try { 
            n.parentElement && n.parentElement.removeChild(n); 
          } catch (_) {} 
        });
        
        // Recursively clean iframes
        const iframes = doc.querySelectorAll('iframe');
        iframes.forEach((iframe) => {
          try {
            const childDoc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
            if (childDoc) removeByIdInDoc(childDoc);
          } catch (_) {} // Cross-origin iframes will fail here
        });
      } catch (_) {}
    }
    removeByIdInDoc(document);
  } catch (_) {}
}

/**
 * Creates and initializes the SVG overlay for element annotations
 * Positions it as a fixed overlay covering the entire viewport
 */
function ensureOverlay() {
  removeOverlay(); // Clean up any existing overlay first
  
  const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
  const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
  
  // Create the main SVG overlay element
  overlaySvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  overlaySvg.setAttribute("id", "ai-annotation-overlay");
  overlaySvg.setAttribute("width", String(vw));
  overlaySvg.setAttribute("height", String(vh));
  overlaySvg.setAttribute("viewBox", `0 0 ${vw} ${vh}`);
  overlaySvg.style.position = "fixed";
  overlaySvg.style.top = "0";
  overlaySvg.style.left = "0";
  overlaySvg.style.pointerEvents = "none"; // Allow clicks to pass through
  overlaySvg.style.zIndex = 2147483647; // Maximum z-index for top layer

  // Create layer group for organizing annotations
  overlayLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  overlayLayer.setAttribute("data-layer", "annotations");
  overlaySvg.appendChild(overlayLayer);
  document.body.appendChild(overlaySvg);
}

/**
 * Removes all event listeners that trigger overlay updates
 * Cleans up listeners from both main window and iframe windows
 */
function detachUpdateListeners() {
  if (!autoUpdateHandlersAttached) return;
  
  // Remove main window listeners
  try {
    window.removeEventListener("resize", handleWindowUpdate);
    window.removeEventListener("scroll", handleWindowUpdate, true);
  } catch (_) {}
  
  // Remove listeners from iframe windows
  try {
    for (const w of attachedIframeWindows) {
      try {
        w.removeEventListener("resize", handleWindowUpdate);
      } catch (_) {}
      try {
        w.removeEventListener("scroll", handleWindowUpdate, true);
      } catch (_) {}
    }
  } catch (_) {}
  
  attachedIframeWindows = [];
  autoUpdateHandlersAttached = false;
}

/**
 * Handles window resize and scroll events with debounced redrawing
 * Prevents excessive redraw operations during rapid events
 */
function handleWindowUpdate() {
  clearTimeout(redrawTimeoutId);
  redrawTimeoutId = setTimeout(() => {
    try { 
      markPage(lastMarkPageOptions || {}); 
    } catch (_) {}
  }, 150); // 150ms debounce delay
}

/**
 * Attaches event listeners for automatic overlay updates
 * Listens for resize and scroll events on main window and accessible iframes
 */
function attachUpdateListeners() {
  if (autoUpdateHandlersAttached) return;
  
  // Attach to main window
  window.addEventListener("resize", handleWindowUpdate);
  window.addEventListener("scroll", handleWindowUpdate, true); // Capture phase for nested containers
  
  // Best-effort: attach to accessible iframe windows for inner scroll detection
  try {
    attachedIframeWindows = [];
    const iframeWindows = [];
    collectAccessibleIframeWindows(document, iframeWindows);
    
    for (const win of iframeWindows) {
      try {
        win.addEventListener("resize", handleWindowUpdate);
        win.addEventListener("scroll", handleWindowUpdate, true);
        attachedIframeWindows.push(win);
      } catch (_) {} // Cross-origin iframes will fail
    }
  } catch (_) {}
  
  autoUpdateHandlersAttached = true;
}

/**
 * Removes all page annotations and cleans up associated resources
 * This is the main cleanup function that should be called before new annotations
 */
function unmarkPage() {
  // Remove rendering overlay and reset label array
  try { 
    removeOverlay(); 
  } catch (_) {}
  
  labels = [];
  detachUpdateListeners();
  removeOverlay(); // Double cleanup for safety
}