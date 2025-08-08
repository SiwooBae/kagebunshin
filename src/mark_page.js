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

const styleTag = document.createElement("style");
styleTag.textContent = customCSS;
document.head.append(styleTag);

let labels = [];
let globalElementIndex = 0;

function unmarkPage() {
  // Unmark page logic
  for (const label of labels) {
    if (label.parentElement) {
      label.parentElement.removeChild(label);
    }
  }
  labels = [];
  globalElementIndex = 0;
}

/**
 * Checks if an element is effectively visible to a user and categorizes viewport position.
 * @param {Element} element The element to check.
 * @param {Node} contextDocument The document or shadow root the element is in.
 * @param {DOMRect} bb The bounding box of the element.
 * @param {boolean} includeOutOfViewport Whether to include elements outside viewport for context.
 * @returns {Object} Object with visibility info and viewport position.
 */
function isEffectivelyVisible(element, contextDocument, bb, includeOutOfViewport = false) {
    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
        return { visible: false, viewportPosition: 'hidden' };
    }

    const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
    
    // Determine viewport position
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

    // For elements in viewport, do occlusion check
    if (viewportPosition === 'in-viewport') {
        const points = [
            [bb.left + 1, bb.top + 1],
            [bb.right - 1, bb.top + 1],
            [bb.left + 1, bb.bottom - 1],
            [bb.right - 1, bb.bottom - 1],
            [bb.left + bb.width / 2, bb.top + bb.height / 2]
        ];

        let visiblePoints = 0;
        for (const [x, y] of points) {
            if (x > 0 && x < vw && y > 0 && y < vh) {
                const elAtPoint = contextDocument.elementFromPoint(x, y);
                if (elAtPoint === element || element.contains(elAtPoint)) {
                    visiblePoints++;
                }
            }
        }
        
        return { visible: visiblePoints > 0, viewportPosition };
    }

    // For out-of-viewport elements, they're "visible" for context purposes
    return { visible: includeOutOfViewport, viewportPosition };
}

/**
 * Gets hierarchical information about an element.
 * @param {Element} element The element to analyze.
 * @returns {Object} Hierarchical information.
 */
function getHierarchicalInfo(element) {
    const hierarchy = [];
    let current = element.parentElement;
    let depth = 0;
    
    // Build hierarchy path up to body or 5 levels max
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
    
    // Get sibling information
    const siblings = element.parentElement ? Array.from(element.parentElement.children) : [];
    const siblingIndex = siblings.indexOf(element);
    const totalSiblings = siblings.length;
    
    // Get child information
    const children = Array.from(element.children);
    const interactiveChildren = children.filter(child => {
        const style = window.getComputedStyle(child);
        return child.tagName === "INPUT" || child.tagName === "BUTTON" || 
               child.tagName === "A" || child.onclick != null || 
               style.cursor === "pointer";
    });
    
    return {
        depth: hierarchy.length,
        hierarchy: hierarchy.reverse(), // Reverse to go from root to element
        siblingIndex: siblingIndex,
        totalSiblings: totalSiblings,
        childrenCount: children.length,
        interactiveChildrenCount: interactiveChildren.length,
        semanticRole: element.getAttribute('role') || element.tagName.toLowerCase()
    };
}

/**
 * Recursively processes iframes and their content.
 * @param {Document} contextDocument The document to search for iframes.
 * @param {Object} documentOffset Offset coordinates for the document.
 * @param {number} depth Current recursion depth to prevent infinite loops.
 * @param {string} frameContext Context string describing the iframe hierarchy.
 * @returns {Array} Array of items found in iframes.
 */
function processIframesRecursively(contextDocument, documentOffset = { x: 0, y: 0 }, depth = 0, frameContext = "") {
    if (depth > 3) { // Prevent infinite recursion
        console.warn("Max iframe recursion depth reached");
        return [];
    }
    
    let allIframeItems = [];
    const iframes = contextDocument.querySelectorAll("iframe");
    
    iframes.forEach((iframe, index) => {
        try {
            const iframeDocument = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDocument) {
                const iframeRect = iframe.getBoundingClientRect();
                const iframeOffset = { 
                    x: documentOffset.x + iframeRect.left, 
                    y: documentOffset.y + iframeRect.top 
                };
                
                const newFrameContext = frameContext ? 
                    `${frameContext}.iframe[${index}]` : 
                    `iframe[${index}]`;
                
                // Get items from this iframe
                const iframeItems = getInteractiveElements(
                    iframeDocument, 
                    iframeOffset, 
                    true, // includeOutOfViewport 
                    newFrameContext
                );
                allIframeItems.push(...iframeItems);
                
                // Recursively process nested iframes
                const nestedItems = processIframesRecursively(
                    iframeDocument, 
                    iframeOffset, 
                    depth + 1, 
                    newFrameContext
                );
                allIframeItems.push(...nestedItems);
            }
        } catch (e) {
            console.error(`Could not access iframe content at depth ${depth}. Likely a cross-origin iframe.`, e);
        }
    });
    
    return allIframeItems;
}

