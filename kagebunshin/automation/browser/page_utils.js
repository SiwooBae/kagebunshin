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
let attachedIframeWindows = [];

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
  // Fallback: remove any stray overlays by id in this document and accessible iframes
  try {
    function removeByIdInDoc(doc) {
      try {
        const nodes = doc.querySelectorAll('#ai-annotation-overlay');
        nodes.forEach((n) => { try { n.parentElement && n.parentElement.removeChild(n); } catch (_) {} });
        const iframes = doc.querySelectorAll('iframe');
        iframes.forEach((iframe) => {
          try {
            const childDoc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
            if (childDoc) removeByIdInDoc(childDoc);
          } catch (_) {}
        });
      } catch (_) {}
    }
    removeByIdInDoc(document);
  } catch (_) {}
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
  // Detach listeners from any iframe windows we attached to
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
  // Best-effort: also listen inside accessible iframes so inner scrolls trigger updates
  try {
    attachedIframeWindows = [];
    const iframeWindows = [];
    collectAccessibleIframeWindows(document, iframeWindows);
    for (const win of iframeWindows) {
      try {
        win.addEventListener("resize", handleWindowUpdate);
        win.addEventListener("scroll", handleWindowUpdate, true);
        attachedIframeWindows.push(win);
      } catch (_) {}
    }
  } catch (_) {}
  autoUpdateHandlersAttached = true;
}

function unmarkPage() {
  // Unmark page logic
  // Remove only the rendering overlay(s); keep data-ai-label attributes for reuse
  try { removeOverlay(); } catch (_) {}
  labels = [];
  detachUpdateListeners();
  removeOverlay();
}

/**
 * Determines the viewport width/height for a given document or shadow root context.
 * @param {Document|ShadowRoot} context
 * @returns {{vw:number, vh:number}}
 */
function getViewportForContext(context) {
  try {
    // Document node
    if (context && context.nodeType === 9) {
      const doc = context;
      const win = doc.defaultView || window;
      const vw = Math.max(doc.documentElement.clientWidth || 0, win.innerWidth || 0);
      const vh = Math.max(doc.documentElement.clientHeight || 0, win.innerHeight || 0);
      return { vw, vh };
    }
    // ShadowRoot node
    if (context && context.host && context.host.ownerDocument) {
      const doc = context.host.ownerDocument;
      const win = doc.defaultView || window;
      const vw = Math.max(doc.documentElement.clientWidth || 0, win.innerWidth || 0);
      const vh = Math.max(doc.documentElement.clientHeight || 0, win.innerHeight || 0);
      return { vw, vh };
    }
  } catch (_) {}
  const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
  const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
  return { vw, vh };
}

/**
 * Recursively collect contentWindow objects for all accessible iframes within a given document.
 * @param {Document} doc
 * @param {Array<Window>} out
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
          collectAccessibleIframeWindows(childDoc, out);
        }
      } catch (_) {}
    });
  } catch (_) {}
}

/**
 * Enhanced element filtering to skip non-interactive elements early.
 * @param {Element} element The element to check.
 * @param {CSSStyleDeclaration} computedStyle Pre-computed style for performance.
 * @returns {Object} Filtering result with reasons.
 */
