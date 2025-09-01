/**
 * Utility Functions for KageBunshin Page Analysis
 * 
 * This module provides utility functions for:
 * - Viewport dimension calculations across different contexts
 * - iframe window collection and access management
 * - Cross-document and shadow DOM operations
 * - Z-index and stacking context analysis
 * - Element layering and occlusion detection
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

/**
 * Z-Index and Stacking Context Analysis Functions
 * These functions help determine element layering and stacking order for occlusion detection
 */

/**
 * Gets the effective z-index value for an element, considering stacking contexts
 * 
 * @param {Element} element - The element to analyze
 * @returns {Object} Object containing z-index information
 */
function getEffectiveZIndex(element) {
    if (!element || element.nodeType !== 1) {
        return { zIndex: 0, hasStackingContext: false, computedZIndex: 'auto' };
    }
    
    try {
        const computedStyle = window.getComputedStyle(element);
        const zIndexValue = computedStyle.zIndex;
        const position = computedStyle.position;
        const opacity = parseFloat(computedStyle.opacity);
        const transform = computedStyle.transform;
        const filter = computedStyle.filter;
        
        // Determine if element creates a stacking context
        const hasStackingContext = (
            zIndexValue !== 'auto' && (position === 'relative' || position === 'absolute' || position === 'fixed') ||
            position === 'sticky' ||
            opacity < 1 ||
            transform !== 'none' ||
            filter !== 'none' ||
            computedStyle.isolation === 'isolate' ||
            computedStyle.mixBlendMode !== 'normal' ||
            computedStyle.webkitBackdropFilter !== 'none' ||
            computedStyle.backdropFilter !== 'none'
        );
        
        // Convert z-index to number
        let numericZIndex = 0;
        if (zIndexValue !== 'auto') {
            const parsed = parseInt(zIndexValue, 10);
            if (!isNaN(parsed)) {
                numericZIndex = parsed;
            }
        }
        
        return {
            zIndex: numericZIndex,
            hasStackingContext,
            computedZIndex: zIndexValue,
            position,
            opacity,
            transform: transform !== 'none',
            filter: filter !== 'none'
        };
    } catch (e) {
        return { zIndex: 0, hasStackingContext: false, computedZIndex: 'auto' };
    }
}

/**
 * Builds the stacking context chain for an element
 * Returns array of elements that create stacking contexts from root to element
 * 
 * @param {Element} element - The element to analyze
 * @returns {Array} Array of stacking context information objects
 */
function getStackingContextChain(element) {
    const chain = [];
    let current = element;
    
    while (current && current !== document.documentElement) {
        const zInfo = getEffectiveZIndex(current);
        
        if (zInfo.hasStackingContext) {
            chain.unshift({
                element: current,
                zIndex: zInfo.zIndex,
                computedZIndex: zInfo.computedZIndex,
                tagName: current.tagName.toLowerCase(),
                className: current.className || '',
                id: current.id || ''
            });
        }
        
        current = current.parentElement;
    }
    
    return chain;
}

/**
 * Compares stacking order between two elements
 * Returns positive if element1 is in front, negative if behind, 0 if same level
 * 
 * @param {Element} element1 - First element to compare
 * @param {Element} element2 - Second element to compare
 * @returns {number} Comparison result (-1, 0, 1)
 */
function compareStackingOrder(element1, element2) {
    if (!element1 || !element2 || element1 === element2) {
        return 0;
    }
    
    try {
        // Get stacking context chains for both elements
        const chain1 = getStackingContextChain(element1);
        const chain2 = getStackingContextChain(element2);
        
        // If one element contains the other, the child is in front
        if (element1.contains(element2)) {
            return -1; // element2 (child) is in front
        }
        if (element2.contains(element1)) {
            return 1; // element1 (child) is in front
        }
        
        // Compare stacking context chains
        const minLength = Math.min(chain1.length, chain2.length);
        
        for (let i = 0; i < minLength; i++) {
            const context1 = chain1[i];
            const context2 = chain2[i];
            
            if (context1.element === context2.element) {
                continue; // Same stacking context, check next level
            }
            
            // Different stacking contexts at same level - compare z-index
            if (context1.zIndex !== context2.zIndex) {
                return context1.zIndex > context2.zIndex ? 1 : -1;
            }
            
            // Same z-index - compare document order
            const position = context1.element.compareDocumentPosition(context2.element);
            if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
                return -1; // element2 comes after element1 in document order (later = in front)
            } else if (position & Node.DOCUMENT_POSITION_PRECEDING) {
                return 1; // element1 comes after element2 in document order
            }
        }
        
        // If chains are same up to min length, longer chain is in front
        if (chain1.length !== chain2.length) {
            return chain1.length > chain2.length ? 1 : -1;
        }
        
        // Fall back to document order comparison
        const position = element1.compareDocumentPosition(element2);
        if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
            return -1;
        } else if (position & Node.DOCUMENT_POSITION_PRECEDING) {
            return 1;
        }
        
        return 0;
    } catch (e) {
        console.warn('Error comparing stacking order:', e);
        return 0;
    }
}

/**
 * Checks if element1 is behind element2 in the stacking order
 * 
 * @param {Element} element1 - Element to check if behind
 * @param {Element} element2 - Element to check if in front
 * @returns {boolean} True if element1 is behind element2
 */
function isElementBehind(element1, element2) {
    return compareStackingOrder(element1, element2) < 0;
}

/**
 * Gets all elements that could potentially occlude the given element
 * Returns elements that are at the same position or in front in stacking order
 * 
 * @param {Element} element - The element to check for occluders
 * @param {DOMRect} boundingBox - The bounding box of the element
 * @param {Document} contextDocument - The document context
 * @returns {Array} Array of potentially occluding elements
 */
function getPotentialOccluders(element, boundingBox, contextDocument = document) {
    const occluders = [];
    const elementZInfo = getEffectiveZIndex(element);
    
    try {
        // Get all elements that intersect with the bounding box
        const allElements = contextDocument.querySelectorAll('*');
        
        for (const otherElement of allElements) {
            if (otherElement === element) continue;
            
            // Quick bounding box intersection test
            const otherRect = otherElement.getBoundingClientRect();
            if (otherRect.width === 0 || otherRect.height === 0) continue;
            
            // Check if rectangles intersect
            const intersects = !(
                boundingBox.right < otherRect.left ||
                boundingBox.left > otherRect.right ||
                boundingBox.bottom < otherRect.top ||
                boundingBox.top > otherRect.bottom
            );
            
            if (!intersects) continue;
            
            // Check if the other element is in front in stacking order
            if (compareStackingOrder(element, otherElement) < 0) {
                occluders.push(otherElement);
            }
        }
    } catch (e) {
        console.warn('Error finding potential occluders:', e);
    }
    
    return occluders;
}