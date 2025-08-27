/**
 * Interactive Elements Discovery and Processing
 * 
 * This module contains the core logic for discovering and processing interactive
 * and content elements on a page. It provides:
 * - Comprehensive element analysis and classification
 * - Interactive and content element identification
 * - Rich metadata extraction for forms, links, and media
 * - Unified element representation with hierarchical context
 * - CAPTCHA detection and special element handling
 */

/**
 * Main function to discover and process interactive and content elements within a document context
 * This function performs comprehensive analysis of all elements, extracting rich metadata
 * and creating a unified representation suitable for LLM consumption
 * 
 * @param {Document|ShadowRoot} contextDocument - The document or shadow root to process
 * @param {Object} documentOffset - Coordinate offset for this document context
 * @param {boolean} includeOutOfViewport - Whether to include elements outside viewport
 * @param {string} frameContext - String identifying the iframe context
 * @returns {Array} Array of processed element items with rich metadata
 */
function getInteractiveElements(contextDocument, documentOffset = { x: 0, y: 0 }, includeOutOfViewport = false, frameContext = "") {
  try {
    const allElements = contextDocument.querySelectorAll("*");
    
    const items = Array.prototype.slice
      .call(allElements)
      .map(function (element, index) {
      try {
        // Cache computed style for performance optimization
        const viewForStyle = (element.ownerDocument && element.ownerDocument.defaultView) || window;
        const style = viewForStyle.getComputedStyle(element);
        
        // Perform basic element filtering for performance
        const basicFilterResult = shouldSkipElement(element, style);
        const isInteractive = !basicFilterResult.skip;
        
        // For non-interactive elements, determine if they should be included as content
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
          return createSkippedElementItem(element, basicFilterResult, frameContext);
        }

        // Extract basic element information
        var textualContent = element.textContent ? element.textContent.trim().replace(/\s{2,}/g, " ") : "";
        var elementType = element.tagName ? element.tagName.toLowerCase() : "";
        var ariaLabel = element.getAttribute("aria-label") || "";
        var className = element.className || "";
        var id = element.id || "";

        // Enhanced image context extraction
        if (elementType === 'img') {
          textualContent = extractImageContext(element);
        }

        // Enhanced link context extraction with URL cleaning
        let linkHref = '';
        if (elementType === 'a') {
          linkHref = extractLinkContext(element);
        }

        // Enhanced input field metadata extraction
        let inputMetadata = {};
        let formContext = {};
        if (elementType === 'input' || elementType === 'textarea' || elementType === 'select') {
          const inputData = extractInputMetadata(element, textualContent, elementType);
          inputMetadata = inputData.metadata;
          formContext = inputData.formContext;
          textualContent = inputData.textContent;
        }

        // Get hierarchical information for DOM structure analysis
        var hierarchicalInfo = getHierarchicalInfo(element);
        
        // Determine element classification and semantic information
        const elementRole = isInteractive ? 'interactive' : 
                           elementType.match(/^h[1-6]$|p|span|div|li|td|th/) ? 'content' :
                           elementType.match(/^section|article|nav|header|footer|aside|main$/) ? 'structural' :
                           elementType.match(/^nav|menu/) ? 'navigation' : 'content';
        
        // Determine content type for non-interactive elements
        const contentData = determineContentType(elementType, isInteractive);
        
        // Calculate word count and apply intelligent truncation
        const textData = processTextContent(textualContent, isInteractive);
        
        // Determine semantic section context
        const semanticSection = determineSemanticSection(element);
        
        // Determine if this is a container element
        const isContainer = Boolean(elementType.match(/^div|section|article|nav|header|footer|aside|main|ul|ol$/)) ||
                           (element.children && element.children.length > 0);
        
        // Build parent-child relationships (will be processed later)
        const parentId = null; // Will be set in post-processing
        const childIds = []; // Will be populated in post-processing

        // Process element bounding rectangles with viewport analysis
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
      const isCaptchaElement = detectCaptcha(element, className, id, ariaLabel, textualContent, elementType);

      // Enhanced clickable element detection
      const isClickable = detectClickable(element, elementType, style, className, ariaLabel, isCaptchaElement);

      // Enhanced area filtering with special significance detection
      const shouldInclude = determineInclusion(area, isInteractive, isClickable, isCaptchaElement, 
                                              ariaLabel, elementType, includeOutOfViewport, includeAsContent);

      // Detect if this element currently has focus
      const isFocused = (element === contextDocument.activeElement);

      return createElementItem(element, shouldInclude, area, rects, textData.displayText, elementType,
                              ariaLabel, isCaptchaElement, className, id, hierarchicalInfo, frameContext,
                              linkHref, inputMetadata, formContext, isInteractive, elementRole,
                              contentData.contentType, contentData.headingLevel, textData.wordCount,
                              textData.truncated, textData.fullTextAvailable, parentId, childIds,
                              isContainer, semanticSection, isFocused);
      
      } catch (elementError) {
        // Return error placeholder for failed elements
        return createErrorElementItem(element, frameContext);
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

/**
 * Helper Functions for Element Processing
 */

/**
 * Creates a skipped element item for elements that don't meet inclusion criteria
 */
function createSkippedElementItem(element, basicFilterResult, frameContext) {
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
    href: "",
    inputMetadata: {},
    formContext: {},
    // Unified fields
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
    semanticSection: null,
    focused: false
  };
}

/**
 * Extracts image context from img elements
 */
function extractImageContext(element) {
  const alt = element.getAttribute('alt') || '';
  const title = element.getAttribute('title') || '';
  const src = element.getAttribute('src') || '';
  
  if (alt) return alt;
  if (title) return title;
  if (src) {
    try {
      const filename = src.split('/').pop().split('?')[0];
      if (filename && filename !== src) {
        return `image: ${filename}`;
      }
    } catch (e) {
      // Fallback if URL parsing fails
    }
  }
  return '';
}

/**
 * Extracts and cleans link context from anchor elements
 */
function extractLinkContext(element) {
  const href = element.getAttribute('href');
  if (!href) return '';
  
  try {
    let cleanHref = href;
    if (href.includes('?')) {
      const url = new URL(href, window.location.origin);
      const paramsToKeep = ['id', 'category', 'search', 'q', 'page'];
      const newParams = new URLSearchParams();
      for (const [key, value] of url.searchParams) {
        if (paramsToKeep.some(keep => key.toLowerCase().includes(keep))) {
          newParams.set(key, value);
        }
      }
      url.search = newParams.toString();
      cleanHref = url.pathname + (url.search ? '?' + url.search : '');
    }
    return cleanHref;
  } catch (e) {
    return href;
  }
}

/**
 * Extracts comprehensive metadata from input elements
 */
function extractInputMetadata(element, textualContent, elementType) {
  const placeholder = element.getAttribute('placeholder') || '';
  const value = element.value || '';
  const inputType = element.getAttribute('type') || 'text';
  
  const metadata = {
    placeholder: placeholder,
    value: value,
    inputType: inputType
  };
  
  let updatedTextContent = textualContent;
  if (!updatedTextContent && placeholder) {
    updatedTextContent = `[${placeholder}]`;
  } else if (!updatedTextContent && inputType) {
    updatedTextContent = `[${inputType} input]`;
  }
  
  // Form association context
  const form = element.closest('form');
  let formContext = {};
  if (form) {
    formContext = {
      id: form.id || form.getAttribute('name') || '',
      action: form.getAttribute('action') || '',
      method: form.getAttribute('method') || 'get'
    };
  }
  
  // Label association
  const elementId = element.id;
  if (elementId) {
    const label = document.querySelector(`label[for="${elementId}"]`);
    if (label && label.textContent) {
      metadata.labelText = label.textContent.trim();
      if (!updatedTextContent || updatedTextContent === `[${inputType} input]`) {
        updatedTextContent = label.textContent.trim();
      }
    }
  }
  
  return { metadata, formContext, textContent: updatedTextContent };
}

/**
 * Determines content type and heading level for elements
 */
function determineContentType(elementType, isInteractive) {
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
  
  return { contentType, headingLevel };
}

/**
 * Processes text content with intelligent truncation
 */
function processTextContent(textualContent, isInteractive) {
  const words = textualContent.split(/\s+/).filter(w => w.length > 0);
  const wordCount = words.length;
  const maxWords = isInteractive ? 50 : 100; // More words for content elements
  const truncated = wordCount > maxWords;
  
  let displayText;
  if (truncated) {
    // Improved truncation that preserves start and end context
    const startWords = Math.floor(maxWords * 0.7);
    const endWords = Math.floor(maxWords * 0.2);
    const remainingWords = maxWords - startWords - endWords;
    
    if (remainingWords >= 0) {
      const start = words.slice(0, startWords).join(' ');
      const end = words.slice(-endWords).join(' ');
      displayText = `${start}...${end}`;
    } else {
      displayText = words.slice(0, maxWords).join(' ') + '...';
    }
  } else {
    displayText = textualContent;
  }
  
  return {
    displayText,
    wordCount,
    truncated,
    fullTextAvailable: wordCount > maxWords
  };
}

/**
 * Determines semantic section context for an element
 */
function determineSemanticSection(element) {
  let semanticSection = null;
  let currentEl = element;
  
  while (currentEl && currentEl !== document.body) {
    const tag = currentEl.tagName ? currentEl.tagName.toLowerCase() : '';
    const role = currentEl.getAttribute('role');
    
    // Check for explicit ARIA roles first
    if (role) {
      const roleMap = {
        'main': 'main',
        'banner': 'header',
        'navigation': 'nav',
        'contentinfo': 'footer',
        'complementary': 'aside',
        'search': 'search',
        'form': 'form'
      };
      if (roleMap[role.toLowerCase()]) {
        semanticSection = roleMap[role.toLowerCase()];
        break;
      }
    }
    
    // Check for semantic HTML5 elements
    if (tag.match(/^header|main|nav|footer|aside|section|article$/)) {
      semanticSection = tag;
      break;
    }
    
    // Check for common class patterns
    const className = currentEl.className ? currentEl.className.toLowerCase() : '';
    if (className) {
      const classMap = {
        'header': 'header', 'navbar': 'header',
        'footer': 'footer',
        'sidebar': 'aside', 'aside': 'aside',
        'main': 'main', 'content': 'main',
        'nav': 'nav'
      };
      
      for (const [pattern, section] of Object.entries(classMap)) {
        if (className.includes(pattern)) {
          semanticSection = section;
          break;
        }
      }
      if (semanticSection) break;
    }
    
    currentEl = currentEl.parentElement;
  }
  
  return semanticSection;
}

/**
 * Detects CAPTCHA elements using comprehensive patterns
 */
function detectCaptcha(element, className, id, ariaLabel, textualContent, elementType) {
  return (className && className.includes("recaptcha")) || 
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
}

/**
 * Detects clickable elements using comprehensive criteria
 */
function detectClickable(element, elementType, style, className, ariaLabel, isCaptchaElement) {
  const roleAttr = element.getAttribute("role") || "";
  const tabIndexAttr = element.getAttribute("tabindex");
  const tabIndex = tabIndexAttr != null ? parseInt(tabIndexAttr, 10) : NaN;
  
  return element.tagName === "INPUT" ||
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
}

/**
 * Determines whether an element should be included based on various criteria
 */
function determineInclusion(area, isInteractive, isClickable, isCaptchaElement, 
                           ariaLabel, elementType, includeOutOfViewport, includeAsContent) {
  const minInteractionSize = 10; // Minimum 10x10px for interaction
  const isLargeEnough = area >= (minInteractionSize * minInteractionSize);
  const isIconSized = area >= 100 && area <= 2500; // 10x10 to 50x50px (likely icons)
  const hasSpecialSignificance = isCaptchaElement || 
                               (ariaLabel && ariaLabel.trim().length > 0) ||
                               elementType === 'button' || elementType === 'a';

  // For interactive elements, use original logic
  // For content elements, include if they have significant content or are structural
  return isInteractive ? 
    (isClickable && (isLargeEnough || isIconSized || hasSpecialSignificance || includeOutOfViewport)) :
    includeAsContent; // Content elements already filtered above
}

/**
 * Creates the final element item object with all metadata
 */
function createElementItem(element, shouldInclude, area, rects, displayText, elementType,
                          ariaLabel, isCaptchaElement, className, id, hierarchicalInfo, frameContext,
                          linkHref, inputMetadata, formContext, isInteractive, elementRole,
                          contentType, headingLevel, wordCount, truncated, fullTextAvailable, 
                          parentId, childIds, isContainer, semanticSection, isFocused) {
  return {
    element: element,
    include: shouldInclude,
    area,
    rects,
    text: displayText,
    type: elementType,
    ariaLabel: ariaLabel,
    isCaptcha: isCaptchaElement,
    className: className,
    elementId: id,
    hierarchy: hierarchicalInfo,
    frameContext: frameContext,
    globalIndex: globalElementIndex++,
    href: linkHref,
    inputMetadata: inputMetadata,
    formContext: formContext,
    // New unified representation fields
    isInteractive: isInteractive,
    elementRole: elementRole,
    contentType: contentType,
    headingLevel: headingLevel,
    wordCount: wordCount,
    truncated: truncated,
    fullTextAvailable: fullTextAvailable,
    parentId: parentId,
    childIds: childIds,
    labelFor: element.getAttribute('for') ? null : null, // Will need to resolve to globalIndex later
    describedBy: element.getAttribute('aria-describedby') ? null : null, // Will need to resolve later
    isContainer: isContainer,
    semanticSection: semanticSection,
    focused: isFocused
  };
}

/**
 * Creates error element item for elements that failed processing
 */
function createErrorElementItem(element, frameContext) {
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
    href: "",
    inputMetadata: {},
    formContext: {},
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
    semanticSection: null,
    focused: false
  };
}