function getInteractiveElements(contextDocument, documentOffset = { x: 0, y: 0 }, includeOutOfViewport = false, frameContext = "") {
  try {
    const allElements = contextDocument.querySelectorAll("*");
    
    const items = Array.prototype.slice
      .call(allElements)
      .map(function (element, index) {
      try {
        var textualContent = element.textContent ? element.textContent.trim().replace(/\s{2,}/g, " ") : "";
        var elementType = element.tagName ? element.tagName.toLowerCase() : "";
        var ariaLabel = element.getAttribute("aria-label") || "";
        var className = element.className || "";
        var id = element.id || "";

        // Get hierarchical information
        var hierarchicalInfo = getHierarchicalInfo(element);

        var rects = [...element.getClientRects()]
            .map((bb) => {
              const visibilityInfo = isEffectivelyVisible(element, contextDocument, bb, includeOutOfViewport);
              if (!visibilityInfo.visible) return null;
              
              const rect = {
                left: bb.left + documentOffset.x,
                top: bb.top + documentOffset.y,
                right: bb.right + documentOffset.x,
                bottom: bb.bottom + documentOffset.y,
              };
              return {
                ...rect,
                width: rect.right - rect.left,
                height: rect.bottom - rect.top,
                viewportPosition: visibilityInfo.viewportPosition
              };
            })
            .filter(rect => rect !== null);

      var area = rects.reduce((acc, rect) => acc + rect.width * rect.height, 0);

      const style = window.getComputedStyle(element);

      // Enhanced CAPTCHA detection
      const isCaptchaElement = 
        (className && className.includes("recaptcha")) || 
        (className && className.includes("g-recaptcha")) ||
        (className && className.includes("rc-")) ||
        (id && id.includes("recaptcha")) ||
        (className && className.includes("hcaptcha")) ||
        (className && className.includes("h-captcha")) ||
        (id && id.includes("hcaptcha")) ||
        (className && className.toLowerCase().includes("captcha")) ||
        (id && id.toLowerCase().includes("captcha")) ||
        (ariaLabel && ariaLabel.toLowerCase().includes("captcha")) ||
        (textualContent && textualContent.toLowerCase().includes("captcha")) ||
        (textualContent && textualContent.toLowerCase().includes("verify")) ||
        (textualContent && textualContent.toLowerCase().includes("i'm not a robot")) ||
        (textualContent && textualContent.toLowerCase().includes("prove you are human")) ||
        (ariaLabel && ariaLabel.toLowerCase().includes("verify")) ||
        (ariaLabel && ariaLabel.includes("security check")) ||
        (elementType === "div" && className && className.includes("checkbox")) ||
        (elementType === "span" && className && className.includes("checkmark"));

      // Enhanced clickable detection
      const isClickable = 
        element.tagName === "INPUT" ||
        element.tagName === "TEXTAREA" ||
        element.tagName === "SELECT" ||
        element.tagName === "BUTTON" ||
        element.tagName === "A" ||
        element.onclick != null ||
        style.cursor == "pointer" ||
        element.tagName === "IFRAME" ||
        element.tagName === "VIDEO" ||
        element.tagName === "LABEL" ||
        (element.tagName === "DIV" && (
          style.cursor === "pointer" ||
          element.onclick != null ||
          element.getAttribute("role") === "button" ||
          element.getAttribute("tabindex") === "0" ||
          (className && className.includes("btn")) ||
          (className && className.includes("button")) ||
          (className && className.includes("clickable")) ||
          (className && className.includes("interactive"))
        )) ||
        (element.tagName === "SPAN" && (
          style.cursor === "pointer" ||
          element.onclick != null ||
          element.getAttribute("role") === "button"
        )) ||
        isCaptchaElement;

      return {
        element: element,
        include: isClickable && (area >= 20 || includeOutOfViewport),
        area,
        rects,
        text: textualContent,
        type: elementType,
        ariaLabel: ariaLabel,
        isCaptcha: isCaptchaElement,
        className: className,
        elementId: id,
        hierarchy: hierarchicalInfo,
        frameContext: frameContext,
        globalIndex: globalElementIndex++
      };
      
      } catch (elementError) {
        // console.error("DEBUG: Error processing element at index", index, ":", elementError);
        return {
          element: element,
          include: false,
          area: 0,
          rects: [],
          text: "",
          type: "",
          ariaLabel: "",
          isCaptcha: false,
          className: "",
          elementId: "",
          hierarchy: {},
          frameContext: frameContext,
          globalIndex: globalElementIndex++
        };
      }
    })
    .filter((item) => item.include);
    
  return items;
  } catch (error) {
    console.error("DEBUG: Error in getInteractiveElements:", error);
    console.error("DEBUG: Error stack:", error.stack);
    throw error;
  }
}

