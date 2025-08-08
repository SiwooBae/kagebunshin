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
let overlaySvg = null;
let overlayLayer = null;
let redrawTimeoutId = null;
let autoUpdateHandlersAttached = false;
let lastMarkPageOptions = null;

// Color-blind friendly palette (Okabe & Ito)
const TYPE_COLORS = {
  button: "#E69F00", // orange
  a: "#0072B2", // blue (links)
  input: "#009E73", // green
  textarea: "#009E73",
  select: "#009E73",
  label: "#CC79A7", // purple
  iframe: "#D55E00", // vermillion
  video: "#56B4E9", // sky blue
  generic: "#BBBBBB", // grey fallback
  captcha: "#F0E442" // yellow
};

function getColorForItem(item) {
  if (item.isCaptcha) return TYPE_COLORS.captcha;
  const tag = (item.type || "").toLowerCase();
  if (TYPE_COLORS[tag]) return TYPE_COLORS[tag];
  // Role-based mapping
  const role = (item.hierarchy && item.hierarchy.semanticRole) || "";
  if (role === "button") return TYPE_COLORS.button;
  return TYPE_COLORS.generic;
}

function removeOverlay() {
  try {
    if (overlaySvg && overlaySvg.parentElement) {
      overlaySvg.parentElement.removeChild(overlaySvg);
    }
  } catch (_) {}
  overlaySvg = null;
  overlayLayer = null;
}

function ensureOverlay() {
  removeOverlay();
  const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
  const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
  overlaySvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  overlaySvg.setAttribute("id", "ai-annotation-overlay");
  overlaySvg.setAttribute("width", String(vw));
  overlaySvg.setAttribute("height", String(vh));
  overlaySvg.setAttribute("viewBox", `0 0 ${vw} ${vh}`);
  overlaySvg.style.position = "fixed";
  overlaySvg.style.top = "0";
  overlaySvg.style.left = "0";
  overlaySvg.style.pointerEvents = "none";
  overlaySvg.style.zIndex = 2147483647;

  // Layer group
  overlayLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  overlayLayer.setAttribute("data-layer", "annotations");
  overlaySvg.appendChild(overlayLayer);
  document.body.appendChild(overlaySvg);
}

function detachUpdateListeners() {
  if (!autoUpdateHandlersAttached) return;
  try {
    window.removeEventListener("resize", handleWindowUpdate);
    window.removeEventListener("scroll", handleWindowUpdate, true);
  } catch (_) {}
  autoUpdateHandlersAttached = false;
}

function handleWindowUpdate() {
  clearTimeout(redrawTimeoutId);
  redrawTimeoutId = setTimeout(() => {
    try { markPage(lastMarkPageOptions || {}); } catch (_) {}
  }, 150);
}

function attachUpdateListeners() {
  if (autoUpdateHandlersAttached) return;
  window.addEventListener("resize", handleWindowUpdate);
  // capture scrolls from nested containers/iframes
  window.addEventListener("scroll", handleWindowUpdate, true);
  autoUpdateHandlersAttached = true;
}

