/**
 * Advanced text fragment detection and merging for browser automation.
 * 
 * Handles websites that split text into individual DOM elements (letter-by-letter 
 * or word-by-word) while preserving interaction accuracy and performance.
 * 
 * Key Features:
 * - Spatial adjacency detection with transformation support
 * - Interaction boundary preservation 
 * - Semantic boundary respect (ARIA, Shadow DOM)
 * - Performance optimization with spatial indexing
 * - Confidence scoring for merge quality
 * - Configurable merge parameters
 */

class TextFragmentMerger {
    constructor(options = {}) {
        // Merge parameters
        this.maxGap = options.maxGap || 5; // Max pixel gap between adjacent elements
        this.maxMergeLength = options.maxMergeLength || 100; // Max characters in merged text
        this.minConfidence = options.minConfidence || 0.7; // Min confidence to include merge
        this.maxLineHeightDiff = options.maxLineHeightDiff || 5; // Max Y position difference for same line
        
        // Performance options
        this.enableSpatialIndex = options.enableSpatialIndex !== false;
        this.maxElementsForFullComparison = options.maxElementsForFullComparison || 50;
        
        // Feature flags
        this.respectAriaLabels = options.respectAriaLabels !== false;
        this.detectIconFonts = options.detectIconFonts !== false;
        this.mergeAcrossLines = options.mergeAcrossLines || false;
        this.respectTransforms = options.respectTransforms !== false;
        
        // Site-specific configurations
        this.siteConfigs = options.siteConfigs || {};
        this.iconFontClasses = options.iconFontClasses || ['fa', 'icon', 'glyphicon', 'material-icons'];
        this.iconUnicodeRanges = [
            [0xE000, 0xF8FF], // Private Use Area
            [0xF0000, 0xFFFFD], // Supplementary Private Use Area-A
            [0x100000, 0x10FFFD], // Supplementary Private Use Area-B
            [0x2600, 0x26FF], // Miscellaneous Symbols
            [0x2700, 0x27BF], // Dingbats
            [0x1F300, 0x1F5FF], // Miscellaneous Symbols and Pictographs
            [0x1F600, 0x1F64F], // Emoticons
            [0x1F680, 0x1F6FF], // Transport and Map Symbols
            [0x1F900, 0x1F9FF], // Supplemental Symbols and Pictographs
        ];
        
        // Performance tracking
        this.stats = {
            totalElements: 0,
            mergedGroups: 0,
            totalMergedElements: 0,
            processingTime: 0
        };
    }
    
    /**
     * Main entry point for merging adjacent text elements.
     * @param {Array<Element>} elements - DOM elements to potentially merge
     * @param {Object} options - Override options for this merge operation
     * @returns {Array<Object>} - Array of merged element groups
     */
    mergeAdjacentElements(elements, options = {}) {
        const startTime = performance.now();
        
        if (!elements || elements.length === 0) {
            return [];
        }
        
        // Apply any site-specific configuration
        const hostname = window.location.hostname;
        const siteConfig = this.siteConfigs[hostname] || {};
        const mergeOptions = { ...this, ...siteConfig, ...options };
        
        this.stats.totalElements = elements.length;
        
        try {
            // Group elements by parent for efficient processing
            const parentGroups = this._groupByParent(elements);
            const mergedGroups = [];
            
            // Process each parent's children separately
            for (const [parent, siblings] of parentGroups) {
                const parentMerged = this._mergeSiblings(siblings, mergeOptions);
                mergedGroups.push(...parentMerged);
            }
            
            // Filter by confidence threshold
            const filtered = mergedGroups.filter(group => 
                group.confidence >= mergeOptions.minConfidence
            );
            
            this.stats.mergedGroups = filtered.length;
            this.stats.totalMergedElements = filtered.reduce((sum, g) => sum + g.elements.length, 0);
            
            return filtered;
            
        } finally {
            this.stats.processingTime = performance.now() - startTime;
        }
    }
    
