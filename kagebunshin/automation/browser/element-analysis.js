/**
 * Element Analysis and Hierarchical Information Extraction
 * 
 * This module provides functions for:
 * - Analyzing DOM element hierarchy and relationships
 * - Extracting semantic structure information
 * - Computing element positioning within document structure
 * - Generating element type breakdowns for containers
 */

/**
 * Gets comprehensive hierarchical information about a DOM element
 * This function analyzes the element's position in the DOM tree, its relationships
 * with parent and child elements, and provides semantic context
 * 
 * @param {Element} element - The DOM element to analyze
 * @returns {Object} Comprehensive hierarchical information object
 */
function getHierarchicalInfo(element) {
    const hierarchy = [];
    let current = element.parentElement;
    let depth = 0;
    
    // Build hierarchy path up to body element or 5 levels max for performance
    while (current && current !== document.body && depth < 5) {
        const info = {
            tagName: current.tagName.toLowerCase(),
            className: current.className || '',
            id: current.id || '',
            role: current.getAttribute('role') || ''
        };
        hierarchy.push(info);
        current = current.parentElement;
        depth++;
    }
    
    // Get sibling relationship information
    const siblings = element.parentElement ? Array.from(element.parentElement.children) : [];
    const siblingIndex = siblings.indexOf(element);
    const totalSiblings = siblings.length;
    
    // Analyze child elements and their interactivity
    const children = Array.from(element.children);
    const interactiveChildren = children.filter(child => {
        const style = window.getComputedStyle(child);
        return child.tagName === "INPUT" || 
               child.tagName === "BUTTON" || 
               child.tagName === "A" || 
               child.onclick != null || 
               style.cursor === "pointer";
    });
    
    // Create breakdown of child element types (only for elements with >2 children)
    // This helps understand the structure of container elements
    let childrenTypeBreakdown = {};
    if (children.length > 2) {
        const typeCounts = {};
        children.forEach(child => {
            const tag = child.tagName ? child.tagName.toLowerCase() : 'unknown';
            typeCounts[tag] = (typeCounts[tag] || 0) + 1;
        });
        
        // Format as "3 div, 2 a, 1 button" - showing top 3 most common types
        const topTypes = Object.entries(typeCounts)
            .sort((a, b) => b[1] - a[1]) // Sort by count descending
            .slice(0, 3) // Show top 3 types only
            .map(([type, count]) => `${count} <${type}>`)
            .join(', ');
            
        if (topTypes) {
            childrenTypeBreakdown = {
                summary: topTypes,
                total: children.length
            };
        }
    }
    
    // Compile comprehensive hierarchical information
    return {
        depth: hierarchy.length, // How deep in the DOM tree
        hierarchy: hierarchy.reverse(), // Reverse to go from root to element
        siblingIndex: siblingIndex, // Position among siblings
        totalSiblings: totalSiblings, // Total number of siblings
        childrenCount: children.length, // Total child elements
        interactiveChildrenCount: interactiveChildren.length, // Interactive children
        childrenTypeBreakdown: childrenTypeBreakdown, // Summary of child types
        semanticRole: element.getAttribute('role') || element.tagName.toLowerCase() // Semantic meaning
    };
}