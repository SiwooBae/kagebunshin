/**
 * Utility Functions for KageBunshin Page Analysis
 * 
 * This module provides utility functions for:
 * - Viewport dimension calculations across different contexts
 * - iframe window collection and access management
 * - Cross-document and shadow DOM operations
 */

/**
 * Determines the viewport width/height for a given document or shadow root context
 * Handles different contexts including main documents, shadow roots, and iframe documents
 * 
 * @param {Document|ShadowRoot} context - The document or shadow root context
 * @returns {{vw: number, vh: number}} Object containing viewport width and height
 */
function getViewportForContext(context) {
  try {
    // Document node (nodeType 9)
    if (context && context.nodeType === 9) {
      const doc = context;
      const win = doc.defaultView || window;
      const vw = Math.max(doc.documentElement.clientWidth || 0, win.innerWidth || 0);
      const vh = Math.max(doc.documentElement.clientHeight || 0, win.innerHeight || 0);
      return { vw, vh };
    }
    
    // ShadowRoot node - get dimensions from host document
    if (context && context.host && context.host.ownerDocument) {
      const doc = context.host.ownerDocument;
      const win = doc.defaultView || window;
      const vw = Math.max(doc.documentElement.clientWidth || 0, win.innerWidth || 0);
      const vh = Math.max(doc.documentElement.clientHeight || 0, win.innerHeight || 0);
      return { vw, vh };
    }
  } catch (_) {
    // Fall through to default calculation
  }
  
  // Fallback to main document viewport
  const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
  const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
  return { vw, vh };
}

/**
 * Recursively collects contentWindow objects for all accessible iframes within a document
 * This function traverses nested iframes and collects their window objects for event binding
 * Cross-origin iframes are silently skipped due to security restrictions
 * 
 * @param {Document} doc - The document to search for iframes
 * @param {Array<Window>} out - Output array to collect iframe window objects
 */
function collectAccessibleIframeWindows(doc, out) {
  try {
    const iframes = doc.querySelectorAll('iframe');
    iframes.forEach((iframe) => {
      try {
        const win = iframe.contentWindow;
        const childDoc = iframe.contentDocument || (win && win.document);
        
        if (win && childDoc) {
          out.push(win);
          // Recursively collect from nested iframes
          collectAccessibleIframeWindows(childDoc, out);
        }
      } catch (_) {
        // Cross-origin iframes will throw security errors - silently skip
      }
    });
  } catch (_) {
    // Document access errors - silently skip
  }
}