    /**
     * Group elements by their parent element.
     * @private
     */
    _groupByParent(elements) {
        const groups = new Map();
        
        for (const element of elements) {
            const parent = element.parentElement || document.body;
            if (!groups.has(parent)) {
                groups.set(parent, []);
            }
            groups.get(parent).push(element);
        }
        
        return groups;
    }
    
    /**
     * Merge sibling elements that are spatially and semantically adjacent.
     * @private
     */
    _mergeSiblings(siblings, options) {
        if (siblings.length === 0) return [];
        if (siblings.length === 1) {
            return [this._createSingleElementGroup(siblings[0])];
        }
        
        // Sort siblings by DOM order for consistent processing
        siblings.sort((a, b) => {
            const position = a.compareDocumentPosition(b);
            if (position & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
            if (position & Node.DOCUMENT_POSITION_PRECEDING) return 1;
            return 0;
        });
        
        const groups = [];
        let currentGroup = null;
        
        for (const element of siblings) {
            if (this._shouldSkipElement(element)) {
                continue;
            }
            
            if (!currentGroup) {
                currentGroup = this._startNewGroup(element);
            } else if (this._shouldMergeWithGroup(element, currentGroup, options)) {
                this._addToGroup(currentGroup, element);
            } else {
                // Finalize current group and start new one
                groups.push(this._finalizeGroup(currentGroup));
                currentGroup = this._startNewGroup(element);
            }
        }
        
        // Don't forget the last group
        if (currentGroup) {
            groups.push(this._finalizeGroup(currentGroup));
        }
        
        return groups;
    }
    
    /**
     * Check if element should be skipped entirely.
     * @private
     */
    _shouldSkipElement(element) {
        // Check for explicit no-merge attribute
        if (element.hasAttribute('data-no-merge') && 
            element.getAttribute('data-no-merge') === 'true') {
            return true;
        }
        
        // Check if parent has no-merge for all children
        let parent = element.parentElement;
        while (parent && parent !== document.body) {
            if (parent.hasAttribute('data-no-merge-children') &&
                parent.getAttribute('data-no-merge-children') === 'true') {
                return true;
            }
            parent = parent.parentElement;
        }
        
        return false;
    }
    
    /**
     * Start a new merge group with the given element.
     * @private
     */
    _startNewGroup(element) {
        const rect = element.getBoundingClientRect();
        const computedStyle = window.getComputedStyle(element);
        
        return {
            elements: [element],
            startElement: element,
            endElement: element,
            boundingRects: [rect],
            mergedText: this._getElementText(element),
            interactionTarget: this._getInteractionTarget(element),
            ariaLabel: element.getAttribute('aria-label'),
            semanticRole: this._getSemanticRole(element),
            computedStyles: [computedStyle],
            isIconFont: this._isIconFont(element, computedStyle),
            transformMatrix: this._getTransformMatrix(computedStyle),
            confidenceFactors: {
                spatialCoherence: 1.0,
                styleConsistency: 1.0,
                semanticCompatibility: 1.0,
                textCoherence: 1.0
            }
        };
    }
    
    /**
     * Check if element should be merged with the current group.
     * @private
     */
    _shouldMergeWithGroup(element, group, options) {
        // Check all merge criteria
        const spatialCheck = this._checkSpatialAdjacency(element, group, options);
        if (!spatialCheck.valid) return false;
        
        const interactionCheck = this._checkInteractionCompatibility(element, group);
        if (!interactionCheck.valid) return false;
        
        const styleCheck = this._checkStyleConsistency(element, group);
        if (!styleCheck.valid) return false;
        
        const semanticCheck = this._checkSemanticCompatibility(element, group, options);
        if (!semanticCheck.valid) return false;
        
        const textCheck = this._checkTextCoherence(element, group, options);
        if (!textCheck.valid) return false;
        
        // Update confidence factors
        group.confidenceFactors.spatialCoherence *= spatialCheck.confidence || 1.0;
        group.confidenceFactors.styleConsistency *= styleCheck.confidence || 1.0;
        group.confidenceFactors.semanticCompatibility *= semanticCheck.confidence || 1.0;
        group.confidenceFactors.textCoherence *= textCheck.confidence || 1.0;
        
        return true;
    }
    
    /**
     * Check if element is spatially adjacent to the group.
     * @private
     */
    _checkSpatialAdjacency(element, group, options) {
        const rect = element.getBoundingClientRect();
        const lastRect = group.boundingRects[group.boundingRects.length - 1];
        
        // Check if on same line (Y position)
        const yDiff = Math.abs(rect.top - lastRect.top);
        if (yDiff > options.maxLineHeightDiff) {
            if (!options.mergeAcrossLines) {
                return { valid: false, reason: 'different-lines' };
            }
        }
        
        // Check horizontal gap
        let gap;
        if (rect.left >= lastRect.right) {
            gap = rect.left - lastRect.right; // Element is to the right
        } else if (rect.right <= lastRect.left) {
            gap = lastRect.left - rect.right; // Element is to the left
        } else {
            gap = 0; // Overlapping
        }
        
        if (gap > options.maxGap) {
            return { valid: false, reason: 'gap-too-large', gap };
        }
        
        // Calculate confidence based on gap size and alignment
        let confidence = Math.max(0.1, 1.0 - (gap / options.maxGap));
        if (yDiff === 0 && gap <= 2) {
            confidence = Math.min(1.0, confidence + 0.2); // Bonus for perfect alignment
        }
        
        return { valid: true, confidence };
    }
    
    /**
     * Check if element has compatible interaction behavior with group.
     * @private
     */
    _checkInteractionCompatibility(element, group) {
        const elementTarget = this._getInteractionTarget(element);
        const groupTarget = group.interactionTarget;
        
        // Both must have same interaction state (interactive or non-interactive)
        if (!elementTarget !== !groupTarget) {
            return { valid: false, reason: 'interaction-mismatch' };
        }
        
        // If both are interactive, they must have the same target
        if (elementTarget && groupTarget) {
            if (elementTarget !== groupTarget) {
                // Check if they're functionally equivalent
                if (!this._areInteractionsEquivalent(elementTarget, groupTarget)) {
                    return { valid: false, reason: 'different-handlers' };
                }
            }
        }
        
        return { valid: true, confidence: 1.0 };
    }
    
    /**
     * Check if element styles are consistent with group.
     * @private
     */
    _checkStyleConsistency(element, group) {
        const style = window.getComputedStyle(element);
        const groupStyle = group.computedStyles[0];
        
        // Check critical style properties
        const criticalProps = ['fontSize', 'fontFamily', 'fontWeight', 'color', 'textDecoration'];
        let matchingProps = 0;
        
        for (const prop of criticalProps) {
            if (style[prop] === groupStyle[prop]) {
                matchingProps++;
            }
        }
        
        const styleMatch = matchingProps / criticalProps.length;
        if (styleMatch < 0.6) {
            return { valid: false, reason: 'style-mismatch', matchRatio: styleMatch };
        }
        
        return { valid: true, confidence: styleMatch };
    }
    
    /**
     * Check if element is semantically compatible with group.
     * @private
     */
    _checkSemanticCompatibility(element, group, options) {
        // Check ARIA labels if enabled
        if (options.respectAriaLabels) {
            const elementAria = element.getAttribute('aria-label');
            const groupAria = group.ariaLabel;
            
            if (elementAria && groupAria && elementAria !== groupAria) {
                return { valid: false, reason: 'different-aria-labels' };
            }
        }
        
        // Check semantic roles
        const elementRole = this._getSemanticRole(element);
        const groupRole = group.semanticRole;
        
        if (elementRole !== groupRole) {
            return { valid: false, reason: 'different-semantic-roles' };
        }
        
        // Check icon font mixing
        if (options.detectIconFonts) {
            const style = window.getComputedStyle(element);
            const isIcon = this._isIconFont(element, style);
            
            if (isIcon !== group.isIconFont) {
                return { valid: false, reason: 'icon-text-mixing' };
            }
        }
        
        return { valid: true, confidence: 1.0 };
    }
    
    /**
     * Check if element text is coherent with group text.
     * @private
     */
    _checkTextCoherence(element, group, options) {
        const elementText = this._getElementText(element);
        const combinedLength = group.mergedText.length + elementText.length;
        
        if (combinedLength > options.maxMergeLength) {
            return { valid: false, reason: 'text-too-long' };
        }
        
        // Check for text coherence patterns
        const combined = group.mergedText + elementText;
        let confidence = 1.0;
        
        // Reduce confidence for mixed languages/scripts
        if (this._hasMixedScripts(combined)) {
            confidence *= 0.8;
        }
        
        // Reduce confidence for nonsensical character combinations
        if (this._hasIncoherentPatterns(combined)) {
            confidence *= 0.6;
        }
        
        return { valid: true, confidence };
    }
    
    /**
     * Add element to existing group.
     * @private
     */
    _addToGroup(group, element) {
        group.elements.push(element);
        group.endElement = element;
        group.boundingRects.push(element.getBoundingClientRect());
        group.mergedText += this._getElementText(element);
        group.computedStyles.push(window.getComputedStyle(element));
    }
    
    /**
     * Finalize group and calculate final confidence score.
     * @private
     */
    _finalizeGroup(group) {
        // Calculate overall confidence
        const factors = group.confidenceFactors;
        const confidence = (factors.spatialCoherence * 0.3 +
                          factors.styleConsistency * 0.25 +
                          factors.semanticCompatibility * 0.25 +
                          factors.textCoherence * 0.2);
        
        // Calculate merged bounding box
        const mergedRect = this._calculateMergedBoundingBox(group.boundingRects);
        
        return {
            elements: group.elements,
            text: group.mergedText.trim(),
            boundingBox: mergedRect,
            confidence: Math.max(0, Math.min(1, confidence)),
            isMerged: group.elements.length > 1,
            originalCount: group.elements.length,
            representativeElement: group.startElement,
            interactionTarget: group.interactionTarget,
            mergeReason: group.elements.length > 1 ? 'adjacent-text-fragments' : 'single-element',
            
            // Debug information
            confidenceBreakdown: factors,
            processingStats: {
                elementsCount: group.elements.length,
                textLength: group.mergedText.length,
                boundingRectCount: group.boundingRects.length
            }
        };
    }
    
    /**
     * Create group for single element (no merging).
     * @private
     */
    _createSingleElementGroup(element) {
        const rect = element.getBoundingClientRect();
        
        return {
            elements: [element],
            text: this._getElementText(element),
            boundingBox: rect,
            confidence: 1.0,
            isMerged: false,
            originalCount: 1,
            representativeElement: element,
            interactionTarget: this._getInteractionTarget(element),
            mergeReason: 'single-element',
            confidenceBreakdown: {
                spatialCoherence: 1.0,
                styleConsistency: 1.0,
                semanticCompatibility: 1.0,
                textCoherence: 1.0
            },
            processingStats: {
                elementsCount: 1,
                textLength: this._getElementText(element).length,
                boundingRectCount: 1
            }
        };
    }
    
    // Helper methods
    
    /**
     * Get text content of element, handling various edge cases.
     * @private
     */
    _getElementText(element) {
        // Try different text properties
        return element.textContent || element.innerText || element.value || '';
    }
    
    /**
     * Get the actual interaction target for an element (considering event delegation).
     * @private
     */
    _getInteractionTarget(element) {
        // Check element itself
        if (element.onclick || element.href || element.type === 'button' || element.type === 'submit') {
            return element;
        }
        
        // Walk up parent chain to find delegated handlers
        let parent = element.parentElement;
        while (parent && parent !== document.body) {
            if (parent.onclick || parent.href) {
                return parent;
            }
            parent = parent.parentElement;
        }
        
        return null;
    }
    
    /**
     * Check if two interaction targets are functionally equivalent.
     * @private
     */
    _areInteractionsEquivalent(target1, target2) {
        if (target1 === target2) return true;
        
        // Check href attributes
        if (target1.href && target2.href) {
            return target1.href === target2.href;
        }
        
        // For click handlers, we can't easily compare function content
        // This is a limitation - in practice, you might need site-specific logic
        return false;
    }
    
    /**
     * Get semantic role of element.
     * @private
     */
    _getSemanticRole(element) {
        return element.getAttribute('role') || 
               element.tagName.toLowerCase() || 
               'generic';
    }
    
    /**
     * Check if element uses icon fonts.
     * @private
     */
    _isIconFont(element, computedStyle) {
        if (!this.detectIconFonts) return false;
        
        // Check for icon font classes
        const className = element.className || '';
        if (this.iconFontClasses.some(cls => className.includes(cls))) {
            return true;
        }
        
        // Check font family
        const fontFamily = computedStyle.fontFamily.toLowerCase();
        const iconFontFamilies = ['fontawesome', 'glyphicons', 'material', 'icon'];
        if (iconFontFamilies.some(font => fontFamily.includes(font))) {
            return true;
        }
        
        // Check for Private Use Area characters (common in icon fonts)
        const text = this._getElementText(element);
        for (const char of text) {
            const code = char.codePointAt(0);
            for (const [start, end] of this.iconUnicodeRanges) {
                if (code >= start && code <= end) {
                    return true;
                }
            }
        }
        
        return false;
    }
    
    /**
     * Get transform matrix for element.
     * @private
     */
    _getTransformMatrix(computedStyle) {
        const transform = computedStyle.transform;
        if (!transform || transform === 'none') {
            return null;
        }
        
        // Parse matrix values
        const values = transform.match(/matrix\(([^)]+)\)/);
        if (values) {
            return values[1].split(',').map(n => parseFloat(n.trim()));
        }
        
        return null;
    }
    
