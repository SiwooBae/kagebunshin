/**
 * Main Page Annotation System for KageBunshin
 * 
 * This module provides the main entry points for the page annotation system:
 * - markPage(): Main function to annotate interactive and content elements
 * - Enhanced element processing with text merging capabilities
 * - SVG overlay rendering with visual labels
 * - Comprehensive result formatting for Python integration
 */

/**
 * Main function to mark and annotate all interactive and content elements on a page
 * This is the primary entry point called by the Python system
 * 
 * @param {Object} options - Configuration options for page marking
 * @param {boolean} options.includeOutOfViewport - Include elements outside viewport
 * @param {number} options.maxOutOfViewportDistance - Maximum distance for out-of-viewport elements
 * @param {boolean} options.enableTextMerging - Enable text fragment merging (experimental)
 * @param {number} options.textMergingGap - Gap threshold for text merging
 * @param {number} options.textMergingLength - Maximum length for merged text
 * @param {number} options.textMergingConfidence - Confidence threshold for merging
 * @returns {Object} Result object with coordinates, viewport categories, and frame stats
 */
function markPage(options = {}) {
  try {
    console.log("DEBUG: Starting enhanced markPage function");
    const { includeOutOfViewport = true, maxOutOfViewportDistance = 2000 } = options;
    lastMarkPageOptions = options;
    
    // Clean up any existing annotations
    unmarkPage();
    console.log("DEBUG: Unmark page completed");

    // Clear any existing data-ai-label attributes for fresh labeling
    clearExistingLabels();

    let allItems = [];
    const rootNodes = [document];
    
    // Collect all shadow roots recursively
    collectShadowRoots(document, rootNodes);
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

    // Get viewport dimensions
    var vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    var vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);

    // Process and categorize items by viewport position
    const viewportCategories = categorizeByViewport(allItems, vw, vh, includeOutOfViewport, maxOutOfViewportDistance);

    // Filter out contained elements and empty rects
    let items = allItems.filter(item => item.rects.length > 0);
    items = items.filter((x) => !items.some((y) => x.element.contains(y.element) && !(x == y)));

    // Apply text fragment merging if enabled
    if (includeOutOfViewport && options.enableTextMerging === true) {
        items = applyTextMerging(items, options);
    }

    // Create visual annotations
    createVisualAnnotations(items);

    // Build and return result
    const result = buildResult(items, viewportCategories);
    
    console.log("DEBUG: Created enhanced result with", result.coordinates.length, "coordinates");
    console.log("DEBUG: Viewport categories:", Object.keys(viewportCategories).map(key => 
        `${key}: ${viewportCategories[key].length}`).join(', '));
    console.log("DEBUG: Frame stats:", result.frameStats);
    
    // Attach auto-update listeners for dynamic pages
    attachUpdateListeners();
    return result;
  
  } catch (error) {
    console.error("DEBUG: Error in markPage:", error);
    console.error("DEBUG: Error stack:", error.stack);
    throw error;
  }
}

/**
 * Helper Functions for markPage
 */

/**
 * Clears all existing data-ai-label attributes from the document and accessible iframes
 */
function clearExistingLabels() {
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

    // Clear labels in current document and shadow roots
    clearLabelsInRoot(document);

    // Clear labels in accessible iframes
    const iframes = document.querySelectorAll('iframe');
    iframes.forEach((iframe) => {
      try {
        const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
        clearLabelsInRoot(doc);
      } catch (e) {
        // Cross-origin iframes will fail - ignore
      }
    });
  } catch (e) {
    // Best-effort cleanup - ignore errors
  }
}

/**
 * Recursively collects all shadow roots in the document
 */
function collectShadowRoots(root, rootNodes) {
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
  })(root);
}

/**
 * Categorizes elements by their viewport position
 */
