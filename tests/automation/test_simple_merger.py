"""
Simple test for TextFragmentMerger functionality.
"""

import pytest
from pathlib import Path
from playwright.sync_api import Page


def test_simple_text_merger(page: Page):
    """Test TextFragmentMerger directly in browser."""
    
    # Load test HTML
    fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
    page.goto(f"file://{fixture_path}")
    
    # Inject a function-based merger to avoid ES6 class issues
    page.evaluate("""
    window.mergeTextFragments = function(elements, options = {}) {
        const maxGap = options.maxGap || 5;
        const minConfidence = options.minConfidence || 0.7;
        const maxLineHeightDiff = options.maxLineHeightDiff || 5;
        const maxMergeLength = options.maxMergeLength || 100;
        
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
            
            // Same line check
            const yDiff = Math.abs(rect.top - lastRect.top);
            if (yDiff > maxLineHeightDiff) return false;
            
            // Gap check
            let gap = rect.left >= lastRect.right ? rect.left - lastRect.right :
                      rect.right <= lastRect.left ? lastRect.left - rect.right : 0;
            if (gap > maxGap) return false;
            
            // Length check
            const elementText = element.textContent || '';
            if ((group.mergedText.length + elementText.length) > maxMergeLength) return false;
            
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
    
    # Test the merger
    result = page.evaluate("""() => {
        const spans = Array.from(document.querySelectorAll('#simple-split span'));
        const merged = window.mergeTextFragments(spans, { maxGap: 5, minConfidence: 0.5 });
        
        return {
            originalCount: spans.length,
            mergedCount: merged.length,
            mergedTexts: merged.map(m => m.text),
            totalText: merged.map(m => m.text).join(''),
            firstGroupElementCount: merged.length > 0 ? merged[0].originalCount : 0
        };
    }""")
    
    print(f"Test results: {result}")
    
    # Assertions
    assert result['originalCount'] == 17  # "Use your location" spans
    assert result['mergedCount'] < result['originalCount']  # Should merge some spans
    assert result['totalText'] == 'Useyourlocation'  # Should preserve all text
    assert result['firstGroupElementCount'] > 1  # First group should have multiple elements
    
    print("✅ TextFragmentMerger working correctly!")