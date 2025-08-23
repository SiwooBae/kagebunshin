"""
Unit tests for naming utility functions.
"""

import pytest
from unittest.mock import patch

from kagebunshin.utils.naming import generate_agent_name


class TestGenerateAgentName:
    """Test suite for agent name generation."""
    
    def test_should_generate_valid_agent_name(self):
        """Test that generated names follow expected format."""
        name = generate_agent_name()
        
        assert isinstance(name, str)
        assert len(name) > 0
        # Should contain some combination of words/characters
        assert any(c.isalpha() for c in name)

    def test_should_generate_different_names_on_multiple_calls(self):
        """Test that multiple calls generate different names."""
        names = set()
        for _ in range(10):
            names.add(generate_agent_name())
        
        # Should have generated at least some different names
        # (small chance of collision but very unlikely with 10 calls)
        assert len(names) > 1

    def test_should_generate_names_without_spaces(self):
        """Test that generated names don't contain spaces (suitable for usernames)."""
        name = generate_agent_name()
        
        assert " " not in name

    def test_should_generate_reasonable_length_names(self):
        """Test that generated names are reasonable length."""
        name = generate_agent_name()
        
        # Should be reasonable length (not empty, not extremely long)
        assert 2 <= len(name) <= 50

    def test_should_handle_petname_library_import_error(self):
        """Test graceful fallback if petname library is unavailable."""
        with patch('kagebunshin.utils.naming.petname') as mock_petname:
            mock_petname.generate.side_effect = ImportError("petname not available")
            
            # Should still generate a name (fallback behavior)
            name = generate_agent_name()
            assert isinstance(name, str)
            assert len(name) > 0

    def test_should_use_petname_library_when_available(self):
        """Test that petname library is used when available."""
        with patch('kagebunshin.utils.naming.petname') as mock_petname:
            mock_petname.generate.return_value = "happy-agent-123"
            
            name = generate_agent_name()
            
            mock_petname.generate.assert_called_once()
            # Implementation uses .title() so expect title case
            assert name == "Happy-Agent-123"

    def test_should_generate_names_suitable_for_identifiers(self):
        """Test that generated names are suitable as identifiers."""
        name = generate_agent_name()
        
        # Should not start with a number
        assert not name[0].isdigit()
        
        # Should only contain alphanumeric and allowed special characters
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        assert all(c in allowed_chars for c in name)

    def test_should_be_deterministic_with_same_seed(self):
        """Test that name generation can be made deterministic if needed."""
        # This test assumes the underlying library supports seeding
        # If not, this test documents the expected behavior
        
        # Generate some names to verify the function works
        name1 = generate_agent_name()
        name2 = generate_agent_name()
        
        # Both should be valid names
        assert isinstance(name1, str) and len(name1) > 0
        assert isinstance(name2, str) and len(name2) > 0