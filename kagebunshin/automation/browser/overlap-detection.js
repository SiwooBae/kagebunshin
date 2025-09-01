/**
 * Overlap Detection and Deduplication for KageBunshin Annotations
 * 
 * This module provides functions for:
 * - Calculating Intersection over Union (IoU) for bounding boxes
 * - Detecting and resolving overlapping element annotations
 * - Prioritizing interactive elements over containers
 * - Deduplicating elements with similar spatial positions
 * - Smart grouping and representative element selection
 */

/**
 * Calculates the Intersection over Union (IoU) between two bounding boxes
 * IoU is a measure of overlap between two bounding boxes, ranging from 0 (no overlap) to 1 (perfect overlap)
 * 
 * @param {Object} rect1 - First bounding box {left, top, right, bottom, width, height}
 * @param {Object} rect2 - Second bounding box {left, top, right, bottom, width, height}
 * @returns {number} IoU value between 0 and 1
 */
function calculateIoU(rect1, rect2) {
    // Calculate intersection coordinates
    const xLeft = Math.max(rect1.left, rect2.left);
    const yTop = Math.max(rect1.top, rect2.top);
    const xRight = Math.min(rect1.right, rect2.right);
    const yBottom = Math.min(rect1.bottom, rect2.bottom);
    
    // No intersection if coordinates don't make a valid rectangle
    if (xLeft >= xRight || yTop >= yBottom) {
        return 0;
    }
    
    // Calculate areas
    const intersectionArea = (xRight - xLeft) * (yBottom - yTop);
    const rect1Area = rect1.width * rect1.height;
    const rect2Area = rect2.width * rect2.height;
    const unionArea = rect1Area + rect2Area - intersectionArea;
    
    // Avoid division by zero
    if (unionArea === 0) {
        return 0;
    }
    
    return intersectionArea / unionArea;
}

/**
 * Calculates the overlap percentage of the smaller rectangle
 * This is useful for detecting when a smaller element is completely contained within a larger one
 * 
 * @param {Object} rect1 - First bounding box
 * @param {Object} rect2 - Second bounding box  
 * @returns {number} Percentage of smaller rectangle that overlaps (0-1)
 */
function calculateOverlapPercentage(rect1, rect2) {
    const xLeft = Math.max(rect1.left, rect2.left);
    const yTop = Math.max(rect1.top, rect2.top);
    const xRight = Math.min(rect1.right, rect2.right);
    const yBottom = Math.min(rect1.bottom, rect2.bottom);
    
    if (xLeft >= xRight || yTop >= yBottom) {
        return 0;
    }
    
    const intersectionArea = (xRight - xLeft) * (yBottom - yTop);
    const rect1Area = rect1.width * rect1.height;
    const rect2Area = rect2.width * rect2.height;
    const smallerArea = Math.min(rect1Area, rect2Area);
    
    if (smallerArea === 0) {
        return 0;
    }
    
    return intersectionArea / smallerArea;
}

/**
 * Determines element priority for overlap resolution
 * Higher priority elements are kept when resolving overlaps
 * 
 * @param {Object} item - Element item with type, role, and metadata
 * @returns {number} Priority score (higher = more important to keep)
 */
function getElementPriority(item) {
    let priority = 0;
    
    // Interactive elements get higher priority
    if (item.isInteractive) {
        priority += 100;
    }
    
    // Specific interactive elements get bonus priority
    const elementType = item.type.toLowerCase();
    const priorityMap = {
        'button': 50,
        'input': 45,
        'textarea': 45,
        'select': 45,
        'a': 40,
        'label': 35,
        'iframe': 30,
        'video': 25
    };
    priority += priorityMap[elementType] || 0;
    
    // CAPTCHA elements are very important
    if (item.isCaptcha) {
        priority += 75;
    }
    
    // Elements with explicit ARIA roles get bonus
    if (item.ariaLabel && item.ariaLabel.trim().length > 0) {
        priority += 20;
    }
    
    // Focused elements get priority
    if (item.focused) {
        priority += 30;
    }
    
    // Penalize generic containers
    if (elementType === 'div' && !item.isInteractive) {
        priority -= 20;
    }
    
    // Small elements (likely icons/buttons) get slight bonus
    if (item.area > 0 && item.area <= 2500) { // 50x50px or smaller
        priority += 10;
    }
    
    // Elements with specific text content get bonus
    if (item.text && item.text.trim().length > 0 && item.text.length < 100) {
        priority += 15;
    }
    
    return priority;
}