function markPage(options = {}) {
  try {
    console.log("DEBUG: Starting enhanced markPage function");
    const { includeOutOfViewport = true, maxOutOfViewportDistance = 2000 } = options;
    
    unmarkPage();
    console.log("DEBUG: Unmark page completed");

    let allItems = [];
    const rootNodes = [document];
    
    // Add all shadow roots to the list of nodes to search
    document.querySelectorAll('*').forEach(el => {
        if (el.shadowRoot) {
            rootNodes.push(el.shadowRoot);
        }
    });

    console.log(`DEBUG: Found ${rootNodes.length} root nodes (including shadow DOMs)`);

    // Get elements from main document and shadow DOMs
    for (const rootNode of rootNodes) {
        const itemsInNode = getInteractiveElements(
            rootNode, 
            { x: 0, y: 0 }, 
            includeOutOfViewport, 
            ""
        );
        allItems.push(...itemsInNode);
    }

    // Recursively process all iframes
    const iframeItems = processIframesRecursively(document, { x: 0, y: 0 }, 0, "");
    allItems.push(...iframeItems);

    var vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    var vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);

    // Process and categorize items by viewport position
    const viewportCategories = {
        'in-viewport': [],
        'above-viewport': [],
        'below-viewport': [],
        'left-of-viewport': [],
        'right-of-viewport': []
    };

    allItems.forEach(item => {
        // Keep original rects for out-of-viewport items, clip for in-viewport
        item.rects = item.rects.map(bb => {
            if (bb.viewportPosition === 'in-viewport') {
                const rect = {
                    left: Math.max(0, bb.left),
                    top: Math.max(0, bb.top),
                    right: Math.min(vw, bb.right),
                    bottom: Math.min(vh, bb.bottom),
                    viewportPosition: bb.viewportPosition
                };
                return { ...rect, width: rect.right - rect.left, height: rect.bottom - rect.top };
            } else {
                // For out-of-viewport items, keep original coordinates but add distance info
                const distanceFromViewport = bb.viewportPosition === 'above-viewport' 
                    ? Math.abs(bb.bottom) 
                    : bb.viewportPosition === 'below-viewport' 
                    ? Math.abs(bb.top - vh)
                    : bb.viewportPosition === 'left-of-viewport'
                    ? Math.abs(bb.right)
                    : Math.abs(bb.left - vw);
                
                return { 
                    ...bb, 
                    distanceFromViewport,
                    width: bb.width,
                    height: bb.height 
                };
            }
        }).filter(rect => {
            if (rect.viewportPosition === 'in-viewport') {
                return rect.width > 0 && rect.height > 0;
            } else {
                // Include out-of-viewport items within max distance
                return !includeOutOfViewport || rect.distanceFromViewport <= maxOutOfViewportDistance;
            }
        });

        // Categorize items by viewport position
        if (item.rects.length > 0) {
            const position = item.rects[0].viewportPosition;
            if (viewportCategories[position]) {
                viewportCategories[position].push(item);
            }
        }
    });

    let items = allItems.filter(item => item.rects.length > 0);
    items = items.filter((x) => !items.some((y) => x.element.contains(y.element) && !(x == y)));

    function getRandomColor() {
        var letters = "0123456789ABCDEF";
        var color = "#";
        for (var i = 0; i < 6; i++) {
            color += letters[Math.floor(Math.random() * 16)];
        }
        return color;
    }

    const labelPositions = [];
    function isOverlapping(rect1, rect2) {
        return !(rect1.right < rect2.left || rect1.left > rect2.right || rect1.bottom < rect2.top || rect1.top > rect2.bottom);
    }

    items.forEach(function (item, index) {
        item.element.setAttribute('data-ai-label', index);
        item.rects.forEach((bbox) => {
            const newElement = document.createElement("div");
            const borderColor = getRandomColor();
            newElement.style.outline = `2px dashed ${borderColor}`;
            newElement.style.position = "fixed";
            newElement.style.left = bbox.left + "px";
            newElement.style.top = bbox.top + "px";
            newElement.style.width = bbox.width + "px";
            newElement.style.height = bbox.height + "px";
            newElement.style.pointerEvents = "none";
            newElement.style.boxSizing = "border-box";
            newElement.style.zIndex = 2147483647;

            const label = document.createElement("span");
            label.textContent = index;
            label.style.position = "absolute";
            label.style.background = borderColor;
            label.style.color = "white";
            label.style.padding = "2px 4px";
            label.style.fontSize = "12px";
            label.style.borderRadius = "2px";
            
            // De-conflict label positions
            const labelHeight = 18;
            const labelWidth = (label.textContent.length * 8) + 8;
            const potentialPositions = [
                { top: -labelHeight, left: 0 }, // Top-left
                { top: -labelHeight, left: bbox.width - labelWidth }, // Top-right
                { top: bbox.height, left: 0 }, // Bottom-left
                { top: bbox.height, left: bbox.width - labelWidth }  // Bottom-right
            ];

            let bestPosition = potentialPositions[0];
            let foundPosition = false;
            for (const pos of potentialPositions) {
                const labelRect = {
                    left: bbox.left + pos.left,
                    top: bbox.top + pos.top,
                    right: bbox.left + pos.left + labelWidth,
                    bottom: bbox.top + pos.top + labelHeight
                };
                if (!labelPositions.some(existing => isOverlapping(labelRect, existing))) {
                    bestPosition = pos;
                    foundPosition = true;
                    break;
                }
            }
            
            label.style.top = bestPosition.top + "px";
            label.style.left = bestPosition.left + "px";
            
            const finalLabelRect = {
                left: bbox.left + bestPosition.left,
                top: bbox.top + bestPosition.top,
                right: bbox.left + bestPosition.left + labelWidth,
                bottom: bbox.top + bestPosition.top + labelHeight
            };
            labelPositions.push(finalLabelRect);

            newElement.appendChild(label);
            document.body.appendChild(newElement);
            labels.push(newElement);
        });
    });

    console.log("DEBUG: About to create coordinates from", items.length, "items");
    
    // Enhanced coordinate structure with hierarchical and viewport context
    const result = {
        coordinates: [],
        viewportCategories: viewportCategories,
        totalElements: items.length,
        frameStats: {
            totalFrames: 0,
            accessibleFrames: 0,
            maxDepth: 0
        }
    };
    
    items.forEach((item, index) => {
        const selector = `[data-ai-label="${index}"]`;
        
        // Update frame statistics
        if (item.frameContext) {
            const depth = item.frameContext.split('.').length;
            result.frameStats.maxDepth = Math.max(result.frameStats.maxDepth, depth);
            result.frameStats.totalFrames++;
            if (item.rects.length > 0) {
                result.frameStats.accessibleFrames++;
            }
        }
        
        item.rects.forEach(({ left, top, width, height, viewportPosition, distanceFromViewport }) => {
            result.coordinates.push({
                x: (left + left + width) / 2,
                y: (top + top + height) / 2,
                type: item.type,
                text: item.text,
                ariaLabel: item.ariaLabel,
                isCaptcha: item.isCaptcha,
                className: item.className,
                elementId: item.elementId,
                selector: selector,
                // Enhanced properties
                hierarchy: item.hierarchy,
                frameContext: item.frameContext || "main",
                viewportPosition: viewportPosition || 'in-viewport',
                distanceFromViewport: distanceFromViewport || 0,
                globalIndex: item.globalIndex,
                boundingBox: { left, top, width, height }
            });
        });
    });
    
    console.log("DEBUG: Created enhanced result with", result.coordinates.length, "coordinates");
    console.log("DEBUG: Viewport categories:", Object.keys(viewportCategories).map(key => 
        `${key}: ${viewportCategories[key].length}`).join(', '));
    console.log("DEBUG: Frame stats:", result.frameStats);
    
    return result;
  
  } catch (error) {
    console.error("DEBUG: Error in markPage:", error);
    console.error("DEBUG: Error stack:", error.stack);
    throw error;
  }
}