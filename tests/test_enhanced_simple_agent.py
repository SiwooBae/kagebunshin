"""
Unit tests for the enhanced Agent API with comprehensive configuration.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage


class TestEnhancedSimpleAgent:
    """Test suite for the enhanced simplified Agent API."""
    
    def test_should_initialize_with_comprehensive_config(self):
        """Test agent initialization with all configuration parameters."""
        from kagebunshin import Agent
        
        mock_llm = Mock()
        
        agent = Agent(
            task="Complex research task",
            llm=mock_llm,
            llm_model="gpt-4o-mini",
            llm_provider="openai",
            llm_reasoning_effort="high",
            llm_temperature=0.5,
            summarizer_model="gpt-5-nano",
            enable_summarization=True,
            headless=True,
            viewport_width=1920,
            viewport_height=1080,
            recursion_limit=200,
            max_iterations=50,
            timeout=120,
            group_room="research_team",
            username="researcher"
        )
        
        assert agent.config.task == "Complex research task"
        assert agent.config.llm == mock_llm
        assert agent.config.llm_model == "gpt-4o-mini"
        assert agent.config.llm_provider == "openai"
        assert agent.config.llm_reasoning_effort == "high"
        assert agent.config.llm_temperature == 0.5
        assert agent.config.summarizer_model == "gpt-5-nano"
        assert agent.config.enable_summarization is True
        assert agent.config.headless is True
        assert agent.config.viewport_width == 1920
        assert agent.config.viewport_height == 1080
        assert agent.config.recursion_limit == 200
        assert agent.config.max_iterations == 50
        assert agent.config.timeout == 120
        assert agent.config.group_room == "research_team"
        assert agent.config.username == "researcher"

    def test_should_initialize_with_defaults_when_no_params_given(self):
        """Test agent uses defaults when only required params provided."""
        from kagebunshin import Agent
        
        agent = Agent(task="Simple task")
        
        assert agent.config.task == "Simple task"
        assert agent.config.llm is None
        assert agent.config.llm_model == "gpt-5-mini"
        assert agent.config.llm_provider == "openai"
        assert agent.config.llm_reasoning_effort == "low"
        assert agent.config.llm_temperature == 1.0
        assert agent.config.headless is False
        assert agent.config.viewport_width == 1280
        assert agent.config.viewport_height == 1280
        assert agent.config.recursion_limit == 150
        assert agent.config.enable_summarization is False

    def test_should_raise_error_for_invalid_config(self):
        """Test agent raises error for invalid configuration."""
        from kagebunshin import Agent
        
        with pytest.raises(ValueError):
            Agent(task="", llm_provider="invalid")

    @pytest.mark.asyncio
    async def test_should_pass_custom_llm_to_kagebunshin_agent(self):
        """Test agent passes custom LLM to KageBunshinAgent."""
        from kagebunshin import Agent
        
        mock_llm = Mock()
        task = "Test task"
        
        with patch('kagebunshin.agent.async_playwright') as mock_playwright:
            # Mock playwright context manager
            mock_p = AsyncMock()
            mock_playwright.return_value.__aenter__.return_value = mock_p
            
            # Mock browser and context
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_p.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            
            # Mock additional dependencies
            with patch('kagebunshin.agent.get_additional_tools') as mock_tools:
                with patch('kagebunshin.agent.apply_fingerprint_profile_to_context') as mock_fingerprint:
                    mock_tools.return_value = []
                    mock_fingerprint.return_value = {'user_agent': 'test'}
                    
                    # Mock KageBunshinAgent
                    with patch('kagebunshin.agent.KageBunshinAgent') as mock_agent_class:
                        mock_agent_instance = AsyncMock()
                        mock_agent_instance.ainvoke.return_value = "result"
                        mock_agent_class.create = AsyncMock(return_value=mock_agent_instance)
                        
                        agent = Agent(task=task, llm=mock_llm, llm_model="custom-model")
                        await agent.run()
                        
                        # Verify custom configuration was passed
                        call_args = mock_agent_class.create.call_args
                        assert call_args[1]['llm'] == mock_llm
                        assert call_args[1]['llm_model'] == "custom-model"

    @pytest.mark.asyncio
    async def test_should_pass_custom_recursion_limit(self):
        """Test agent passes custom recursion limit to KageBunshinAgent."""
        from kagebunshin import Agent
        
        task = "Test task"
        
        with patch('kagebunshin.agent.async_playwright') as mock_playwright:
            mock_p = AsyncMock()
            mock_playwright.return_value.__aenter__.return_value = mock_p
            
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_p.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            
            with patch('kagebunshin.agent.get_additional_tools') as mock_tools:
                with patch('kagebunshin.agent.apply_fingerprint_profile_to_context') as mock_fingerprint:
                    mock_tools.return_value = []
                    mock_fingerprint.return_value = {'user_agent': 'test'}
                    
                    with patch('kagebunshin.agent.KageBunshinAgent') as mock_agent_class:
                        mock_agent_instance = AsyncMock()
                        mock_agent_instance.ainvoke.return_value = "result"
                        mock_agent_class.create = AsyncMock(return_value=mock_agent_instance)
                        
                        agent = Agent(task=task, recursion_limit=300)
                        await agent.run()
                        
                        # Verify custom recursion limit was passed
                        call_args = mock_agent_class.create.call_args
                        assert call_args[1]['recursion_limit'] == 300

    @pytest.mark.asyncio
    async def test_should_use_custom_browser_config(self):
        """Test agent uses custom browser configuration."""
        from kagebunshin import Agent
        
        task = "Test task"
        
        with patch('kagebunshin.agent.async_playwright') as mock_playwright:
            mock_p = AsyncMock()
            mock_playwright.return_value.__aenter__.return_value = mock_p
            
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_p.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            
            with patch('kagebunshin.agent.get_additional_tools') as mock_tools:
                with patch('kagebunshin.agent.apply_fingerprint_profile_to_context') as mock_fingerprint:
                    mock_tools.return_value = []
                    mock_fingerprint.return_value = {'user_agent': 'test'}
                    
                    with patch('kagebunshin.agent.KageBunshinAgent') as mock_agent_class:
                        mock_agent_instance = AsyncMock()
                        mock_agent_instance.ainvoke.return_value = "result"
                        mock_agent_class.create = AsyncMock(return_value=mock_agent_instance)
                        
                        agent = Agent(
                            task=task,
                            headless=True,
                            viewport_width=1920,
                            viewport_height=1080,
                            browser_executable_path="/custom/chrome"
                        )
                        await agent.run()
                        
                        # Verify browser launch options
                        launch_call_args = mock_p.chromium.launch.call_args
                        assert launch_call_args[1]['headless'] is True
                        assert launch_call_args[1]['executable_path'] == "/custom/chrome"
                        
                        # Verify context options
                        context_call_args = mock_browser.new_context.call_args
                        assert context_call_args[1]['viewport']['width'] == 1920
                        assert context_call_args[1]['viewport']['height'] == 1080

    def test_should_validate_configuration_on_init(self):
        """Test agent validates configuration during initialization."""
        from kagebunshin import Agent
        
        # Should raise validation error for invalid parameters
        with pytest.raises(ValueError, match="viewport_width must be a positive integer"):
            Agent(task="Test task", viewport_width=0)
        
        with pytest.raises(ValueError, match="llm_provider must be one of"):
            Agent(task="Test task", llm_provider="invalid")
        
        with pytest.raises(ValueError, match="recursion_limit must be a positive integer"):
            Agent(task="Test task", recursion_limit=-1)

    def test_should_handle_mixed_configuration_approaches(self):
        """Test agent handles both LLM instance and configuration parameters."""
        from kagebunshin import Agent
        
        mock_llm = Mock()
        
        # Should work with LLM instance and still allow config overrides
        agent = Agent(
            task="Test task",
            llm=mock_llm,
            llm_model="custom-model",  # This should be passed through
            llm_temperature=0.2
        )
        
        assert agent.config.llm == mock_llm
        assert agent.config.llm_model == "custom-model"
        assert agent.config.llm_temperature == 0.2

    def test_should_raise_error_for_unknown_parameters(self):
        """Test agent raises error for unknown configuration parameters."""
        from kagebunshin import Agent
        
        # Should raise TypeError for unknown parameters to prevent typos
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            Agent(
                task="Test task",
                unknown_param="should_cause_error"
            )