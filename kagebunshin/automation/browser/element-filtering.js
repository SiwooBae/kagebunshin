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
 * and advanced occlusion detection with visibility percentage calculation
 * 
 * @param {Element} element - The element to check
 * @param {Node} contextDocument - The document or shadow root the element is in
 * @param {DOMRect} bb - The bounding box of the element
 * @param {boolean} includeOutOfViewport - Whether to include elements outside viewport
 * @param {Object} options - Additional options for visibility detection
 * @param {number} options.minVisibilityPercentage - Minimum visibility percentage (0-1, default: 0.3)
 * @param {boolean} options.useAdvancedOcclusion - Use z-index aware occlusion detection (default: true)
 * @param {number} options.testPoints - Number of test points (9, 16, or 25, default: 9)
 * @returns {Object} Object with visibility info, viewport position, and visibility percentage
 */
function isEffectivelyVisible(element, contextDocument, bb, includeOutOfViewport = false, options = {}) {
    const {
        minVisibilityPercentage = 0.3,
        useAdvancedOcclusion = true,
        testPoints = 9
    } = options;
    
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
        return { visible: false, viewportPosition, visibilityPercentage: 0 };
    }

    // For elements in viewport, perform advanced occlusion detection
    if (viewportPosition === 'in-viewport') {
        const visibilityResult = calculateElementVisibility(element, contextDocument, bb, vw, vh, {
            testPoints,
            useAdvancedOcclusion
        });
        
        const isVisible = visibilityResult.visibilityPercentage >= minVisibilityPercentage;
        
        return { 
            visible: isVisible, 
            viewportPosition,
            visibilityPercentage: visibilityResult.visibilityPercentage,
            occludedBy: visibilityResult.occludedBy || []
        };
    }

    // For out-of-viewport elements, they're "visible" for context purposes
    // when includeOutOfViewport is true
    return { 
        visible: includeOutOfViewport, 
        viewportPosition,
        visibilityPercentage: includeOutOfViewport ? 1 : 0 
    };
}

/**
 * Calculates detailed visibility information for an in-viewport element
 * Uses multiple test points and z-index analysis for accurate occlusion detection
 * 
 * @param {Element} element - The element to analyze
 * @param {Node} contextDocument - The document context
 * @param {DOMRect} bb - The bounding box
 * @param {number} vw - Viewport width
 * @param {number} vh - Viewport height
 * @param {Object} options - Calculation options
 * @returns {Object} Detailed visibility information
 */
function calculateElementVisibility(element, contextDocument, bb, vw, vh, options = {}) {
    const { testPoints = 9, useAdvancedOcclusion = true } = options;
    
    // Generate test points in a grid pattern
    const points = generateTestPoints(bb, testPoints);
    const occludedBy = new Set();
    let visiblePoints = 0;
    let totalValidPoints = 0;

    for (const [x, y] of points) {
        // Ensure point is within viewport bounds
        if (x <= 0 || x >= vw || y <= 0 || y >= vh) {
            continue;
        }
        
        totalValidPoints++;
        
        const elAtPoint = contextDocument.elementFromPoint(x, y);
        if (!elAtPoint) {
            continue;
        }
        
        // Element is visible at this point if the point hits the element itself
        // or any of its child elements
        if (elAtPoint === element || element.contains(elAtPoint)) {
            visiblePoints++;
        } else if (useAdvancedOcclusion) {
            // Advanced occlusion: check if the occluding element is actually in front
            const isActuallyOccluded = isElementActuallyOccluded(element, elAtPoint);
            
            if (isActuallyOccluded) {
                occludedBy.add(elAtPoint);
            } else {
                // Not actually occluded (e.g., transparent overlay, same z-level)
                visiblePoints++;
            }
        } else {
            // Basic occlusion: different element at this point means occlusion
            occludedBy.add(elAtPoint);
        }
    }
    
    const visibilityPercentage = totalValidPoints > 0 ? visiblePoints / totalValidPoints : 0;
    
    return {
        visibilityPercentage,
        visiblePoints,
        totalValidPoints,
        occludedBy: Array.from(occludedBy)
    };
}

/**
 * Generates test points for visibility detection based on element size and requested density
 * 
 * @param {DOMRect} bb - The bounding box
 * @param {number} numPoints - Requested number of test points (9, 16, or 25)
 * @returns {Array} Array of [x, y] coordinate pairs
 */
function generateTestPoints(bb, numPoints = 9) {
    const points = [];
    let gridSize;
    
    // Determine grid size based on requested points
    switch (numPoints) {
        case 16:
            gridSize = 4;
            break;
        case 25:
            gridSize = 5;
            break;
        default:
            gridSize = 3; // 9 points
    }
    
    // For very small elements, use fewer points
    if (bb.width < 20 || bb.height < 20) {
        gridSize = 2; // 4 points for small elements
    }
    
    // Generate grid of points
    for (let i = 0; i < gridSize; i++) {
        for (let j = 0; j < gridSize; j++) {
            const x = bb.left + (bb.width * (i + 0.5)) / gridSize;
            const y = bb.top + (bb.height * (j + 0.5)) / gridSize;
            points.push([x, y]);
        }
    }
    
    // Always include center point for critical visibility
    const centerX = bb.left + bb.width / 2;
    const centerY = bb.top + bb.height / 2;
    if (!points.some(([x, y]) => Math.abs(x - centerX) < 1 && Math.abs(y - centerY) < 1)) {
        points.push([centerX, centerY]);
    }
    
    return points;
}

/**
 * Determines if an element is actually occluded by another element
 * Uses z-index analysis and transparency detection
 * 
 * @param {Element} element - The element being checked
 * @param {Element} potentialOccluder - The element that might be occluding
 * @returns {boolean} True if element is actually occluded
 */
function isElementActuallyOccluded(element, potentialOccluder) {
    if (!element || !potentialOccluder || element === potentialOccluder) {
        return false;
    }
    
    try {
        // If the potential occluder contains the element, it's not occlusion
        if (potentialOccluder.contains(element)) {
            return false;
        }
        
        // Check z-index stacking order if available
        if (typeof compareStackingOrder === 'function') {
            const stackingOrder = compareStackingOrder(element, potentialOccluder);
            if (stackingOrder > 0) {
                // Element is in front of potential occluder
                return false;
            }
        }
        
        // Check if the occluder is transparent or has low opacity
        const occluderStyle = window.getComputedStyle(potentialOccluder);
        const opacity = parseFloat(occluderStyle.opacity);
        
        if (opacity < 0.1) {
            // Very transparent, not a real occluder
            return false;
        }
        
        // Check for pointer-events: none (click-through elements)
        if (occluderStyle.pointerEvents === 'none') {
            return false;
        }
        
        // Check background/content visibility
        const hasVisibleBackground = (
            occluderStyle.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
            occluderStyle.backgroundColor !== 'transparent'
        ) || (
            occluderStyle.backgroundImage !== 'none'
        );
        
        const hasVisibleContent = potentialOccluder.textContent && 
                                 potentialOccluder.textContent.trim().length > 0;
        
        const hasVisibleBorder = occluderStyle.borderWidth && 
                                parseFloat(occluderStyle.borderWidth) > 0 &&
                                occluderStyle.borderColor !== 'transparent';
        
        // If occluder has no visible content, background, or border, it's not really occluding
        if (!hasVisibleBackground && !hasVisibleContent && !hasVisibleBorder) {
            return false;
        }
        
        return true;
    } catch (e) {
        // If we can't analyze, assume it's occluding to be safe
        return true;
    }
}