function categorizeByViewport(allItems, vw, vh, includeOutOfViewport, maxOutOfViewportDistance) {
  const viewportCategories = {
      'in-viewport': [],
      'above-viewport': [],
      'below-viewport': [],
      'left-of-viewport': [],
      'right-of-viewport': []
  };

  allItems.forEach(item => {
      // Process rectangles with viewport clipping and distance calculation
      item.rects = item.rects.map(bb => {
          if (bb.viewportPosition === 'in-viewport') {
              // Clip in-viewport elements to viewport bounds
              const rect = {
                  left: Math.max(0, bb.left),
                  top: Math.max(0, bb.top),
                  right: Math.min(vw, bb.right),
                  bottom: Math.min(vh, bb.bottom),
                  viewportPosition: bb.viewportPosition
              };
              return { ...rect, width: rect.right - rect.left, height: rect.bottom - rect.top };
          } else {
              // Calculate distance from viewport for out-of-viewport elements
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

  return viewportCategories;
}

/**
 * Applies text fragment merging using the TextFragmentMerger
 */
function applyTextMerging(items, options) {
  console.log(`DEBUG: Starting text merging on ${items.length} items`);
  
  try {
      // Check if TextFragmentMerger is available
      if (typeof TextFragmentMerger === 'undefined' || typeof TextFragmentMerger !== 'function') {
          console.warn('DEBUG: TextFragmentMerger class is not available, skipping text merging');
          return items;
      }

      const merger = new TextFragmentMerger({
          maxGap: options.textMergingGap || 5,
          maxMergeLength: options.textMergingLength || 100,
          minConfidence: options.textMergingConfidence || 0.7,
          respectAriaLabels: options.textMergingRespectAria !== false,
          detectIconFonts: options.textMergingDetectIcons !== false,
          mergeAcrossLines: options.textMergingAcrossLines || false
      });
      
      const mergedGroups = merger.mergeAdjacentElements(
          items.map(item => item.element),
          { enableTextMerging: true }
      );
      
      console.log(`DEBUG: Merged ${items.length} items into ${mergedGroups.length} groups`);
      
      // Convert merged groups back to item format
      const mergedItems = mergedGroups.map((group, mergedIndex) => {
          const originalItem = items.find(item => item.element === group.representativeElement);
          if (!originalItem) {
              console.warn('DEBUG: Could not find original item for merged group', group);
              return null;
          }
          
          return {
              ...originalItem,
              element: group.representativeElement,
              text: group.text,
              rects: group.boundingBox ? [{
                  left: group.boundingBox.left,
                  top: group.boundingBox.top,
                  right: group.boundingBox.right,
                  bottom: group.boundingBox.bottom,
                  width: group.boundingBox.width,
                  height: group.boundingBox.height,
                  viewportPosition: 'in-viewport'
              }] : originalItem.rects,
              // Merged-specific properties
              isMergedText: group.isMerged,
              mergedElementCount: group.originalCount,
              mergedElements: group.elements,
              mergingConfidence: group.confidence,
              globalIndex: originalItem.globalIndex
          };
      }).filter(item => item !== null);
      
      console.log(`DEBUG: Final merged items count: ${mergedItems.length}`);
      return mergedItems;
      
  } catch (mergeError) {
      console.error('DEBUG: Error during text merging, falling back to original items:', mergeError);
      console.error('DEBUG: Error details:', mergeError.message);
      return items;
  }
}

/**
 * Creates visual SVG annotations for elements
 */
function createVisualAnnotations(items) {
  const labelPositions = [];
  
  function isOverlapping(rect1, rect2) {
      return !(rect1.right < rect2.left || rect1.left > rect2.right || 
               rect1.bottom < rect2.top || rect1.top > rect2.bottom);
  }

  // Create SVG overlay for visual annotations
  ensureOverlay();

  items.forEach(function (item, index) {
    item.element.setAttribute('data-ai-label', index);
    const color = getColorForItem(item);

    item.rects.forEach((bbox) => {
      // Only render in-viewport boxes visually
      if (bbox.viewportPosition !== 'in-viewport') return;

      // Create rectangle overlay with focus styling
      const rectEl = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rectEl.setAttribute("x", String(bbox.left));
      rectEl.setAttribute("y", String(bbox.top));
      rectEl.setAttribute("width", String(bbox.width));
      rectEl.setAttribute("height", String(bbox.height));
      rectEl.setAttribute("fill", color + (item.focused ? "60" : "40")); // Stronger fill for focused
      rectEl.setAttribute("stroke", item.focused ? "#FFD700" : color); // Gold stroke for focused
      rectEl.setAttribute("stroke-width", item.focused ? "3" : "2"); // Thicker stroke for focused

      // Create label with background, add focus indicator if needed
      const labelText = item.focused ? `[F] ${index}` : String(index);
      const approxCharW = 7;
      const labelHeight = 18;
      const labelWidth = (labelText.length * approxCharW) + 8;

      // Find optimal label position to avoid overlaps
      const potentialPositions = [
        { dx: 0, dy: -labelHeight }, // top-left
        { dx: bbox.width - labelWidth, dy: -labelHeight }, // top-right
        { dx: 0, dy: bbox.height }, // bottom-left
        { dx: bbox.width - labelWidth, dy: bbox.height } // bottom-right
      ];

      let best = potentialPositions[0];
      for (const pos of potentialPositions) {
        const l = bbox.left + pos.dx;
        const t = bbox.top + pos.dy;
        const candidate = { left: l, top: t, right: l + labelWidth, bottom: t + labelHeight };
        if (!labelPositions.some(existing => isOverlapping(candidate, existing))) {
          best = pos; 
          break;
        }
      }
      
      const labelLeft = Math.max(0, Math.min(bbox.left + best.dx, overlaySvg.viewBox.baseVal.width - labelWidth));
      const labelTop = Math.max(0, Math.min(bbox.top + best.dy, overlaySvg.viewBox.baseVal.height - labelHeight));

      labelPositions.push({ left: labelLeft, top: labelTop, right: labelLeft + labelWidth, bottom: labelTop + labelHeight });

      // Create label background
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

      // Create label text
      const textEl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      textEl.setAttribute("x", String(labelLeft + 4));
      textEl.setAttribute("y", String(labelTop + labelHeight - 5));
      textEl.setAttribute("fill", "#ffffff");
      textEl.setAttribute("font-size", "12");
      textEl.setAttribute("font-family", "system-ui, -apple-system, Segoe UI, Roboto, sans-serif");
      textEl.setAttribute("font-weight", "bold");
      textEl.textContent = labelText;

      // Add tooltip for debugging
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      const shortText = (item.text || '').slice(0, 80);
      const focusInfo = item.focused ? '\nFOCUSED: YES' : '';
      title.textContent = `type: ${item.type} role: ${(item.hierarchy && item.hierarchy.semanticRole) || ''}\naria: ${item.ariaLabel || ''}\ntext: ${shortText}${item.text && item.text.length > 80 ? '…' : ''}\nframe: ${item.frameContext || 'main'}${focusInfo}`;
      rectEl.appendChild(title);

      // Add all elements to overlay
      overlayLayer.appendChild(rectEl);
      overlayLayer.appendChild(labelBg);
      overlayLayer.appendChild(textEl);
    });
  });
}

/**
 * Builds the final result object for Python integration
 */
function buildResult(items, viewportCategories) {
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
          // Choose representative rect with largest area
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
              href: item.href || "",
              inputMetadata: item.inputMetadata || {},
              formContext: item.formContext || {},
              // Enhanced properties
              hierarchy: item.hierarchy,
              frameContext: item.frameContext || "main",
              viewportPosition: viewportPosition || 'in-viewport',
              distanceFromViewport: distanceFromViewport || 0,
              globalIndex: item.globalIndex,
              boundingBox: { left, top, width, height },
              // Unified representation fields
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
              semanticSection: item.semanticSection,
              focused: item.focused
          });
      }
  });
  
  return result;
}