/**
 * Element Filtering and Visibility Detection for KageBunshin
 * 
 * This module provides functions for:
 * - Filtering out non-interactive or hidden elements early in processing
 * - Determining element visibility and viewport position
 * - Occlusion detection for in-viewport elements
 * - Performance optimization through early filtering
 */

/**
 * Enhanced element filtering to skip non-interactive elements early in processing
 * This function performs early filtering to improve performance by skipping elements
 * that are clearly not suitable for annotation
 * 
 * @param {Element} element - The DOM element to check
 * @param {CSSStyleDeclaration} computedStyle - Pre-computed style for performance
 * @returns {Object} Filtering result with skip flag and reason
 */
function shouldSkipElement(element, computedStyle) {
    // Skip non-element nodes early (text nodes, comments, etc.)
    if (element.nodeType !== 1) {
        return { skip: true, reason: 'not-element-node' };
    }

    // Early visibility checks - CSS-based hiding
    if (computedStyle.display === 'none' || 
        computedStyle.visibility === 'hidden' || 
        parseFloat(computedStyle.opacity) === 0) {
        return { skip: true, reason: 'hidden-by-css' };
    }

    // Skip elements with pointer events disabled
    if (computedStyle.pointerEvents === 'none') {
        return { skip: true, reason: 'pointer-events-none' };
    }

    // Check for ARIA hidden attribute
    if (element.getAttribute('aria-hidden') === 'true') {
        return { skip: true, reason: 'aria-hidden' };
    }

    // Check for disabled state
    if (element.hasAttribute('disabled') || 
        element.getAttribute('aria-disabled') === 'true') {
        // Skip unless it's explicitly interactive (some disabled elements are still clickable)
        const hasClickHandler = element.onclick != null || 
                               element.getAttribute('onclick') != null;
        if (!hasClickHandler) {
            return { skip: true, reason: 'disabled' };
        }
    }

    // Size threshold - skip elements that are too small to interact with
    const rect = element.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) {
        return { skip: true, reason: 'too-small' };
    }

    return { skip: false };
}

/**
 * Checks if an element is effectively visible to a user and categorizes viewport position
 * This function performs comprehensive visibility analysis including viewport positioning
 * and occlusion detection for in-viewport elements
 * 
 * @param {Element} element - The element to check
 * @param {Node} contextDocument - The document or shadow root the element is in
 * @param {DOMRect} bb - The bounding box of the element
 * @param {boolean} includeOutOfViewport - Whether to include elements outside viewport
 * @returns {Object} Object with visibility info and viewport position
 */
function isEffectivelyVisible(element, contextDocument, bb, includeOutOfViewport = false) {
    // Note: Basic visibility is checked earlier in shouldSkipElement for performance
    
    // Use the correct viewport for the element's context (iframe/shadow root/main)
    const { vw, vh } = getViewportForContext(contextDocument);
    
    // Determine viewport position relative to the current viewport
    let viewportPosition = 'in-viewport';
    if (bb.bottom < 0) {
        viewportPosition = 'above-viewport';
    } else if (bb.top > vh) {
        viewportPosition = 'below-viewport';
    } else if (bb.right < 0) {
        viewportPosition = 'left-of-viewport';
    } else if (bb.left > vw) {
        viewportPosition = 'right-of-viewport';
    }

    // If not including out-of-viewport elements and element is outside viewport
    if (!includeOutOfViewport && viewportPosition !== 'in-viewport') {
        return { visible: false, viewportPosition };
    }

    // For elements in viewport, perform occlusion detection
    if (viewportPosition === 'in-viewport') {
        // Test multiple points on the element to detect partial occlusion
        const points = [
            [bb.left + 1, bb.top + 1],           // top-left corner
            [bb.right - 1, bb.top + 1],          // top-right corner
            [bb.left + 1, bb.bottom - 1],        // bottom-left corner
            [bb.right - 1, bb.bottom - 1],       // bottom-right corner
            [bb.left + bb.width / 2, bb.top + bb.height / 2] // center point
        ];

        let visiblePoints = 0;
        for (const [x, y] of points) {
            // Ensure point is within viewport bounds
            if (x > 0 && x < vw && y > 0 && y < vh) {
                const elAtPoint = contextDocument.elementFromPoint(x, y);
                // Element is visible at this point if the point hits the element itself
                // or any of its child elements
                if (elAtPoint === element || element.contains(elAtPoint)) {
                    visiblePoints++;
                }
            }
        }
        
        // Element is considered visible if at least one test point is not occluded
        return { visible: visiblePoints > 0, viewportPosition };
    }

    // For out-of-viewport elements, they're "visible" for context purposes
    // when includeOutOfViewport is true
    return { visible: includeOutOfViewport, viewportPosition };
}