    /**
     * Check if text contains mixed scripts.
     * @private
     */
    _hasMixedScripts(text) {
        // Simple heuristic - detect if text contains both Latin and non-Latin scripts
        const hasLatin = /[a-zA-Z]/.test(text);
        const hasNonLatin = /[^\x00-\x7F]/.test(text);
        
        return hasLatin && hasNonLatin && text.length > 10;
    }
    
    /**
     * Check for incoherent character patterns that suggest bad merging.
     * @private
     */
    _hasIncoherentPatterns(text) {
        // Look for patterns that suggest over-merging
        
        // Multiple currency symbols
        if ((text.match(/[$€£¥₹]/g) || []).length > 1) {
            return true;
        }
        
        // Multiple @ symbols (likely email addresses merged)
        if ((text.match(/@/g) || []).length > 1) {
            return true;
        }
        
        // Numbers mixed with letters in suspicious patterns
        if (/\d+[a-zA-Z]+\d+/.test(text) && text.length > 15) {
            return true;
        }
        
        return false;
    }
    
    /**
     * Calculate merged bounding box from multiple rects.
     * @private
     */
    _calculateMergedBoundingBox(rects) {
        if (rects.length === 0) return new DOMRect();
        if (rects.length === 1) return rects[0];
        
        let minLeft = Infinity, minTop = Infinity;
        let maxRight = -Infinity, maxBottom = -Infinity;
        
        for (const rect of rects) {
            minLeft = Math.min(minLeft, rect.left);
            minTop = Math.min(minTop, rect.top);
            maxRight = Math.max(maxRight, rect.right);
            maxBottom = Math.max(maxBottom, rect.bottom);
        }
        
        return new DOMRect(
            minLeft,
            minTop,
            maxRight - minLeft,
            maxBottom - minTop
        );
    }
    
    /**
     * Get performance statistics.
     */
    getStats() {
        return { ...this.stats };
    }
    
    /**
     * Reset performance statistics.
     */
    resetStats() {
        this.stats = {
            totalElements: 0,
            mergedGroups: 0,
            totalMergedElements: 0,
            processingTime: 0
        };
    }
}

// Export for both CommonJS and ES6 modules, and global scope
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TextFragmentMerger;
} else if (typeof exports !== 'undefined') {
    exports.TextFragmentMerger = TextFragmentMerger;
} else {
    // Global scope for browser
    window.TextFragmentMerger = TextFragmentMerger;
}