/**
 * Groups overlapping elements and selects the best representative for each group
 * Uses IoU and overlap percentage to determine which elements should be grouped together
 * 
 * @param {Array} items - Array of element items to deduplicate
 * @param {Object} options - Configuration options
 * @param {number} options.iotThreshold - IoU threshold for grouping (default: 0.7)
 * @param {number} options.overlapThreshold - Overlap percentage threshold (default: 0.8)
 * @param {boolean} options.preserveInteractive - Always preserve interactive elements (default: true)
 * @returns {Array} Deduplicated array of element items
 */
function deduplicateOverlappingElements(items, options = {}) {
    const {
        iouThreshold = 0.7,
        overlapThreshold = 0.8,
        preserveInteractive = true
    } = options;
    
    if (!items || items.length === 0) {
        return items;
    }
    
    // Filter out items without valid rectangles
    const validItems = items.filter(item => 
        item.rects && item.rects.length > 0 && 
        item.rects[0].width > 0 && item.rects[0].height > 0
    );
    
    if (validItems.length <= 1) {
        return validItems;
    }
    
    // Create groups of overlapping elements
    const groups = [];
    const processed = new Set();
    
    for (let i = 0; i < validItems.length; i++) {
        if (processed.has(i)) continue;
        
        const currentItem = validItems[i];
        const currentRect = currentItem.rects[0]; // Use primary rectangle
        const group = [{ item: currentItem, index: i }];
        processed.add(i);
        
        // Find all items that overlap significantly with current item
        for (let j = i + 1; j < validItems.length; j++) {
            if (processed.has(j)) continue;
            
            const otherItem = validItems[j];
            const otherRect = otherItem.rects[0];
            
            const iou = calculateIoU(currentRect, otherRect);
            const overlapPct = calculateOverlapPercentage(currentRect, otherRect);
            
            // Group if IoU is high or if one element significantly overlaps another
            if (iou >= iouThreshold || overlapPct >= overlapThreshold) {
                group.push({ item: otherItem, index: j });
                processed.add(j);
            }
        }
        
        groups.push(group);
    }
    
    // Select the best representative from each group
    const deduplicated = [];
    
    for (const group of groups) {
        if (group.length === 1) {
            // No overlap, keep the element
            deduplicated.push(group[0].item);
        } else {
            // Multiple overlapping elements - select the best one
            let bestItem = null;
            let bestPriority = -1;
            
            for (const { item } of group) {
                const priority = getElementPriority(item);
                
                if (priority > bestPriority) {
                    bestPriority = priority;
                    bestItem = item;
                }
            }
            
            // If we're preserving interactive elements, check if we're losing any
            if (preserveInteractive) {
                const interactiveItems = group.filter(({ item }) => item.isInteractive);
                const hasInteractiveInGroup = interactiveItems.length > 0;
                const bestIsInteractive = bestItem && bestItem.isInteractive;
                
                // If we have interactive items but best isn't interactive, pick best interactive
                if (hasInteractiveInGroup && !bestIsInteractive) {
                    let bestInteractive = null;
                    let bestInteractivePriority = -1;
                    
                    for (const { item } of interactiveItems) {
                        const priority = getElementPriority(item);
                        if (priority > bestInteractivePriority) {
                            bestInteractivePriority = priority;
                            bestInteractive = item;
                        }
                    }
                    
                    if (bestInteractive) {
                        bestItem = bestInteractive;
                    }
                }
            }
            
            if (bestItem) {
                // Merge information from other elements in the group if beneficial
                const mergedItem = mergeElementInfo(bestItem, group.map(g => g.item));
                deduplicated.push(mergedItem);
            }
        }
    }
    
    return deduplicated;
}

