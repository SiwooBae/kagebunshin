"""
Unit tests for AgentConfig class.
"""

import pytest
from unittest.mock import Mock

from kagebunshin.config.agent_config import AgentConfig


class TestAgentConfig:
    """Test suite for AgentConfig configuration management."""
    
    def test_should_initialize_with_required_task_parameter(self):
        """Test AgentConfig requires task parameter."""
        config = AgentConfig(task="Test task")
        assert config.task == "Test task"
    
    def test_should_raise_error_for_missing_task(self):
        """Test AgentConfig raises error when task is missing."""
        with pytest.raises(ValueError, match="task parameter is required"):
            AgentConfig.from_kwargs()
    
    def test_should_raise_error_for_empty_task(self):
        """Test AgentConfig raises error when task is empty."""
        with pytest.raises(ValueError, match="Task must be a non-empty string"):
            AgentConfig(task="")
    
    def test_should_raise_error_for_whitespace_task(self):
        """Test AgentConfig raises error when task is only whitespace."""
        with pytest.raises(ValueError, match="Task cannot be empty or only whitespace"):
            AgentConfig(task="   ")
    
    def test_should_initialize_with_custom_llm_config(self):
        """Test AgentConfig with custom LLM configuration."""
        mock_llm = Mock()
        config = AgentConfig(
            task="Test task",
            llm=mock_llm,
            llm_model="gpt-4o-mini",
            llm_provider="openai",
            llm_reasoning_effort="high",
            llm_temperature=0.5
        )
        
        assert config.task == "Test task"
        assert config.llm == mock_llm
        assert config.llm_model == "gpt-4o-mini"
        assert config.llm_provider == "openai"
        assert config.llm_reasoning_effort == "high"
        assert config.llm_temperature == 0.5
    
    def test_should_initialize_with_custom_browser_config(self):
        """Test AgentConfig with custom browser configuration."""
        config = AgentConfig(
            task="Test task",
            headless=True,
            viewport_width=1920,
            viewport_height=1080,
            browser_executable_path="/custom/path/chrome",
            user_data_dir="/custom/profile"
        )
        
        assert config.headless is True
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.browser_executable_path == "/custom/path/chrome"
        assert config.user_data_dir == "/custom/profile"
    
    def test_should_initialize_with_custom_workflow_config(self):
        """Test AgentConfig with custom workflow configuration."""
        config = AgentConfig(
            task="Test task",
            recursion_limit=200,
            max_iterations=50,
            timeout=120
        )
        
        assert config.recursion_limit == 200
        assert config.max_iterations == 50
        assert config.timeout == 120
    
    def test_should_validate_llm_provider(self):
        """Test AgentConfig validates LLM provider."""
        with pytest.raises(ValueError, match="llm_provider must be one of"):
            AgentConfig(task="Test task", llm_provider="invalid")
    
    def test_should_validate_llm_reasoning_effort(self):
        """Test AgentConfig validates LLM reasoning effort."""
        with pytest.raises(ValueError, match="llm_reasoning_effort must be one of"):
            AgentConfig(task="Test task", llm_reasoning_effort="invalid")
    
    def test_should_validate_summarizer_config(self):
        """Test AgentConfig validates summarizer configuration."""
        with pytest.raises(ValueError, match="summarizer_provider must be one of"):
            AgentConfig(task="Test task", summarizer_provider="invalid")
        
        with pytest.raises(ValueError, match="summarizer_reasoning_effort must be one of"):
            AgentConfig(task="Test task", summarizer_reasoning_effort="invalid")
    
    def test_should_validate_temperature_range(self):
        """Test AgentConfig validates temperature range."""
        with pytest.raises(ValueError, match="llm_temperature must be a non-negative number"):
            AgentConfig(task="Test task", llm_temperature=-0.5)
    
    def test_should_validate_viewport_dimensions(self):
        """Test AgentConfig validates viewport dimensions."""
        with pytest.raises(ValueError, match="viewport_width must be a positive integer"):
            AgentConfig(task="Test task", viewport_width=0)
        
        with pytest.raises(ValueError, match="viewport_height must be a positive integer"):
            AgentConfig(task="Test task", viewport_height=-100)
    
    def test_should_validate_workflow_parameters(self):
        """Test AgentConfig validates workflow parameters."""
        with pytest.raises(ValueError, match="recursion_limit must be a positive integer"):
            AgentConfig(task="Test task", recursion_limit=0)
        
        with pytest.raises(ValueError, match="max_iterations must be a positive integer"):
            AgentConfig(task="Test task", max_iterations=-5)
        
        with pytest.raises(ValueError, match="timeout must be a positive integer"):
            AgentConfig(task="Test task", timeout=0)
    
    def test_should_convert_to_kagebunshin_kwargs(self):
        """Test AgentConfig converts to KageBunshin kwargs correctly."""
        mock_llm = Mock()
        config = AgentConfig(
            task="Test task",
            llm=mock_llm,
            llm_model="gpt-4o-mini",
            enable_summarization=True,
            group_room="test_room"
        )
        
        kwargs = config.to_kagebunshin_kwargs()
        
        assert kwargs['llm'] == mock_llm
        assert kwargs['llm_model'] == "gpt-4o-mini"
        assert kwargs['enable_summarization'] is True
        assert kwargs['group_room'] == "test_room"
    
    def test_should_get_browser_launch_options(self):
        """Test AgentConfig provides correct browser launch options."""
        config = AgentConfig(
            task="Test task",
            headless=True,
            browser_executable_path="/custom/chrome"
        )
        
        options = config.get_browser_launch_options()
        
        assert options['headless'] is True
        assert options['executable_path'] == "/custom/chrome"
        assert 'args' in options
        assert 'ignore_default_args' in options
    
    def test_should_get_browser_context_options(self):
        """Test AgentConfig provides correct browser context options."""
        config = AgentConfig(
            task="Test task",
            viewport_width=1920,
            viewport_height=1080
        )
        
        options = config.get_browser_context_options()
        
        assert options['viewport']['width'] == 1920
        assert options['viewport']['height'] == 1080
        assert 'permissions' in options
    
    def test_should_create_from_kwargs_with_filtering(self):
        """Test AgentConfig.from_kwargs filters out unknown parameters."""
        config = AgentConfig.from_kwargs(
            task="Test task",
            llm_model="gpt-4o-mini",
            unknown_param="should_be_filtered",
            another_unknown=123
        )
        
        assert config.task == "Test task"
        assert config.llm_model == "gpt-4o-mini"
        # Unknown parameters should not cause errors
    
    def test_should_use_default_values(self):
        """Test AgentConfig uses sensible defaults."""
        config = AgentConfig(task="Test task")
        
        # Should have all defaults set
        assert config.llm is None
        assert config.llm_model == "gpt-5-mini"
        assert config.llm_provider == "openai"
        assert config.headless is False
        assert config.viewport_width == 1280
        assert config.viewport_height == 1280
        assert config.recursion_limit == 150
        assert config.enable_summarization is False