function unmarkPage() {
  // Unmark page logic
  for (const label of labels) {
    if (label.parentElement) {
      label.parentElement.removeChild(label);
    }
  }
  labels = [];
  globalElementIndex = 0;
  detachUpdateListeners();
  removeOverlay();

  // Also clear any stale data-ai-label attributes from current document, shadow roots, and accessible iframes
  try {
    const clearLabelsInRoot = (root) => {
      if (!root) return;
      try {
        // Remove attribute on elements in this root
        const labeled = root.querySelectorAll('[data-ai-label]');
        labeled.forEach((el) => {
          try { el.removeAttribute('data-ai-label'); } catch (e) {}
        });
        // Traverse shadow roots
        if (root.querySelectorAll) {
          root.querySelectorAll('*').forEach((el) => {
            try { if (el.shadowRoot) clearLabelsInRoot(el.shadowRoot); } catch (e) {}
          });
        }
      } catch (e) {}
    };

    // Current document and shadow roots
    clearLabelsInRoot(document);

    // Accessible iframes (best-effort; cross-origin will be skipped)
    const iframes = document.querySelectorAll('iframe');
    iframes.forEach((iframe) => {
      try {
        const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
        clearLabelsInRoot(doc);
      } catch (e) {
        // Ignore cross-origin
      }
    });
  } catch (e) {
    // Best-effort cleanup; ignore errors
  }
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
    lastMarkPageOptions = options;
    
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

    // Use a single SVG overlay for performance and clarity
    ensureOverlay();

    items.forEach(function (item, index) {
      item.element.setAttribute('data-ai-label', index);
      const color = getColorForItem(item);

      item.rects.forEach((bbox) => {
        // Only render in-viewport boxes; keep others in data only
        if (bbox.viewportPosition !== 'in-viewport') return;

        // High-contrast rectangle: black halo + bright colored stroke + stronger fill
        const rectShadow = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rectShadow.setAttribute("x", String(bbox.left));
        rectShadow.setAttribute("y", String(bbox.top));
        rectShadow.setAttribute("width", String(bbox.width));
        rectShadow.setAttribute("height", String(bbox.height));
        rectShadow.setAttribute("fill", "none");
        rectShadow.setAttribute("stroke", "#000000");
        rectShadow.setAttribute("stroke-width", "5");
        rectShadow.setAttribute("opacity", "0.75");

        const rectEl = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rectEl.setAttribute("x", String(bbox.left));
        rectEl.setAttribute("y", String(bbox.top));
        rectEl.setAttribute("width", String(bbox.width));
        rectEl.setAttribute("height", String(bbox.height));
        rectEl.setAttribute("fill", color + "66"); // ~40% alpha for strong contrast
        rectEl.setAttribute("stroke", color);
        rectEl.setAttribute("stroke-width", "3");
        rectEl.setAttribute("stroke-dasharray", "6 4");

        // Create label as SVG (background rect + text)
        const labelText = String(index);
        const approxCharW = 7;
        const labelHeight = 18;
        const labelWidth = (labelText.length * approxCharW) + 8;

        const potentialPositions = [
          { dx: 0, dy: -labelHeight }, // top-left
          { dx: bbox.width - labelWidth, dy: -labelHeight }, // top-right
          { dx: 0, dy: bbox.height }, // bottom-left
          { dx: bbox.width - labelWidth, dy: bbox.height } // bottom-right
        ];

        let best = potentialPositions[0];
        let found = false;
        for (const pos of potentialPositions) {
          const l = bbox.left + pos.dx;
          const t = bbox.top + pos.dy;
          const candidate = { left: l, top: t, right: l + labelWidth, bottom: t + labelHeight };
          if (!labelPositions.some(existing => isOverlapping(candidate, existing))) {
            best = pos; found = true; break;
          }
        }
        const labelLeft = Math.max(0, Math.min(bbox.left + best.dx, overlaySvg.viewBox.baseVal.width - labelWidth));
        const labelTop = Math.max(0, Math.min(bbox.top + best.dy, overlaySvg.viewBox.baseVal.height - labelHeight));

        const finalLabelRect = { left: labelLeft, top: labelTop, right: labelLeft + labelWidth, bottom: labelTop + labelHeight };
        labelPositions.push(finalLabelRect);

        const labelBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        labelBg.setAttribute("x", String(labelLeft));
        labelBg.setAttribute("y", String(labelTop));
        labelBg.setAttribute("width", String(labelWidth));
        labelBg.setAttribute("height", String(labelHeight));
        labelBg.setAttribute("rx", "3");
        labelBg.setAttribute("fill", color);
        labelBg.setAttribute("opacity", "0.95");
        labelBg.setAttribute("stroke", "#000");
        labelBg.setAttribute("stroke-width", "2");

        const textEl = document.createElementNS("http://www.w3.org/2000/svg", "text");
        textEl.setAttribute("x", String(labelLeft + 4));
        textEl.setAttribute("y", String(labelTop + labelHeight - 5));
        textEl.setAttribute("fill", "#ffffff");
        textEl.setAttribute("font-size", "12");
        textEl.setAttribute("font-family", "system-ui, -apple-system, Segoe UI, Roboto, sans-serif");
        // Halo for readability on any background
        textEl.setAttribute("stroke", "#000000");
        textEl.setAttribute("stroke-width", "2");
        textEl.setAttribute("paint-order", "stroke fill");
        textEl.setAttribute("stroke-linejoin", "round");
        textEl.textContent = labelText;

        // Tooltip for context
        const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
        const shortText = (item.text || '').slice(0, 80);
        title.textContent = `type: ${item.type} role: ${(item.hierarchy && item.hierarchy.semanticRole) || ''}\naria: ${item.ariaLabel || ''}\ntext: ${shortText}${item.text && item.text.length > 80 ? '…' : ''}\nframe: ${item.frameContext || 'main'}`;
        rectEl.appendChild(title);

        overlayLayer.appendChild(rectShadow);
        overlayLayer.appendChild(rectEl);
        overlayLayer.appendChild(labelBg);
        overlayLayer.appendChild(textEl);
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

        if (item.rects && item.rects.length > 0) {
            // Choose a single representative rect per item so that bbox_id matches the visual label/index
            // Prefer the rect with the largest area
            let bestRect = item.rects[0];
            let bestArea = bestRect.width * bestRect.height;
            for (let i = 1; i < item.rects.length; i++) {
                const r = item.rects[i];
                const a = r.width * r.height;
                if (a > bestArea) {
                    bestRect = r;
                    bestArea = a;
                }
            }

            const { left, top, width, height, viewportPosition, distanceFromViewport } = bestRect;
            result.coordinates.push({
                x: left + width / 2,
                y: top + height / 2,
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
        }
    });
    
    console.log("DEBUG: Created enhanced result with", result.coordinates.length, "coordinates");
    console.log("DEBUG: Viewport categories:", Object.keys(viewportCategories).map(key => 
        `${key}: ${viewportCategories[key].length}`).join(', '));
    console.log("DEBUG: Frame stats:", result.frameStats);
    
    // Attach lightweight auto-update so labels remain aligned
    attachUpdateListeners();
    return result;
  
  } catch (error) {
    console.error("DEBUG: Error in markPage:", error);
    console.error("DEBUG: Error stack:", error.stack);
    throw error;
  }
}