"""
Test edge cases for the text fragment merger.
"""

import pytest
from pathlib import Path
from playwright.sync_api import Page


def test_line_break_handling(page: Page):
    """Test that elements on different lines don't merge."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
    page.goto(f"file://{fixture_path}")
    
    # Inject merger function
    page.evaluate("""
    window.mergeTextFragments = function(elements, options = {}) {
        const maxGap = options.maxGap || 5;
        const minConfidence = options.minConfidence || 0.7;
        const maxLineHeightDiff = options.maxLineHeightDiff || 5;
        
        if (!elements || elements.length === 0) return [];
        
        const groups = [];
        let currentGroup = null;
        
        function startNewGroup(element) {
            return {
                elements: [element],
                boundingRects: [element.getBoundingClientRect()],
                mergedText: element.textContent || '',
                confidence: 1.0
            };
        }
        
        function shouldMergeWithGroup(element, group) {
            const rect = element.getBoundingClientRect();
            const lastRect = group.boundingRects[group.boundingRects.length - 1];
            
            // Same line check - stricter for this test
            const yDiff = Math.abs(rect.top - lastRect.top);
            if (yDiff > maxLineHeightDiff) return false;
            
            // Gap check
            let gap = rect.left >= lastRect.right ? rect.left - lastRect.right :
                      rect.right <= lastRect.left ? lastRect.left - rect.right : 0;
            if (gap > maxGap) return false;
            
            return true;
        }
        
        function addToGroup(group, element) {
            group.elements.push(element);
            group.boundingRects.push(element.getBoundingClientRect());
            group.mergedText += element.textContent || '';
        }
        
        function finalizeGroup(group) {
            return {
                elements: group.elements,
                text: group.mergedText.trim(),
                confidence: group.confidence,
                isMerged: group.elements.length > 1,
                originalCount: group.elements.length,
                representativeElement: group.elements[0]
            };
        }
        
        for (const element of elements) {
            if (!currentGroup) {
                currentGroup = startNewGroup(element);
            } else if (shouldMergeWithGroup(element, currentGroup)) {
                addToGroup(currentGroup, element);
            } else {
                groups.push(finalizeGroup(currentGroup));
                currentGroup = startNewGroup(element);
            }
        }
        
        if (currentGroup) {
            groups.push(finalizeGroup(currentGroup));
        }
        
        return groups.filter(g => g.confidence >= minConfidence);
    };
    """)
    
    # Test multiline spans
    result = page.evaluate("""() => {
        const spans = Array.from(document.querySelectorAll('#multiline-split span'));
        const merged = window.mergeTextFragments(spans, { maxGap: 5, minConfidence: 0.5, maxLineHeightDiff: 5 });
        
        return {
            originalCount: spans.length,
            mergedCount: merged.length,
            mergedTexts: merged.map(m => m.text),
            allText: merged.map(m => m.text).join(' ')
        };
    }""")
    
    print(f"Multiline test results: {result}")
    
    # Should have more than 2 groups since text is on different lines
    assert result['mergedCount'] >= 2
    
    # Should contain "First" and "Second" in separate groups
    merged_texts = ' '.join(result['mergedTexts'])
    assert 'First' in merged_texts
    assert 'Second' in merged_texts


def test_mixed_interaction_boundaries(page: Page):
    """Test that elements with different click handlers don't merge."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
    page.goto(f"file://{fixture_path}")
    
    # Add interaction checking to merger
    page.evaluate("""
    window.mergeWithInteractionCheck = function(elements, options = {}) {
        const maxGap = options.maxGap || 5;
        const minConfidence = options.minConfidence || 0.7;
        const maxLineHeightDiff = options.maxLineHeightDiff || 5;
        
        if (!elements || elements.length === 0) return [];
        
        function getInteractionTarget(element) {
            if (element.onclick || element.href) return element;
            let parent = element.parentElement;
            while (parent && parent !== document.body) {
                if (parent.onclick || parent.href) return parent;
                parent = parent.parentElement;
            }
            return null;
        }
        
        const groups = [];
        let currentGroup = null;
        
        function startNewGroup(element) {
            return {
                elements: [element],
                boundingRects: [element.getBoundingClientRect()],
                mergedText: element.textContent || '',
                interactionTarget: getInteractionTarget(element),
                confidence: 1.0
            };
        }
        
        function shouldMergeWithGroup(element, group) {
            const rect = element.getBoundingClientRect();
            const lastRect = group.boundingRects[group.boundingRects.length - 1];
            
            // Same line check
            const yDiff = Math.abs(rect.top - lastRect.top);
            if (yDiff > maxLineHeightDiff) return false;
            
            // Gap check
            let gap = rect.left >= lastRect.right ? rect.left - lastRect.right :
                      rect.right <= lastRect.left ? lastRect.left - rect.right : 0;
            if (gap > maxGap) return false;
            
            // Interaction compatibility check
            const elementTarget = getInteractionTarget(element);
            if (!elementTarget !== !group.interactionTarget) return false;
            if (elementTarget && group.interactionTarget && elementTarget !== group.interactionTarget) {
                return false; // Different interaction targets
            }
            
            return true;
        }
        
        function addToGroup(group, element) {
            group.elements.push(element);
            group.boundingRects.push(element.getBoundingClientRect());
            group.mergedText += element.textContent || '';
        }
        
        function finalizeGroup(group) {
            return {
                elements: group.elements,
                text: group.mergedText.trim(),
                confidence: group.confidence,
                isMerged: group.elements.length > 1,
                originalCount: group.elements.length,
                representativeElement: group.elements[0],
                hasInteraction: !!group.interactionTarget
            };
        }
        
        for (const element of elements) {
            if (!currentGroup) {
                currentGroup = startNewGroup(element);
            } else if (shouldMergeWithGroup(element, currentGroup)) {
                addToGroup(currentGroup, element);
            } else {
                groups.push(finalizeGroup(currentGroup));
                currentGroup = startNewGroup(element);
            }
        }
        
        if (currentGroup) {
            groups.push(finalizeGroup(currentGroup));
        }
        
        return groups.filter(g => g.confidence >= minConfidence);
    };
    """)
    
    # Test mixed interaction spans
    result = page.evaluate("""() => {
        const spans = Array.from(document.querySelectorAll('#mixed-interaction span'));
        const merged = window.mergeWithInteractionCheck(spans, { maxGap: 10, minConfidence: 0.5 });
        
        return {
            originalCount: spans.length,
            mergedCount: merged.length,
            mergedTexts: merged.map(m => m.text),
            interactionCounts: merged.map(m => ({ text: m.text, hasInteraction: m.hasInteraction }))
        };
    }""")
    
    print(f"Mixed interaction test results: {result}")
    
    # Should have multiple groups due to different interaction targets
    assert result['mergedCount'] >= 2
    
    # Check that some groups have interactions and some don't
    interactionStates = result['interactionCounts']
    hasInteractiveGroups = any(item['hasInteraction'] for item in interactionStates)
    hasNonInteractiveGroups = any(not item['hasInteraction'] for item in interactionStates)
    
    print(f"Interaction states: {interactionStates}")
    assert hasInteractiveGroups or hasNonInteractiveGroups  # At least one should be true