function shouldSkipElement(element, computedStyle) {
    // Skip non-element nodes early
    if (element.nodeType !== 1) {
        return { skip: true, reason: 'not-element-node' };
    }

    // Early visibility checks
    if (computedStyle.display === 'none' || 
        computedStyle.visibility === 'hidden' || 
        parseFloat(computedStyle.opacity) === 0) {
        return { skip: true, reason: 'hidden-by-css' };
    }

    // Skip elements with pointer events disabled
    if (computedStyle.pointerEvents === 'none') {
        return { skip: true, reason: 'pointer-events-none' };
    }

    // Check for ARIA hidden
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
 * Checks if an element is effectively visible to a user and categorizes viewport position.
 * @param {Element} element The element to check.
 * @param {Node} contextDocument The document or shadow root the element is in.
 * @param {DOMRect} bb The bounding box of the element.
 * @param {boolean} includeOutOfViewport Whether to include elements outside viewport for context.
 * @returns {Object} Object with visibility info and viewport position.
 */
function isEffectivelyVisible(element, contextDocument, bb, includeOutOfViewport = false) {
    // Note: Basic visibility is now checked earlier in shouldSkipElement for performance
    // Use the correct viewport for the element's context (iframe/shadow root/main)
    const { vw, vh } = getViewportForContext(contextDocument);
    
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
                
                // Get items from this iframe document and any nested shadow roots
                const frameRoots = [iframeDocument];
                (function collect(root) {
                    try {
                        const qsa = root && root.querySelectorAll ? root.querySelectorAll('*') : [];
                        qsa.forEach((el) => {
                            try {
                                if (el.shadowRoot) {
                                    frameRoots.push(el.shadowRoot);
                                    collect(el.shadowRoot);
                                }
                            } catch (_) {}
                        });
                    } catch (_) {}
                })(iframeDocument);

                for (const frameRoot of frameRoots) {
                    const iframeItems = getInteractiveElements(
                        frameRoot,
                        iframeOffset,
                        true, // includeOutOfViewport
                        newFrameContext
                    );
                    allIframeItems.push(...iframeItems);
                }
                
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
        // Cache computed style for performance
        const viewForStyle = (element.ownerDocument && element.ownerDocument.defaultView) || window;
        const style = viewForStyle.getComputedStyle(element);
        
        // Basic visibility filtering - but we now include content elements too
        const basicFilterResult = shouldSkipElement(element, style);
        const isInteractive = !basicFilterResult.skip;
        
        // For non-interactive elements, check if they're content we should include
        let includeAsContent = false;
        if (basicFilterResult.skip) {
          // Check if this is a content element we should include
          const tagName = element.tagName ? element.tagName.toLowerCase() : "";
          const textContent = element.textContent ? element.textContent.trim() : "";
          const hasSignificantText = textContent.length > 5; // At least 6 characters
          
          // Include content elements: headings, paragraphs, text containers
          includeAsContent = (
            (tagName.match(/^h[1-6]$/) && hasSignificantText) || // Headings
            (tagName === 'p' && hasSignificantText) || // Paragraphs
            (tagName === 'span' && hasSignificantText && textContent.length > 20) || // Significant spans
            (tagName === 'div' && hasSignificantText && textContent.length > 30) || // Significant divs
            (tagName === 'li' && hasSignificantText) || // List items
            (tagName === 'td' && hasSignificantText) || // Table cells
            (tagName === 'th' && hasSignificantText) || // Table headers
            (tagName === 'section') || // Semantic sections
            (tagName === 'article') || // Articles
            (tagName === 'nav') || // Navigation
            (tagName === 'header') || // Headers
            (tagName === 'footer') || // Footers
            (tagName === 'aside') || // Asides
            (tagName === 'main') || // Main content
            (tagName === 'img' && element.alt) // Images with alt text
          );
        }
        
        // Skip if neither interactive nor content
        if (!isInteractive && !includeAsContent) {
          return {
            element: element,
            include: false,
            skipReason: basicFilterResult.reason || 'not-content',
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
            globalIndex: globalElementIndex++,
            // New unified fields
            isInteractive: false,
            elementRole: 'skipped',
            contentType: null,
            headingLevel: null,
            wordCount: 0,
            truncated: false,
            fullTextAvailable: false,
            parentId: null,
            childIds: [],
            labelFor: null,
            describedBy: null,
            isContainer: false,
            semanticSection: null
          };
        }

        var textualContent = element.textContent ? element.textContent.trim().replace(/\s{2,}/g, " ") : "";
        var elementType = element.tagName ? element.tagName.toLowerCase() : "";
        var ariaLabel = element.getAttribute("aria-label") || "";
        var className = element.className || "";
        var id = element.id || "";

        // Get hierarchical information
        var hierarchicalInfo = getHierarchicalInfo(element);
        
        // Determine element classification
        const elementRole = isInteractive ? 'interactive' : 
                           elementType.match(/^h[1-6]$|p|span|div|li|td|th/) ? 'content' :
                           elementType.match(/^section|article|nav|header|footer|aside|main$/) ? 'structural' :
                           elementType.match(/^nav|menu/) ? 'navigation' : 'content';
        
        // Determine content type for non-interactive elements
        let contentType = null;
        let headingLevel = null;
        if (!isInteractive) {
          if (elementType.match(/^h[1-6]$/)) {
            contentType = 'heading';
            headingLevel = parseInt(elementType.replace('h', ''));
          } else if (elementType === 'p') {
            contentType = 'paragraph';
          } else if (elementType === 'img') {
            contentType = 'image';
          } else if (elementType.match(/^ul|ol|li$/)) {
            contentType = 'list';
          } else if (elementType.match(/^table|tr|td|th$/)) {
            contentType = 'table';
          } else if (elementType.match(/^div|span$/)) {
            contentType = 'container';
          }
        }
        
        // Calculate word count and truncation
        const words = textualContent.split(/\s+/).filter(w => w.length > 0);
        const wordCount = words.length;
        const maxWords = isInteractive ? 50 : 100; // More words for content elements
        const truncated = wordCount > maxWords;
        const displayText = truncated ? words.slice(0, maxWords).join(' ') + '...' : textualContent;
        
        // Determine semantic section
        let semanticSection = null;
        let currentEl = element;
        while (currentEl && currentEl !== document.body) {
          const tag = currentEl.tagName ? currentEl.tagName.toLowerCase() : '';
          if (tag.match(/^header|main|nav|footer|aside$/)) {
            semanticSection = tag;
            break;
          }
          currentEl = currentEl.parentElement;
        }
        
        // Determine if this is a container element
        const isContainer = Boolean(elementType.match(/^div|section|article|nav|header|footer|aside|main|ul|ol$/)) ||
                           (element.children && element.children.length > 0);
        
        // Build parent-child relationships (will be processed later)
        const parentId = null; // Will be set in post-processing
        const childIds = []; // Will be populated in post-processing

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
      const roleAttr = element.getAttribute("role") || "";
      const tabIndexAttr = element.getAttribute("tabindex");
      const tabIndex = tabIndexAttr != null ? parseInt(tabIndexAttr, 10) : NaN;
      const isClickable = 
        element.tagName === "INPUT" ||
        element.tagName === "TEXTAREA" ||
        element.tagName === "SELECT" ||
        element.tagName === "BUTTON" ||
        element.tagName === "A" ||
        element.onclick != null ||
        style.cursor === "pointer" ||
        element.tagName === "IFRAME" ||
        element.tagName === "VIDEO" ||
        element.tagName === "LABEL" ||
        roleAttr === "button" ||
        roleAttr === "link" ||
        roleAttr === "menuitem" ||
        roleAttr === "tab" ||
        roleAttr === "checkbox" ||
        roleAttr === "radio" ||
        roleAttr === "switch" ||
        (!Number.isNaN(tabIndex) && tabIndex >= 0) ||
        element.isContentEditable === true ||
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

      // Enhanced area filtering: skip very small elements unless they're likely icons or have special significance
      const minInteractionSize = 10; // Minimum 10x10px for interaction
      const isLargeEnough = area >= (minInteractionSize * minInteractionSize);
      const isIconSized = area >= 100 && area <= 2500; // 10x10 to 50x50px (likely icons)
      const hasSpecialSignificance = isCaptchaElement || 
                                   (ariaLabel && ariaLabel.trim().length > 0) ||
                                   elementType === 'button' || elementType === 'a';

      // For interactive elements, use original logic
      // For content elements, include if they have significant content or are structural
      const shouldInclude = isInteractive ? 
        (isClickable && (isLargeEnough || isIconSized || hasSpecialSignificance || includeOutOfViewport)) :
        includeAsContent; // Content elements already filtered above

      return {
        element: element,
        include: shouldInclude,
        area,
        rects,
        text: displayText, // Use truncated text
        type: elementType,
        ariaLabel: ariaLabel,
        isCaptcha: isCaptchaElement,
        className: className,
        elementId: id,
        hierarchy: hierarchicalInfo,
        frameContext: frameContext,
        globalIndex: globalElementIndex++,
        // New unified representation fields
        isInteractive: isInteractive,
        elementRole: elementRole,
        contentType: contentType,
        headingLevel: headingLevel,
        wordCount: wordCount,
        truncated: truncated,
        fullTextAvailable: wordCount > maxWords,
        parentId: parentId,
        childIds: childIds,
        labelFor: element.getAttribute('for') ? null : null, // Will need to resolve to globalIndex later
        describedBy: element.getAttribute('aria-describedby') ? null : null, // Will need to resolve later
        isContainer: isContainer,
        semanticSection: semanticSection
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
          globalIndex: globalElementIndex++,
          // New unified representation fields
          isInteractive: false,
          elementRole: 'error',
          contentType: null,
          headingLevel: null,
          wordCount: 0,
          truncated: false,
          fullTextAvailable: false,
          parentId: null,
          childIds: [],
          labelFor: null,
          describedBy: null,
          isContainer: false,
          semanticSection: null
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

    // Clear any existing data-ai-label attributes so new labels are fresh
    try {
      const clearLabelsInRoot = (root) => {
        if (!root) return;
        try {
          const labeled = root.querySelectorAll('[data-ai-label]');
          labeled.forEach((el) => {
            try { el.removeAttribute('data-ai-label'); } catch (e) {}
          });
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

    let allItems = [];
    const rootNodes = [document];
    
    // Add all open shadow roots (recursively) to the list of nodes to search
    (function collect(root) {
        try {
            const qsa = root && root.querySelectorAll ? root.querySelectorAll('*') : [];
            qsa.forEach((el) => {
                try {
                    if (el.shadowRoot) {
                        rootNodes.push(el.shadowRoot);
                        collect(el.shadowRoot);
                    }
                } catch (_) {}
            });
        } catch (_) {}
    })(document);

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

        // Clean rectangle with solid stroke and subtle fill for VLM clarity
        const rectEl = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rectEl.setAttribute("x", String(bbox.left));
        rectEl.setAttribute("y", String(bbox.top));
        rectEl.setAttribute("width", String(bbox.width));
        rectEl.setAttribute("height", String(bbox.height));
        rectEl.setAttribute("fill", color + "40"); // 25% alpha for subtle overlay
        rectEl.setAttribute("stroke", color);
        rectEl.setAttribute("stroke-width", "2"); // Thinner stroke for cleaner lines

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
        // Clean text without stroke for better VLM parsing
        textEl.setAttribute("font-weight", "bold");
        textEl.textContent = labelText;

        // Tooltip for context
        const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
        const shortText = (item.text || '').slice(0, 80);
        title.textContent = `type: ${item.type} role: ${(item.hierarchy && item.hierarchy.semanticRole) || ''}\naria: ${item.ariaLabel || ''}\ntext: ${shortText}${item.text && item.text.length > 80 ? '…' : ''}\nframe: ${item.frameContext || 'main'}`;
        rectEl.appendChild(title);

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
                boundingBox: { left, top, width, height },
                // New unified representation fields
                isInteractive: item.isInteractive,
                elementRole: item.elementRole,
                contentType: item.contentType,
                headingLevel: item.headingLevel,
                wordCount: item.wordCount,
                truncated: item.truncated,
                fullTextAvailable: item.fullTextAvailable,
                parentId: item.parentId,
                childIds: item.childIds,
                labelFor: item.labelFor,
                describedBy: item.describedBy,
                isContainer: item.isContainer,
                semanticSection: item.semanticSection
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