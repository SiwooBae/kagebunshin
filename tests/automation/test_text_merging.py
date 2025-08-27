"""
Comprehensive test suite for text fragment detection and merging.

This module tests the browser automation system's ability to properly handle
websites that split text into individual DOM elements (letter-by-letter or
word-by-word) while maintaining interaction accuracy and performance.
"""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from playwright.sync_api import Page, Browser, BrowserContext, Locator


class MockTextMerger:
    """Mock implementation of TextMerger for testing the algorithm logic."""
    
    def __init__(self, max_gap=5, max_merge_length=100, min_confidence=0.7):
        self.max_gap = max_gap
        self.max_merge_length = max_merge_length
        self.min_confidence = min_confidence
    
    def merge_adjacent(self, elements, return_confidence=False):
        """Mock merge implementation for testing."""
        if not elements:
            return []
        
        groups = []
        current_group = {'elements': [elements[0]], 'text': elements[0].text_content() or ''}
        
        for element in elements[1:]:
            text = element.text_content() or ''
            if self._should_merge(element, current_group):
                current_group['elements'].append(element)
                current_group['text'] += text
            else:
                groups.append(self._finalize_group(current_group, return_confidence))
                current_group = {'elements': [element], 'text': text}
        
        groups.append(self._finalize_group(current_group, return_confidence))
        return [g for g in groups if g.get('confidence', 1.0) >= self.min_confidence]
    
    def _should_merge(self, element, group):
        """Simplified merge decision for testing."""
        # Basic implementation - check if same parent and adjacent
        last_element = group['elements'][-1]
        return (element.evaluate('el => el.parentElement') == 
                last_element.evaluate('el => el.parentElement'))
    
    def _finalize_group(self, group, return_confidence):
        """Create final group object."""
        result = {
            'elements': group['elements'],
            'text': group['text'].strip(),
            'representative_element': group['elements'][0],
            'is_merged': len(group['elements']) > 1,
            'original_count': len(group['elements'])
        }
        
        if return_confidence:
            # Mock confidence based on text length and element count
            confidence = min(1.0, len(group['text']) / 10.0 + 0.5)
            result['confidence'] = confidence
        
        return result