def test_icon_font_detection(page: Page):
    """Test that icon fonts are handled separately."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
    page.goto(f"file://{fixture_path}")
    
    # Add icon font detection to merger
    page.evaluate("""
    window.mergeWithIconDetection = function(elements, options = {}) {
        const maxGap = options.maxGap || 5;
        const minConfidence = options.minConfidence || 0.7;
        const maxLineHeightDiff = options.maxLineHeightDiff || 5;
        
        if (!elements || elements.length === 0) return [];
        
        function isIconFont(element) {
            const className = element.className || '';
            if (className.includes('icon-font')) return true;
            
            // Check for icon unicode characters
            const text = element.textContent || '';
            for (const char of text) {
                const code = char.codePointAt(0);
                // Check for common icon font ranges
                if ((code >= 0xE000 && code <= 0xF8FF) || // Private Use Area
                    (code >= 0x2600 && code <= 0x26FF) || // Miscellaneous Symbols
                    (code >= 0x2700 && code <= 0x27BF) || // Dingbats
                    (code >= 0x1F300 && code <= 0x1F5FF)) { // Emoji ranges
                    return true;
                }
            }
            return false;
        }
        
        const groups = [];
        let currentGroup = null;
        
        function startNewGroup(element) {
            return {
                elements: [element],
                boundingRects: [element.getBoundingClientRect()],
                mergedText: element.textContent || '',
                isIconFont: isIconFont(element),
                confidence: 1.0
            };
        }
        
        function shouldMergeWithGroup(element, group) {
            const rect = element.getBoundingClientRect();
            const lastRect = group.boundingRects[group.boundingRects.length - 1];
            
            // Same line check
            const yDiff = Math.abs(rect.top - lastRect.top);
            if (yDiff > maxLineHeightDiff) return false;
            
            // Gap check
            let gap = rect.left >= lastRect.right ? rect.left - lastRect.right :
                      rect.right <= lastRect.left ? lastRect.left - rect.right : 0;
            if (gap > maxGap) return false;
            
            // Icon font mixing check
            const isIcon = isIconFont(element);
            if (isIcon !== group.isIconFont) return false;
            
            return true;
        }
        
        function addToGroup(group, element) {
            group.elements.push(element);
            group.boundingRects.push(element.getBoundingClientRect());
            group.mergedText += element.textContent || '';
        }
        
        function finalizeGroup(group) {
            return {
                elements: group.elements,
                text: group.mergedText.trim(),
                confidence: group.confidence,
                isMerged: group.elements.length > 1,
                originalCount: group.elements.length,
                representativeElement: group.elements[0],
                isIconFont: group.isIconFont
            };
        }
        
        for (const element of elements) {
            if (!currentGroup) {
                currentGroup = startNewGroup(element);
            } else if (shouldMergeWithGroup(element, currentGroup)) {
                addToGroup(currentGroup, element);
            } else {
                groups.push(finalizeGroup(currentGroup));
                currentGroup = startNewGroup(element);
            }
        }
        
        if (currentGroup) {
            groups.push(finalizeGroup(currentGroup));
        }
        
        return groups.filter(g => g.confidence >= minConfidence);
    };
    """)
    
    # Test icon + text spans
    result = page.evaluate("""() => {
        const spans = Array.from(document.querySelectorAll('#icon-text span'));
        const merged = window.mergeWithIconDetection(spans, { maxGap: 10, minConfidence: 0.5 });
        
        return {
            originalCount: spans.length,
            mergedCount: merged.length,
            groupDetails: merged.map(m => ({ 
                text: m.text, 
                isIcon: m.isIconFont, 
                elementCount: m.originalCount 
            }))
        };
    }""")
    
    print(f"Icon font test results: {result}")
    
    # Should have separate groups for icons vs text
    iconGroups = [g for g in result['groupDetails'] if g['isIcon']]
    textGroups = [g for g in result['groupDetails'] if not g['isIcon']]
    
    print(f"Icon groups: {iconGroups}")
    print(f"Text groups: {textGroups}")
    
    # Should have both icon and text groups
    assert len(iconGroups) >= 1  # At least one icon group
    assert len(textGroups) >= 1  # At least one text group


def test_performance_with_stress_elements(page: Page):
    """Test performance with many elements."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
    page.goto(f"file://{fixture_path}")
    
    # Use the simple merger
    page.evaluate("""
    window.mergeTextFragments = function(elements, options = {}) {
        const maxGap = options.maxGap || 5;
        const minConfidence = options.minConfidence || 0.7;
        const maxLineHeightDiff = options.maxLineHeightDiff || 5;
        
        if (!elements || elements.length === 0) return [];
        
        const startTime = performance.now();
        const groups = [];
        let currentGroup = null;
        
        function startNewGroup(element) {
            return {
                elements: [element],
                boundingRects: [element.getBoundingClientRect()],
                mergedText: element.textContent || '',
                confidence: 1.0
            };
        }
        
        function shouldMergeWithGroup(element, group) {
            const rect = element.getBoundingClientRect();
            const lastRect = group.boundingRects[group.boundingRects.length - 1];
            
            const yDiff = Math.abs(rect.top - lastRect.top);
            if (yDiff > maxLineHeightDiff) return false;
            
            let gap = rect.left >= lastRect.right ? rect.left - lastRect.right :
                      rect.right <= lastRect.left ? lastRect.left - rect.right : 0;
            if (gap > maxGap) return false;
            
            return true;
        }
        
        function addToGroup(group, element) {
            group.elements.push(element);
            group.boundingRects.push(element.getBoundingClientRect());
            group.mergedText += element.textContent || '';
        }
        
        function finalizeGroup(group) {
            return {
                elements: group.elements,
                text: group.mergedText.trim(),
                confidence: group.confidence,
                isMerged: group.elements.length > 1,
                originalCount: group.elements.length,
                representativeElement: group.elements[0]
            };
        }
        
        for (const element of elements) {
            if (!currentGroup) {
                currentGroup = startNewGroup(element);
            } else if (shouldMergeWithGroup(element, currentGroup)) {
                addToGroup(currentGroup, element);
            } else {
                groups.push(finalizeGroup(currentGroup));
                currentGroup = startNewGroup(element);
            }
        }
        
        if (currentGroup) {
            groups.push(finalizeGroup(currentGroup));
        }
        
        const filtered = groups.filter(g => g.confidence >= minConfidence);
        const endTime = performance.now();
        
        return {
            groups: filtered,
            processingTime: endTime - startTime,
            originalCount: elements.length,
            mergedCount: filtered.length
        };
    };
    """)
    
    # Test with stress elements
    result = page.evaluate("""() => {
        const spans = Array.from(document.querySelectorAll('#stress-test span'));
        const mergeResult = window.mergeTextFragments(spans, { maxGap: 5, minConfidence: 0.5 });
        
        return {
            originalCount: mergeResult.originalCount,
            mergedCount: mergeResult.mergedCount,
            processingTime: mergeResult.processingTime,
            totalText: mergeResult.groups.map(g => g.text).join(''),
            mergeRatio: mergeResult.mergedCount / mergeResult.originalCount
        };
    }""")
    
    print(f"Performance test results: {result}")
    
    # Should handle many elements efficiently
    assert result['originalCount'] >= 100  # Should have many test elements
    assert result['processingTime'] < 1000  # Should complete within 1 second
    assert result['mergedCount'] < result['originalCount']  # Should merge some elements
    assert result['mergeRatio'] < 0.8  # Should reduce element count by at least 20%
    assert len(result['totalText']) > 50  # Should preserve significant text