/**
 * Merges information from overlapping elements to create a more complete representation
 * 
 * @param {Object} primaryItem - The primary element to keep
 * @param {Array} allItems - All elements in the overlap group
 * @returns {Object} Enhanced primary item with merged information
 */
function mergeElementInfo(primaryItem, allItems) {
    const enhanced = { ...primaryItem };
    
    // Collect all text content and pick the most descriptive
    const allTexts = allItems
        .map(item => item.text || '')
        .filter(text => text.trim().length > 0)
        .sort((a, b) => b.length - a.length); // Sort by length, longest first
    
    if (allTexts.length > 0 && allTexts[0].length > (enhanced.text || '').length) {
        enhanced.text = allTexts[0];
    }
    
    // Collect all ARIA labels and pick the most descriptive
    const allAriaLabels = allItems
        .map(item => item.ariaLabel || '')
        .filter(label => label.trim().length > 0)
        .sort((a, b) => b.length - a.length);
        
    if (allAriaLabels.length > 0 && allAriaLabels[0].length > (enhanced.ariaLabel || '').length) {
        enhanced.ariaLabel = allAriaLabels[0];
    }
    
    // If primary isn't interactive but group has interactive elements, mark as interactive
    const hasInteractive = allItems.some(item => item.isInteractive);
    if (hasInteractive && !enhanced.isInteractive) {
        enhanced.isInteractive = true;
        enhanced.elementRole = 'interactive';
    }
    
    // Preserve CAPTCHA status if any element in group is CAPTCHA
    if (allItems.some(item => item.isCaptcha)) {
        enhanced.isCaptcha = true;
    }
    
    // Preserve focus status if any element is focused
    if (allItems.some(item => item.focused)) {
        enhanced.focused = true;
    }
    
    return enhanced;
}

/**
 * Advanced deduplication that considers parent-child relationships
 * Prevents annotating both a container and its interactive children
 * 
 * @param {Array} items - Array of element items
 * @returns {Array} Filtered items with parent-child conflicts resolved
 */
function resolveParentChildConflicts(items) {
    if (!items || items.length <= 1) {
        return items;
    }
    
    const toRemove = new Set();
    
    for (let i = 0; i < items.length; i++) {
        for (let j = 0; j < items.length; j++) {
            if (i === j || toRemove.has(i) || toRemove.has(j)) continue;
            
            const item1 = items[i];
            const item2 = items[j];
            
            // Check if one element contains the other
            try {
                const element1 = item1.element;
                const element2 = item2.element;
                
                if (element1 && element2) {
                    // If element1 contains element2
                    if (element1.contains(element2)) {
                        // Remove the container if the child is interactive
                        if (item2.isInteractive && !item1.isInteractive) {
                            toRemove.add(i);
                        }
                        // Remove the child if it's less specific than the interactive parent
                        else if (item1.isInteractive && !item2.isInteractive) {
                            toRemove.add(j);
                        }
                        // If both are interactive, keep the more specific one (child)
                        else if (item1.isInteractive && item2.isInteractive) {
                            const priority1 = getElementPriority(item1);
                            const priority2 = getElementPriority(item2);
                            if (priority2 > priority1) {
                                toRemove.add(i);
                            } else {
                                toRemove.add(j);
                            }
                        }
                    }
                }
            } catch (e) {
                // Element access failed, skip this comparison
                continue;
            }
        }
    }
    
    return items.filter((_, index) => !toRemove.has(index));
}

/**
 * Main function to apply all overlap detection and deduplication logic
 * 
 * @param {Array} items - Array of element items to process
 * @param {Object} options - Configuration options
 * @returns {Array} Deduplicated and optimized array of element items
 */
function applyOverlapDetection(items, options = {}) {
    console.log(`DEBUG: Starting overlap detection on ${items.length} items`);
    
    // Step 1: Resolve parent-child conflicts
    let filtered = resolveParentChildConflicts(items);
    console.log(`DEBUG: After parent-child resolution: ${filtered.length} items`);
    
    // Step 2: Deduplicate overlapping elements
    filtered = deduplicateOverlappingElements(filtered, options);
    console.log(`DEBUG: After overlap deduplication: ${filtered.length} items`);
    
    return filtered;
}