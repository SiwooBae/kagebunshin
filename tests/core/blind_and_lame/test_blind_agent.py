"""
Tests for BlindAgent - The agent with reasoning but no direct page access.

Tests cover:
- Agent initialization and LangGraph workflow setup
- Reasoning and planning through act() tool
- Task completion detection and workflow management
- Streaming capabilities
- Integration with LameAgent
- Drop-in compatibility with KageBunshinAgent interface
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path

from kagebunshin.core.blind_and_lame.blind_agent import BlindAgent
from kagebunshin.core.blind_and_lame.lame_agent import LameAgent
from kagebunshin.core.agent import KageBunshinAgent
from kagebunshin.core.state_manager import KageBunshinStateManager
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from playwright.async_api import BrowserContext


@pytest.fixture
def mock_lame_agent():
    """Create a mock LameAgent for testing."""
    mock_lame = Mock(spec=LameAgent)
    
    # Create a mock act tool
    @tool
    async def mock_act(command: str) -> str:
        """Mock act tool that returns predictable responses."""
        return f"Executed: {command}"
    
    mock_lame.get_act_tool_for_blind.return_value = mock_act
    mock_lame.get_current_state_description = AsyncMock(return_value="Mock page state")
    mock_lame.dispose = Mock()
    
    return mock_lame


class TestBlindAgentInitialization:
    """Test BlindAgent initialization and configuration."""
    
    def test_should_create_blind_agent_successfully(self, mock_lame_agent):
        """Test successful BlindAgent creation with LameAgent."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model') as mock_init_llm:
            mock_llm = Mock()
            mock_llm.bind_tools.return_value = Mock()
            mock_init_llm.return_value = mock_llm
            
            blind_agent = BlindAgent(mock_lame_agent)
            
            assert blind_agent.lame_agent == mock_lame_agent
            assert blind_agent.llm == mock_llm
            assert blind_agent.act_tool is not None
            assert blind_agent.llm_with_tools is not None
            assert blind_agent.agent is not None  # LangGraph workflow compiled
    
    def test_should_load_system_prompt_from_file(self, mock_lame_agent):
        """Test that BlindAgent loads system prompt from configuration file."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = "Custom blind agent prompt"
                
                blind_agent = BlindAgent(mock_lame_agent)
                
                assert blind_agent.system_prompt == "Custom blind agent prompt"
    
    def test_should_handle_missing_prompt_file_gracefully(self, mock_lame_agent):
        """Test fallback behavior when system prompt file is missing."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            with patch('builtins.open', side_effect=FileNotFoundError):
                blind_agent = BlindAgent(mock_lame_agent)
                
                assert "blind agent" in blind_agent.system_prompt.lower()
                assert "act() tool" in blind_agent.system_prompt.lower()
    
    def test_should_configure_llm_with_reasoning_for_gpt5(self, mock_lame_agent):
        """Test that GPT-5 models get reasoning configuration."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model') as mock_init_llm:
            # Mock the settings to use GPT-5
            with patch.dict('kagebunshin.core.blind_and_lame.blind_agent.__dict__', {
                'BLIND_MODEL': 'gpt-5', 
                'BLIND_PROVIDER': 'openai',
                'BLIND_REASONING_EFFORT': 'medium',
                'BLIND_TEMPERATURE': 1.0
            }):
                blind_agent = BlindAgent(mock_lame_agent)
                
                # Verify init_chat_model was called with reasoning parameter
                call_kwargs = mock_init_llm.call_args[1]
                assert 'reasoning' in call_kwargs
                assert call_kwargs['reasoning'] == {'effort': 'medium'}


# NOTE: The following tests are commented out as they test the old BlindAgent architecture
# The new BlindAgent uses KageBunshinAgent-compatible interface and ReAct agent internally
# See TestBlindAgentKageBunshinCompatibility for the new interface tests

# class TestBlindAgentWorkflow:
#     """Test LangGraph workflow execution and routing."""
#     (Tests commented out - see new compatibility tests below)


# NOTE: The following test classes are commented out as they test the old BlindAgent architecture
# The new BlindAgent uses KageBunshinAgent-compatible interface and ReAct agent internally
# See TestBlindAgentKageBunshinCompatibility for the new interface tests

# class TestBlindAgentExecution:
# class TestBlindAgentAnswerExtraction:
# class TestBlindAgentIntegration:
# class TestBlindAgentEdgeCases:
# (All commented out - see new compatibility tests below)


class TestBlindAgentKageBunshinCompatibility:
    """Test BlindAgent's drop-in compatibility with KageBunshinAgent interface."""

    @pytest.fixture
    def mock_browser_context(self):
        """Create a mock BrowserContext for testing."""
        mock_context = Mock(spec=BrowserContext)
        return mock_context

    @pytest.fixture
    def mock_state_manager(self):
        """Create a mock KageBunshinStateManager for testing."""
        mock_state_manager = Mock(spec=KageBunshinStateManager)
        mock_state_manager.get_tools_for_llm.return_value = []
        mock_state_manager.num_actions_done = 5
        mock_state_manager.current_state = None  # Add current_state attribute
        return mock_state_manager

    @pytest.mark.asyncio
    async def test_should_create_blind_agent_with_kagebunshin_interface(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent.create() works with KageBunshinAgent parameters."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.LameAgent.create') as mock_lame_create:
            mock_lame_agent = Mock()
            mock_lame_agent.get_act_tool_for_blind.return_value = Mock()
            mock_lame_create.return_value = mock_lame_agent
            
            with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model') as mock_init_llm:
                mock_llm = Mock()
                mock_llm.bind_tools.return_value = Mock()
                mock_init_llm.return_value = mock_llm
                
                with patch('kagebunshin.core.state_manager.KageBunshinStateManager.create', return_value=mock_state_manager) as mock_state_create:
                    with patch.object(BlindAgent, '_initialize_react_agent') as mock_init_react:
                        # Create BlindAgent using KageBunshinAgent's interface
                        blind_agent = await BlindAgent.create(
                            context=mock_browser_context,
                            additional_tools=[],
                            system_prompt="Custom system prompt",
                            enable_summarization=True,  # Should be ignored
                            group_room="test_room",
                            username="test_agent",
                            clone_depth=1,
                            llm_model="gpt-4",
                            llm_provider="openai",
                            filesystem_enabled=True,  # Should be ignored
                        )
                        
                        # Manually set agent after creation to avoid tool creation issues
                        blind_agent.agent = Mock()
                    
                    # Verify BlindAgent was created with proper attributes
                    assert blind_agent.initial_context == mock_browser_context
                    assert blind_agent.state_manager == mock_state_manager
                    assert blind_agent.username == "test_agent"
                    assert blind_agent.clone_depth == 1
                    assert blind_agent.group_room == "test_room"
                    assert blind_agent.system_prompt == "Custom system prompt"
                    assert blind_agent.lame_agent == mock_lame_agent

    def test_should_have_same_constructor_signature_as_kagebunshin_agent(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent constructor accepts all KageBunshinAgent parameters."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            with patch('kagebunshin.core.blind_and_lame.blind_agent.LameAgent') as mock_lame_class:
                mock_lame_agent = Mock()
                mock_lame_agent.get_act_tool_for_blind.return_value = Mock()
                mock_lame_class.return_value = mock_lame_agent
                
                # Create BlindAgent with all KageBunshinAgent parameters
                blind_agent = BlindAgent(
                    context=mock_browser_context,
                    state_manager=mock_state_manager,
                    additional_tools=[],
                    system_prompt="Test prompt",
                    enable_summarization=True,
                    group_room="test_room",
                    username="test_user",
                    clone_depth=2,
                    llm=None,
                    llm_model="gpt-4",
                    llm_provider="openai",
                    llm_reasoning_effort="medium",
                    llm_temperature=0.7,
                    summarizer_llm=None,
                    summarizer_model="gpt-3.5-turbo",
                    summarizer_provider="openai",
                    summarizer_reasoning_effort="low",
                    recursion_limit=100,
                    filesystem_enabled=True,
                    filesystem_sandbox_base="/tmp",
                )
                
                # Should not raise any errors and should have expected attributes
                assert blind_agent.username == "test_user"
                assert blind_agent.clone_depth == 2
                assert blind_agent.recursion_limit == 100

    @pytest.mark.asyncio
    async def test_should_implement_kagebunshin_agent_interface_methods(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent implements all required KageBunshinAgent methods."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.LameAgent.create') as mock_lame_create:
            mock_lame_agent = Mock()
            mock_lame_agent.get_act_tool_for_blind.return_value = Mock()
            mock_lame_agent.get_current_url = AsyncMock(return_value="https://example.com")
            mock_lame_create.return_value = mock_lame_agent
            
            with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
                with patch('kagebunshin.core.state_manager.KageBunshinStateManager.create', return_value=mock_state_manager):
                    with patch.object(BlindAgent, '_initialize_react_agent'):
                        blind_agent = await BlindAgent.create(
                            context=mock_browser_context,
                            username="test_agent"
                        )
                        blind_agent.agent = Mock()  # Set mock agent
                        
                        # Test interface methods exist and work
                        url = await blind_agent.get_current_url()
                        assert url == "https://example.com"
                        
                        title = await blind_agent.get_current_title()
                        assert isinstance(title, str)
                        
                        action_count = blind_agent.get_action_count()
                        assert isinstance(action_count, int)
                        
                        # Test dispose method
                        blind_agent.dispose()
                        mock_lame_agent.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_handle_ainvoke_like_kagebunshin_agent(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent.ainvoke works like KageBunshinAgent.ainvoke."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.LameAgent.create') as mock_lame_create:
            mock_lame_agent = Mock()
            mock_lame_agent.get_act_tool_for_blind.return_value = Mock()
            mock_lame_create.return_value = mock_lame_agent
            
            with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
                with patch('kagebunshin.core.state_manager.KageBunshinStateManager.create', return_value=mock_state_manager):
                    with patch.object(BlindAgent, '_initialize_react_agent'):
                        blind_agent = await BlindAgent.create(
                            context=mock_browser_context,
                            username="test_agent"
                        )
                        
                        # Mock the agent workflow
                        mock_final_state = {
                            "messages": [
                                HumanMessage(content="Test task"),
                                AIMessage(content="Task completed successfully!")
                            ]
                        }
                        blind_agent.agent = AsyncMock()
                        blind_agent.agent.ainvoke.return_value = mock_final_state
                        
                        # Test ainvoke
                        result = await blind_agent.ainvoke("Test task")
                        
                        # Should return string like KageBunshinAgent
                        assert isinstance(result, str)
                        assert "task completed successfully" in result.lower()

    @pytest.mark.asyncio
    async def test_should_handle_astream_like_kagebunshin_agent(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent.astream works like KageBunshinAgent.astream."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.LameAgent.create') as mock_lame_create:
            mock_lame_agent = Mock()
            mock_lame_agent.get_act_tool_for_blind.return_value = Mock()
            mock_lame_create.return_value = mock_lame_agent
            
            with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
                with patch('kagebunshin.core.state_manager.KageBunshinStateManager.create', return_value=mock_state_manager):
                    with patch.object(BlindAgent, '_initialize_react_agent'):
                        blind_agent = await BlindAgent.create(
                            context=mock_browser_context,
                            username="test_agent"
                        )
                        
                        # Mock streaming workflow
                        async def mock_astream(*args, **kwargs):
                            yield {"agent": {"messages": [AIMessage(content="Planning...")]}}
                            yield {"action": {"messages": [ToolMessage(content="Action executed", tool_call_id="1")]}}
                        
                        blind_agent.agent = Mock()
                        blind_agent.agent.astream = mock_astream
                        
                        # Test astream
                        chunks = []
                        async for chunk in blind_agent.astream("Test streaming task"):
                            chunks.append(chunk)
                        
                        # Should yield dictionaries like KageBunshinAgent
                        assert len(chunks) == 2
                        assert "agent" in chunks[0]
                        assert "action" in chunks[1]

    def test_should_maintain_persistent_messages_across_turns(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent maintains message history like KageBunshinAgent."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(
                context=mock_browser_context,
                state_manager=mock_state_manager,
                username="test_agent"
            )
            
            # Initially should have empty persistent messages
            assert blind_agent.persistent_messages == []
            
            # Add some messages
            test_messages = [
                HumanMessage(content="First task"),
                AIMessage(content="Completed first task")
            ]
            blind_agent.persistent_messages = test_messages
            
            # Should persist the messages
            assert len(blind_agent.persistent_messages) == 2
            assert blind_agent.persistent_messages[0].content == "First task"

    @pytest.mark.asyncio
    async def test_should_enforce_instance_limits_like_kagebunshin_agent(self, mock_browser_context):
        """Test that BlindAgent enforces instance limits like KageBunshinAgent."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.LameAgent.create'):
            with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
                with patch('kagebunshin.core.state_manager.KageBunshinStateManager.create'):
                    # Set instance count to max limit
                    original_count = BlindAgent._INSTANCE_COUNT
                    try:
                        with patch('kagebunshin.config.settings.MAX_KAGEBUNSHIN_INSTANCES', 1):
                            BlindAgent._INSTANCE_COUNT = 1
                            
                            # Should raise RuntimeError when limit exceeded
                            with pytest.raises(RuntimeError, match="Instance limit reached"):
                                await BlindAgent.create(context=mock_browser_context)
                    finally:
                        # Reset instance count
                        BlindAgent._INSTANCE_COUNT = original_count

    def test_should_support_group_chat_compatibility(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent has group chat support like KageBunshinAgent."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(
                context=mock_browser_context,
                state_manager=mock_state_manager,
                group_room="test_room",
                username="test_agent"
            )
            
            # Should have group chat attributes
            assert blind_agent.group_room == "test_room"
            assert blind_agent.username == "test_agent"
            assert hasattr(blind_agent, 'group_client')
            assert hasattr(blind_agent, '_post_intro_message')

    def test_should_provide_filesystem_compatibility_methods(self, mock_browser_context, mock_state_manager):
        """Test that BlindAgent provides filesystem compatibility methods."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(
                context=mock_browser_context,
                state_manager=mock_state_manager,
                username="test_agent"
            )
            
            # Should have filesystem compatibility methods
            fs_context = blind_agent.get_filesystem_context()
            assert isinstance(fs_context, str)
            assert "blindagent" in fs_context.lower()
            
            cleanup_result = blind_agent.cleanup_filesystem()
            assert isinstance(cleanup_result, dict)
            assert cleanup_result["status"] == "skipped"