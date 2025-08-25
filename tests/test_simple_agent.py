"""
Unit tests for the simplified Agent API.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage


class TestSimpleAgent:
    """Test suite for the simplified Agent API."""
    
    def test_should_initialize_with_task_and_llm(self):
        """Test agent initialization with task and LLM."""
        from kagebunshin import Agent
        
        mock_llm = Mock()
        task = "Find the price of a Tesla Model S"
        
        agent = Agent(task=task, llm=mock_llm)
        
        assert agent.config.task == task
        assert agent.config.llm == mock_llm

    def test_should_initialize_with_optional_parameters(self):
        """Test agent initialization with optional parameters."""
        from kagebunshin import Agent
        
        mock_llm = Mock()
        task = "Test task"
        
        agent = Agent(
            task=task,
            llm=mock_llm,
            headless=True,
            enable_summarization=True,
            group_room="test_room"
        )
        
        assert agent.config.task == task
        assert agent.config.llm == mock_llm
        assert agent.config.headless is True
        assert agent.config.enable_summarization is True
        assert agent.config.group_room == "test_room"

    @pytest.mark.asyncio
    async def test_should_run_and_return_result(self):
        """Test agent run method returns a result."""
        from kagebunshin import Agent
        
        mock_llm = Mock()
        task = "Test task"
        expected_result = "Task completed successfully"
        
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
                        mock_agent_instance.ainvoke.return_value = expected_result
                        mock_agent_class.create = AsyncMock(return_value=mock_agent_instance)
                
                        agent = Agent(task=task, llm=mock_llm)
                        result = await agent.run()
                        
                        assert result == expected_result
                        mock_agent_instance.ainvoke.assert_called_once_with(task)

    @pytest.mark.asyncio
    async def test_should_handle_browser_lifecycle(self):
        """Test agent properly manages browser lifecycle."""
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
                        
                        agent = Agent(task=task, llm=mock_llm)
                        await agent.run()
                        
                        # Verify browser lifecycle
                        mock_p.chromium.launch.assert_called_once()
                        mock_browser.new_context.assert_called_once()
                        mock_browser.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_handle_headless_parameter(self):
        """Test agent respects headless parameter."""
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
                        
                        agent = Agent(task=task, llm=mock_llm, headless=True)
                        await agent.run()
                        
                        # Verify headless parameter was passed
                        launch_call_args = mock_p.chromium.launch.call_args
                        assert launch_call_args[1]['headless'] is True

    @pytest.mark.asyncio
    async def test_should_pass_llm_to_kagebunshin_agent(self):
        """Test agent passes LLM configuration to KageBunshinAgent."""
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
                        
                        agent = Agent(task=task, llm=mock_llm)
                        await agent.run()
                        
                        # Verify KageBunshinAgent was created with context
                        call_args = mock_agent_class.create.call_args
                        assert call_args[0][0] == mock_context
                        assert call_args[1]['additional_tools'] == []
                        assert call_args[1]['group_room'] == 'lobby'
                        assert call_args[1]['enable_summarization'] == False
                        assert 'username' in call_args[1]