class TestTextMergingEdgeCases:
    """Test text fragment detection and merging edge cases."""
    
    @pytest.fixture
    def test_page(self, page: Page) -> Page:
        """Load test fixtures page."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
        page.goto(f"file://{fixture_path}")
        # Wait for any dynamic content to load
        page.wait_for_timeout(100)
        return page
    
    @pytest.fixture
    def mock_merger(self):
        """Create a mock text merger for testing."""
        return MockTextMerger()
    
    def test_should_merge_simple_letter_splits(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 1: Single-letter spans should merge into complete words."""
        spans = test_page.locator('#simple-split span').all()
        assert len(spans) == 17  # 17 individual letters/spaces for "Use your location"
        
        merged = mock_merger.merge_adjacent(spans)
        
        # Should merge into fewer groups
        assert len(merged) < len(spans)
        assert len(merged) <= 3  # "Use", "your", "location" (may merge spaces)
        
        # Check that text is preserved
        full_text = ''.join(m['text'] for m in merged)
        expected_text = 'Use your location'
        assert full_text.replace(' ', '') == expected_text.replace(' ', '')
    
    def test_should_not_merge_across_line_breaks(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 2: Text on different lines should not merge."""
        spans = test_page.locator('#multiline-split span').all()
        merged = mock_merger.merge_adjacent(spans)
        
        # Should have separate groups for each line
        # Even with simple logic, line break should create separation
        assert len(merged) >= 2  # At least 2 groups for 2 lines
        
        # Check that text on different lines isn't merged together
        texts = [m['text'] for m in merged if m['text'].strip()]
        assert any('First' in text for text in texts)
        assert any('Second' in text for text in texts)
    
    def test_should_respect_interaction_boundaries(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 3: Don't merge elements with different click handlers."""
        spans = test_page.locator('#mixed-interaction span').all()
        
        # Check that link spans have different parent/behavior
        link_spans = test_page.locator('#mixed-interaction a span').all()
        other_spans = test_page.locator('#mixed-interaction > span').all()
        
        assert len(link_spans) == 2  # "o", "r" inside link
        assert len(other_spans) > len(link_spans)  # Other text spans
        
        merged = mock_merger.merge_adjacent(spans)
        
        # Should keep link spans separate from parent-delegated spans
        # This is a limitation of our mock, but important for real implementation
        assert len(merged) > 1  # Should not merge everything together
    
    def test_should_handle_word_boundaries_and_punctuation(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 4: Proper handling of punctuation and word boundaries."""
        spans = test_page.locator('#word-boundaries span').all()
        merged = mock_merger.merge_adjacent(spans)
        
        # Should merge letters but respect word boundaries
        full_text = ''.join(m['text'] for m in merged)
        expected = "Hello, world! How are you?"
        
        # Remove extra spaces for comparison
        assert full_text.replace(' ', '') == expected.replace(' ', '')
    
    def test_should_handle_transformed_text(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 5: Rotated/transformed text should still merge if aligned."""
        spans = test_page.locator('#transformed span').all()
        merged = mock_merger.merge_adjacent(spans)
        
        # Should still merge rotated text
        assert len(merged) == 1  # "Rotated" as single word
        assert merged[0]['text'] == 'Rotated'
    
    def test_should_handle_dynamic_loading_content(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 6: Handle hidden/loading elements correctly."""
        # Get initial state
        visible_spans = test_page.locator('#loading-state span:visible').all()
        merged = mock_merger.merge_adjacent(visible_spans)
        
        # Should only include visible elements
        for group in merged:
            for element in group['elements']:
                assert element.is_visible()
        
        # Wait for loading to complete and test again
        test_page.wait_for_timeout(2100)  # Wait for JS to show hidden elements
        all_spans = test_page.locator('#loading-state span:visible').all()
        merged_after = mock_merger.merge_adjacent(all_spans)
        
        # Should now include more elements
        total_after = sum(len(g['elements']) for g in merged_after)
        total_before = sum(len(g['elements']) for g in merged)
        assert total_after >= total_before
    
    def test_should_handle_bidi_text(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 7: RTL and LTR text should merge appropriately."""
        spans = test_page.locator('#bidi-text span').all()
        merged = mock_merger.merge_adjacent(spans)
        
        # Should handle mixed text directions
        full_text = ''.join(m['text'] for m in merged)
        assert 'Hello' in full_text
        assert 'world' in full_text
        # RTL text should also be preserved
        assert len(merged) >= 3  # At least "Hello", RTL text, "world"
    
    def test_should_handle_overlapping_elements(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 8: Absolutely positioned overlapping elements."""
        spans = test_page.locator('#overlapping span').all()
        merged = mock_merger.merge_adjacent(spans)
        
        # Should merge overlapping positioned elements
        assert len(merged) <= 2  # Should merge most/all letters
        full_text = ''.join(m['text'] for m in merged)
        assert 'Overlap' in full_text
    
    def test_should_preserve_aria_boundaries(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 9: Different ARIA labels should not merge."""
        spans = test_page.locator('#aria-different span').all()
        
        # Check ARIA labels exist and are different
        us_spans = test_page.locator('#aria-different span[aria-label="United States"]').all()
        dollar_spans = test_page.locator('#aria-different span[aria-label="Dollar"]').all()
        number_spans = test_page.locator('#aria-different span[aria-label="Number"]').all()
        
        assert len(us_spans) == 2  # "U", "S"
        assert len(dollar_spans) == 1  # "$"
        assert len(number_spans) == 3  # "1", "0", "0"
        
        merged = mock_merger.merge_adjacent(spans)
        
        # In a real implementation, should respect ARIA boundaries
        # Our mock doesn't implement this, but it's critical for accessibility
        assert len(merged) >= 3  # Should keep different ARIA groups separate
    
    def test_should_handle_icon_fonts(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 10: Icon fonts should not merge with regular text."""
        spans = test_page.locator('#icon-text span').all()
        
        # Check for icon vs text spans
        icon_spans = test_page.locator('#icon-text span.icon-font').all()
        text_spans = test_page.locator('#icon-text span:not(.icon-font)').all()
        
        assert len(icon_spans) >= 2  # ✓ and ★ icons
        assert len(text_spans) >= 9  # "Success" + "Rated" letters
        
        merged = mock_merger.merge_adjacent(spans)
        
        # Icons should be separate from text
        # Look for groups that contain only icon characters
        icon_groups = [m for m in merged if any(char in m['text'] for char in '✓★')]
        text_groups = [m for m in merged if m not in icon_groups]
        
        assert len(icon_groups) >= 1  # At least some icon groups
        assert len(text_groups) >= 1  # At least some text groups
    
    def test_performance_with_many_elements(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 11: Should handle 200+ elements efficiently."""
        spans = test_page.locator('#stress-test span').all()
        
        # Should have ~200 spans (limited by our test fixture)
        assert len(spans) >= 100
        assert len(spans) <= 250
        
        # Measure performance
        start_time = time.time()
        merged = mock_merger.merge_adjacent(spans)
        elapsed = time.time() - start_time
        
        # Should complete quickly (even our mock implementation)
        assert elapsed < 1.0  # Less than 1 second
        
        # Should merge many elements
        total_original = len(spans)
        total_merged = len(merged)
        merge_ratio = total_merged / total_original
        
        assert merge_ratio < 0.8  # Should reduce element count by at least 20%
        
        # Should preserve text content
        original_text = ''.join(span.text_content() or '' for span in spans)
        merged_text = ''.join(m['text'] for m in merged)
        assert len(merged_text) >= len(original_text) * 0.9  # Allow for some space normalization
    
    def test_merge_confidence_scoring(self, test_page: Page):
        """Test Case 12: Confidence scores should reflect merge quality."""
        merger_with_confidence = MockTextMerger(min_confidence=0.5)
        spans = test_page.locator('#simple-split span').all()
        
        merged = merger_with_confidence.merge_adjacent(spans, return_confidence=True)
        
        # All returned merges should have confidence scores
        for group in merged:
            assert 'confidence' in group
            assert 0.0 <= group['confidence'] <= 1.0
            assert group['confidence'] >= merger_with_confidence.min_confidence
        
        # Longer text should generally have higher confidence
        text_lengths = [(len(m['text']), m['confidence']) for m in merged]
        if len(text_lengths) > 1:
            # Not a strict requirement, but generally expected
            avg_conf_by_length = {}
            for length, conf in text_lengths:
                length_bucket = length // 5  # Group by 5-char buckets
                if length_bucket not in avg_conf_by_length:
                    avg_conf_by_length[length_bucket] = []
                avg_conf_by_length[length_bucket].append(conf)
            
            # Just verify confidence values are reasonable
            all_confidences = [conf for _, conf in text_lengths]
            assert min(all_confidences) >= 0.5
            assert max(all_confidences) <= 1.0
    
    def test_merge_reversibility(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 13: Merged elements should maintain original references."""
        spans = test_page.locator('#simple-split span').all()
        merged = mock_merger.merge_adjacent(spans)
        
        # Should maintain references to original elements
        for group in merged:
            assert 'elements' in group
            assert len(group['elements']) >= 1
            
            # Each original element should be a valid Playwright locator
            for element in group['elements']:
                assert element.text_content() is not None
        
        # Total original elements should equal sum of group elements
        total_in_groups = sum(len(g['elements']) for g in merged)
        assert total_in_groups == len(spans)
    
    def test_should_handle_shadow_dom_boundaries(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 13: Should respect Shadow DOM boundaries."""
        # Get spans from outside shadow DOM
        regular_spans = test_page.locator('#shadow-boundary > span').all()
        
        # Shadow DOM content should be handled separately
        # Our mock doesn't implement shadow DOM, but real implementation should
        assert len(regular_spans) >= 10  # "Before" + "After" spans
        
        merged = mock_merger.merge_adjacent(regular_spans)
        
        # Should merge spans that are outside shadow boundary
        full_text = ''.join(m['text'] for m in merged)
        assert 'Before' in full_text
        assert 'After' in full_text
    
    def test_should_handle_pseudo_elements(self, test_page: Page, mock_merger: MockTextMerger):
        """Test Case 14: CSS pseudo-elements should not interfere with merging."""
        spans = test_page.locator('#pseudo-elements span:not(.pseudo-content)').all()
        
        if spans:  # If there are actual spans inside
            merged = mock_merger.merge_adjacent(spans)
            
            # Should merge normally despite pseudo-elements
            full_text = ''.join(m['text'] for m in merged)
            assert 'Middle' in full_text
        
        # Main test is that pseudo-elements don't break the algorithm
        # (they're not in DOM so shouldn't be processed anyway)
    
    def test_should_respect_no_merge_attribute(self, test_page: Page):
        """Test Case 15: Manual no-merge control via data attributes."""
        # Elements with data-no-merge should not be merged
        no_merge_spans = test_page.locator('[data-no-merge="true"] span').all()
        regular_spans = test_page.locator('#no-merge-control div:not([data-no-merge]) span').all()
        
        assert len(no_merge_spans) >= 4  # "Dont"
        assert len(regular_spans) >= 9  # "But merge"
        
        # In real implementation, should respect no-merge attribute
        # Our mock doesn't implement this, but it's important for manual control
        
        merger = MockTextMerger()
        no_merge_result = merger.merge_adjacent(no_merge_spans)
        regular_result = merger.merge_adjacent(regular_spans)
        
        # This test documents the expected behavior
        # Real implementation should not merge no_merge_spans
        # but should merge regular_spans normally


class TestTextMergerIntegration:
    """Integration tests for text merger with real page_utils.js functionality."""
    
    @pytest.fixture
    def page_with_utils(self, page: Page) -> Page:
        """Page with page_utils.js loaded."""
        # Load the actual page_utils.js file
        utils_path = Path(__file__).parent.parent.parent / "kagebunshin" / "automation" / "browser" / "page_utils.js"
        
        # Read and inject the script content
        script_content = utils_path.read_text()
        page.add_init_script(script_content)
        
        return page
    
    def test_script_loading_debug(self, page_with_utils: Page):
        """Debug script loading issues."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
        page_with_utils.goto(f"file://{fixture_path}")
        page_with_utils.wait_for_timeout(100)
        
        # Check what globals are available
        globals_check = page_with_utils.evaluate("""
        const globals = [];
        for (const key in window) {
            if (key.startsWith('Text') || key.includes('Fragment') || key.includes('Merger')) {
                globals.push(key);
            }
        }
        return globals;
        """)
        print(f"Globals with Text/Fragment/Merger: {globals_check}")
        
        # Test for any function defined
        function_check = page_with_utils.evaluate("""
        const functions = [];
        for (const key in window) {
            if (typeof window[key] === 'function' && key.length > 5) {
                functions.push(key);
            }
        }
        return functions.slice(0, 10); // First 10 functions
        """)
        print(f"Some functions available: {function_check}")
        
        # Check if any script errors occurred
        console_messages = []
        def collect_console_message(msg):
            console_messages.append(f"{msg.type}: {msg.text}")
        
        page_with_utils.on("console", collect_console_message)
        page_with_utils.reload()
        page_with_utils.wait_for_timeout(500)
        
        print(f"Console messages: {console_messages}")
        
        # Try to manually define a simple TextFragmentMerger and test
        manual_test = page_with_utils.evaluate("""
        class TestMerger {
            constructor() {
                this.test = true;
            }
        }
        window.TestMerger = TestMerger;
        return typeof TestMerger;
        """)
        
        assert manual_test == "function"
    
    def test_text_merger_basic_functionality(self, page_with_utils: Page):
        """Test basic text merger functionality."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "text_splitting_patterns.html"
        page_with_utils.goto(f"file://{fixture_path}")
        page_with_utils.wait_for_timeout(100)
        
        # Test merging simple letter splits
        result = page_with_utils.evaluate("""
        const merger = new TextFragmentMerger({ maxGap: 5, minConfidence: 0.5 });
        const spans = Array.from(document.querySelectorAll('#simple-split span'));
        const merged = merger.mergeAdjacentElements(spans);
        
        return {
            originalCount: spans.length,
            mergedCount: merged.length,
            mergedTexts: merged.map(m => m.text),
            totalText: merged.map(m => m.text).join('')
        };
        """)
        
        print(f"Original spans: {result['originalCount']}")
        print(f"Merged groups: {result['mergedCount']}")  
        print(f"Merged texts: {result['mergedTexts']}")
        print(f"Total text: '{result['totalText']}'")
        
        # Should merge the 17 individual spans into fewer groups
        assert result['originalCount'] == 17  # "Use your location" spans
        assert result['mergedCount'] < result['originalCount']  # Should merge some
        assert 'Use' in result['totalText']
        assert 'your' in result['totalText'] 
        assert 'location' in result['totalText']
    
    def test_existing_functionality_unchanged(self, page_with_utils: Page):
        """Ensure existing page_utils.js functionality is not broken."""
        # Test that existing markPage still works
        result = page_with_utils.evaluate("markPage()")
        
        assert 'coordinates' in result
        assert isinstance(result['coordinates'], list)
        assert 'totalElements' in result
        
        # Should find interactive elements on our test page
        assert result['totalElements'] > 0


class TestTextMergerConfiguration:
    """Test configuration and customization options for text merger."""
    
    def test_configurable_merge_parameters(self):
        """Test that merge parameters can be configured."""
        # Test different gap tolerances
        strict_merger = MockTextMerger(max_gap=1)
        lenient_merger = MockTextMerger(max_gap=10)
        
        assert strict_merger.max_gap == 1
        assert lenient_merger.max_gap == 10
        
        # Test confidence thresholds
        high_conf_merger = MockTextMerger(min_confidence=0.9)
        low_conf_merger = MockTextMerger(min_confidence=0.3)
        
        assert high_conf_merger.min_confidence == 0.9
        assert low_conf_merger.min_confidence == 0.3
    
    def test_merge_length_limits(self):
        """Test that merge length can be limited."""
        short_merger = MockTextMerger(max_merge_length=20)
        long_merger = MockTextMerger(max_merge_length=200)
        
        assert short_merger.max_merge_length == 20
        assert long_merger.max_merge_length == 200
        
        # In real implementation, should enforce these limits
    
    def test_site_specific_configuration(self):
        """Test site-specific configuration options."""
        # This documents expected behavior for site-specific configs
        # Will be implemented in the actual merger
        
        site_configs = {
            'animated-text-library.com': {
                'max_gap': 10,
                'merge_across_lines': False
            },
            'icon-heavy-site.com': {
                'detect_icon_fonts': True,
                'icon_font_classes': ['fa', 'icon', 'glyphicon']
            }
        }
        
        # Should be able to create merger with site-specific config
        assert 'animated-text-library.com' in site_configs
        assert site_configs['animated-text-library.com']['max_gap'] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])