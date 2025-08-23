"""
Unit tests for KageBunshinAgent.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from kagebunshin.core.agent import KageBunshinAgent
from kagebunshin.core.state import KageBunshinState


class TestKageBunshinAgent:
    """Test suite for KageBunshinAgent initialization and core functionality."""
    
    def test_should_initialize_with_default_parameters(self, mock_browser_context, state_manager):
        """Test agent initialization with default settings."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=state_manager
            )
            
            assert agent.initial_context == mock_browser_context
            assert agent.state_manager == state_manager
            assert agent.clone_depth == 0
            assert len(agent.persistent_messages) == 0

    def test_should_initialize_with_custom_parameters(self, mock_browser_context, state_manager):
        """Test agent initialization with custom parameters."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            custom_prompt = "Custom system prompt"
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=state_manager,
                system_prompt=custom_prompt,
                clone_depth=2,
                username="test_agent"
            )
            
            assert agent.system_prompt == custom_prompt
            assert agent.clone_depth == 2
            assert agent.username == "test_agent"

    def test_should_bind_tools_to_llm_on_initialization(self, mock_browser_context, state_manager):
        """Test that tools are properly bound to LLM during initialization."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=state_manager
            )
            
            mock_llm.bind_tools.assert_called_once()
            """
Unit tests for KageBunshinAgent.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from kagebunshin.core.agent import KageBunshinAgent
from kagebunshin.core.state import KageBunshinState


class TestKageBunshinAgent:
    """Test suite for KageBunshinAgent initialization and core functionality."""
    
    @pytest.mark.asyncio
    async def test_should_initialize_with_default_parameters(self, mock_browser_context, state_manager):
        """Test agent initialization with default settings."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=await state_manager
            )
            
            assert agent.initial_context == mock_browser_context
            assert agent.state_manager == await state_manager
            assert agent.clone_depth == 0
            assert len(agent.persistent_messages) == 0

    @pytest.mark.asyncio
    async def test_should_initialize_with_custom_parameters(self, mock_browser_context, state_manager):
        """Test agent initialization with custom parameters."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            custom_prompt = "Custom system prompt"
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=await state_manager,
                system_prompt=custom_prompt,
                clone_depth=2,
                username="test_agent"
            )
            
            assert agent.system_prompt == custom_prompt
            assert agent.clone_depth == 2
            assert agent.username == "test_agent"

    @pytest.mark.asyncio
    async def test_should_bind_tools_to_llm_on_initialization(self, mock_browser_context, state_manager):
        """Test that tools are properly bound to LLM during initialization."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=await state_manager
            )
            
            mock_llm.bind_tools.assert_called_once()
            assert agent.llm_with_tools == mock_llm

    @pytest.mark.asyncio
    async def test_should_track_instance_count(self, mock_browser_context, state_manager):
        """Test that agent instances are tracked for concurrency limits."""
        initial_count = KageBunshinAgent._INSTANCE_COUNT
        
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=await state_manager
            )
            
            assert isinstance(agent, KageBunshinAgent)

    @pytest.mark.asyncio
    async def test_should_process_user_input_through_workflow(self, kage_agent, sample_state):
        """Test that user input is processed through the LangGraph workflow."""
        agent = await kage_agent
        with patch.object(agent, 'workflow') as mock_workflow:
            mock_workflow.ainvoke = AsyncMock(return_value=sample_state)
            
            result = await agent.run(sample_state)
            
            mock_workflow.ainvoke.assert_called_once_with(sample_state)
            assert result == sample_state

    @pytest.mark.asyncio
    async def test_should_maintain_persistent_message_history(self, kage_agent):
        """Test that agent maintains message history across turns."""
        agent = await kage_agent
        initial_message = HumanMessage(content="Hello")
        agent.persistent_messages.append(initial_message)
        
        assert len(agent.persistent_messages) == 1
        assert agent.persistent_messages[0] == initial_message
        
        new_message = AIMessage(content="Hi there!")
        agent.persistent_messages.append(new_message)
        
        assert len(agent.persistent_messages) == 2
        assert agent.persistent_messages[1] == new_message

    @pytest.mark.asyncio
    async def test_should_setup_group_chat_client(self, mock_browser_context, state_manager):
        """Test that group chat client is properly initialized."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.GroupChatClient') as mock_group_chat:
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=await state_manager,
                    group_room="test_room"
                )
                
                mock_group_chat.assert_called_once()
                assert agent.group_room == "test_room"

    @pytest.mark.asyncio
    async def test_should_generate_username_when_not_provided(self, mock_browser_context, state_manager):
        """Test that agent generates a username when none is provided."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.generate_agent_name') as mock_gen_name:
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                mock_gen_name.return_value = "generated_agent"
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=await state_manager
                )
                
                mock_gen_name.assert_called_once()
                assert agent.username == "generated_agent"

    @pytest.mark.asyncio
    async def test_should_create_workflow_with_correct_nodes(self, mock_browser_context, state_manager):
        """Test that the LangGraph workflow is created with required nodes."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.StateGraph') as mock_state_graph:
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                mock_workflow = Mock()
                mock_state_graph.return_value = mock_workflow
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=await state_manager,
                    enable_summarization=True
                )
                
                mock_workflow.add_node.assert_any_call("agent", agent.call_agent)
                mock_workflow.set_entry_point.assert_called_with("agent")

    @pytest.mark.asyncio
    async def test_should_handle_tool_calls_in_agent_node(self, kage_agent, sample_state):
        """Test that the agent node properly handles tool calls."""
        agent = await kage_agent
        mock_message = AIMessage(
            content="I'll click the button",
            tool_calls=[{"name": "click", "args": {"selector": "[data-ai-label='1']"}}]
        )
        
        with patch.object(agent.llm_with_tools, 'ainvoke', return_value=mock_message):
            result = await agent.call_agent(sample_state)
            
            assert "messages" in result
            assert len(result["messages"]) > 0

    @pytest.mark.asyncio
    async def test_should_configure_llm_models_correctly(self, mock_browser_context, state_manager):
        """Test that LLM models are configured with correct parameters."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=await state_manager
            )
            
            assert mock_init.call_count == 2  # Main LLM and summarizer LLM
            assert agent.llm == mock_llm
            assert agent.summarizer_llm == mock_llm


    def test_should_track_instance_count(self, mock_browser_context, state_manager):
        """Test that agent instances are tracked for concurrency limits."""
        initial_count = KageBunshinAgent._INSTANCE_COUNT
        
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=state_manager
            )
            
            assert isinstance(agent, KageBunshinAgent)

    @pytest.mark.asyncio
    async def test_should_process_user_input_through_workflow(self, kage_agent, sample_state):
        """Test that user input is processed through the LangGraph workflow."""
        with patch.object(kage_agent, 'workflow') as mock_workflow:
            mock_workflow.ainvoke = AsyncMock(return_value=sample_state)
            
            result = await kage_agent.run(sample_state)
            
            mock_workflow.ainvoke.assert_called_once_with(sample_state)
            assert result == sample_state

    @pytest.mark.asyncio
    async def test_should_maintain_persistent_message_history(self, kage_agent):
        """Test that agent maintains message history across turns."""
        initial_message = HumanMessage(content="Hello")
        kage_agent.persistent_messages.append(initial_message)
        
        assert len(kage_agent.persistent_messages) == 1
        assert kage_agent.persistent_messages[0] == initial_message
        
        new_message = AIMessage(content="Hi there!")
        kage_agent.persistent_messages.append(new_message)
        
        assert len(kage_agent.persistent_messages) == 2
        assert kage_agent.persistent_messages[1] == new_message

    def test_should_setup_group_chat_client(self, mock_browser_context, state_manager):
        """Test that group chat client is properly initialized."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.GroupChatClient') as mock_group_chat:
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=state_manager,
                    group_room="test_room"
                )
                
                mock_group_chat.assert_called_once()
                assert agent.group_room == "test_room"

    def test_should_generate_username_when_not_provided(self, mock_browser_context, state_manager):
        """Test that agent generates a username when none is provided."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.generate_agent_name') as mock_gen_name:
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                mock_gen_name.return_value = "generated_agent"
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=state_manager
                )
                
                mock_gen_name.assert_called_once()
                assert agent.username == "generated_agent"

    def test_should_create_workflow_with_correct_nodes(self, mock_browser_context, state_manager):
        """Test that the LangGraph workflow is created with required nodes."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.StateGraph') as mock_state_graph:
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                mock_workflow = Mock()
                mock_state_graph.return_value = mock_workflow
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=state_manager,
                    enable_summarization=True
                )
                
                mock_workflow.add_node.assert_any_call("agent", agent.call_agent)
                mock_workflow.set_entry_point.assert_called_with("agent")

    @pytest.mark.asyncio
    async def test_should_handle_tool_calls_in_agent_node(self, kage_agent, sample_state):
        """Test that the agent node properly handles tool calls."""
        mock_message = AIMessage(
            content="I'll click the button",
            tool_calls=[{"name": "click", "args": {"selector": "[data-ai-label='1']"}}]
        )
        
        with patch.object(kage_agent.llm_with_tools, 'ainvoke', return_value=mock_message):
            result = await kage_agent.call_agent(sample_state)
            
            assert "messages" in result
            assert len(result["messages"]) > 0

    def test_should_configure_llm_models_correctly(self, mock_browser_context, state_manager):
        """Test that LLM models are configured with correct parameters."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            mock_llm.bind_tools.return_value = mock_llm
            
            agent = KageBunshinAgent(
                context=mock_browser_context,
                state_manager=state_manager
            )
            
            assert mock_init.call_count == 2  # Main LLM and summarizer LLM
            assert agent.llm == mock_llm
            assert agent.summarizer_llm == mock_llm