/**
 * iframe Processing and Recursive Content Analysis
 * 
 * This module provides functions for:
 * - Recursively processing iframe content and nested iframes
 * - Handling cross-origin iframe security restrictions
 * - Managing iframe coordinate transformations
 * - Processing shadow DOM content within iframes
 */

/**
 * Recursively processes iframes and their content to extract interactive elements
 * This function handles the complex task of traversing nested iframe structures
 * while respecting security boundaries and coordinate transformations
 * 
 * @param {Document} contextDocument - The document to search for iframes
 * @param {Object} documentOffset - Offset coordinates for coordinate transformation
 * @param {number} depth - Current recursion depth to prevent infinite loops
 * @param {string} frameContext - Context string describing the iframe hierarchy
 * @returns {Array} Array of items found in all accessible iframes
 */
function processIframesRecursively(contextDocument, documentOffset = { x: 0, y: 0 }, depth = 0, frameContext = "") {
    // Prevent infinite recursion by limiting depth
    if (depth > 3) {
        console.warn("Max iframe recursion depth reached");
        return [];
    }
    
    let allIframeItems = [];
    const iframes = contextDocument.querySelectorAll("iframe");
    
    iframes.forEach((iframe, index) => {
        try {
            // Attempt to access iframe content - will fail for cross-origin frames
            const iframeDocument = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDocument) {
                // Calculate coordinate offset for elements within this iframe
                const iframeRect = iframe.getBoundingClientRect();
                const iframeOffset = { 
                    x: documentOffset.x + iframeRect.left, 
                    y: documentOffset.y + iframeRect.top 
                };
                
                // Build frame context string for debugging and identification
                const newFrameContext = frameContext ? 
                    `${frameContext}.iframe[${index}]` : 
                    `iframe[${index}]`;
                
                // Collect all root nodes within this iframe (including shadow roots)
                const frameRoots = [iframeDocument];
                
                // Recursively find all shadow roots within the iframe
                (function collect(root) {
                    try {
                        const qsa = root && root.querySelectorAll ? root.querySelectorAll('*') : [];
                        qsa.forEach((el) => {
                            try {
                                if (el.shadowRoot) {
                                    frameRoots.push(el.shadowRoot);
                                    collect(el.shadowRoot); // Recursively collect nested shadow roots
                                }
                            } catch (_) {
                                // Shadow root access may fail - silently continue
                            }
                        });
                    } catch (_) {
                        // Root access may fail - silently continue
                    }
                })(iframeDocument);

                // Process interactive elements in each root (document + shadow roots)
                for (const frameRoot of frameRoots) {
                    const iframeItems = getInteractiveElements(
                        frameRoot,
                        iframeOffset,
                        true, // includeOutOfViewport - include elements outside iframe viewport
                        newFrameContext
                    );
                    allIframeItems.push(...iframeItems);
                }
                
                // Recursively process nested iframes within this iframe
                const nestedItems = processIframesRecursively(
                    iframeDocument, 
                    iframeOffset, 
                    depth + 1, // Increment depth to track recursion level
                    newFrameContext
                );
                allIframeItems.push(...nestedItems);
            }
        } catch (e) {
            // Log cross-origin iframe access failures for debugging
            console.error(`Could not access iframe content at depth ${depth}. Likely a cross-origin iframe.`, e);
            // Continue processing other iframes even if one fails
        }
    });
    
    return allIframeItems;
}