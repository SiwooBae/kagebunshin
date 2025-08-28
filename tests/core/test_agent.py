"""
Unit tests for KageBunshinAgent.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from kagebunshin.core.agent import KageBunshinAgent

class TestKageBunshinAgent:
    """Test suite for KageBunshinAgent initialization and core functionality."""
    
    def test_should_initialize_with_default_parameters(self, mock_browser_context, state_manager):
        """Test agent initialization with default settings."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.GroupChatClient'):
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
            with patch('kagebunshin.core.agent.GroupChatClient'):
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
            with patch('kagebunshin.core.agent.GroupChatClient'):
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=state_manager
                )
                
                mock_llm.bind_tools.assert_called_once()
                assert agent.llm_with_tools == mock_llm

    def test_should_track_instance_count(self, mock_browser_context, state_manager):
        """Test that agent instances are tracked for concurrency limits."""
        initial_count = KageBunshinAgent._INSTANCE_COUNT
        
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.GroupChatClient'):
                mock_llm = Mock()
                mock_init.return_value = mock_llm
                mock_llm.bind_tools.return_value = mock_llm
                
                agent = KageBunshinAgent(
                    context=mock_browser_context,
                    state_manager=state_manager
                )
                
                assert isinstance(agent, KageBunshinAgent)

    @pytest.mark.asyncio
    async def test_should_process_user_input_through_astream(self, kage_agent):
        """Test that user input is processed through astream method."""
        # Create a proper async generator mock
        async def mock_astream_generator(state, stream_mode=None, config=None):
            yield {"agent": {"messages": [AIMessage(content="Test response")]}}
            
        with patch.object(kage_agent, 'agent') as mock_agent:
            mock_agent.astream = mock_astream_generator
            
            result_chunks = []
            async for chunk in kage_agent.astream("test input"):
                result_chunks.append(chunk)
            
            assert len(result_chunks) > 0

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
            with patch('kagebunshin.core.agent.GroupChatClient'):
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
            with patch('kagebunshin.core.agent.GroupChatClient'):
                with patch('kagebunshin.core.agent.StateGraph') as mock_state_graph:
                    mock_llm = Mock()
                    mock_init.return_value = mock_llm
                    mock_llm.bind_tools.return_value = mock_llm
                    mock_workflow = Mock()
                    mock_state_graph.return_value = mock_workflow
                    mock_compiled = Mock()
                    mock_workflow.compile.return_value = mock_compiled
                    
                    agent = KageBunshinAgent(
                        context=mock_browser_context,
                        state_manager=state_manager,
                        enable_summarization=True
                    )
                    
                    mock_workflow.add_node.assert_any_call("agent", agent.call_agent)
                    mock_workflow.set_entry_point.assert_called_with("agent")
                    assert agent.agent == mock_compiled

    @pytest.mark.asyncio
    async def test_should_handle_call_agent_method(self, kage_agent, sample_state):
        """Test that the call_agent method works correctly."""
        mock_message = AIMessage(
            content="I'll help you with that",
            tool_calls=[]
        )
        
        # Mock the async ainvoke method properly
        with patch.object(kage_agent.llm_with_tools, 'ainvoke', new_callable=AsyncMock) as mock_ainvoke:
            mock_ainvoke.return_value = mock_message
            
            result = await kage_agent.call_agent(sample_state)
            
            assert "messages" in result
            assert len(result["messages"]) > 0
            mock_ainvoke.assert_called_once()

    def test_should_configure_llm_models_correctly(self, mock_browser_context, state_manager):
        """Test that LLM models are configured with correct parameters."""
        with patch('kagebunshin.core.agent.init_chat_model') as mock_init:
            with patch('kagebunshin.core.agent.GroupChatClient'):
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

    @pytest.mark.asyncio
    async def test_should_dispose_properly(self, kage_agent):
        """Test that agent disposes resources properly."""
        initial_count = KageBunshinAgent._INSTANCE_COUNT
        
        # Dispose should not raise an exception
        kage_agent.dispose()
        
        # Should be able to call dispose multiple times
        kage_agent.dispose()

    @pytest.mark.asyncio
    async def test_should_get_current_url(self, kage_agent):
        """Test getting current URL from active page."""
        with patch.object(kage_agent.state_manager, 'current_state') as mock_state:
            mock_state.__getitem__.return_value.pages = [Mock()]
            mock_state.__getitem__.return_value.pages[0].url = "https://test.com"
            
            url = await kage_agent.get_current_url()
            
            assert url == "https://test.com"

    @pytest.mark.asyncio  
    async def test_should_get_current_title(self, kage_agent):
        """Test getting current title from active page."""
        with patch.object(kage_agent.state_manager, 'current_state') as mock_state:
            mock_page = AsyncMock()
            mock_page.title.return_value = "Test Title"
            mock_state.__getitem__.return_value.pages = [mock_page]
            
            title = await kage_agent.get_current_title()
            
            assert title == "Test Title"

    def test_should_get_action_count(self, kage_agent):
        """Test getting action count from state manager."""
        kage_agent.state_manager._action_count = 5
        
        count = kage_agent.get_action_count()
        
        assert count == 5


class TestAgentTermination:
    """Test suite for the new termination logic with complete_task tool."""
    
    def test_should_continue_returns_end_when_complete_task_called(self, kage_agent):
        """Test that should_continue returns 'end' when complete_task tool is called."""
        from kagebunshin.core.state import KageBunshinState
        from langchain_core.messages import AIMessage, ToolCall
        
        # Mock AI message with complete_task tool call
        tool_call = ToolCall(name="complete_task", args={"status": "success", "result": "Task done"}, id="test_call_1")
        ai_message = AIMessage(content="", tool_calls=[tool_call])
        
        state = {
            "messages": [ai_message],
            "tool_call_retry_count": 0
        }
        
        result = kage_agent.should_continue(state)
        
        assert result == "end"
    
    def test_should_continue_returns_continue_for_other_tool_calls(self, kage_agent):
        """Test that should_continue returns 'continue' for non-complete_task tool calls."""
        from langchain_core.messages import AIMessage, ToolCall
        
        # Mock AI message with regular tool call
        tool_call = ToolCall(name="click", args={"bbox_id": 1}, id="test_call_2")
        ai_message = AIMessage(content="", tool_calls=[tool_call])
        
        state = {
            "messages": [ai_message],
            "tool_call_retry_count": 1
        }
        
        result = kage_agent.should_continue(state)
        
        assert result == "continue"
        # Should reset retry count when tool call is made
        assert state["tool_call_retry_count"] == 0
    
    def test_should_continue_adds_reminder_on_missing_tool_call(self, kage_agent):
        """Test that should_continue adds reminder message when no tool call is made."""
        from langchain_core.messages import AIMessage, SystemMessage
        
        # Mock AI message without tool calls
        ai_message = AIMessage(content="I'm thinking about this task...")
        
        state = {
            "messages": [ai_message],
            "tool_call_retry_count": 0
        }
        
        result = kage_agent.should_continue(state)
        
        assert result == "continue"
        assert state["tool_call_retry_count"] == 1
        
        # Check that reminder message was added
        assert len(state["messages"]) == 2
        reminder_msg = state["messages"][1]
        assert isinstance(reminder_msg, SystemMessage)
        assert "Tool Call Required" in reminder_msg.content
        assert "complete_task" in reminder_msg.content
    
    def test_should_continue_terminates_after_max_retries(self, kage_agent):
        """Test that should_continue returns 'end' after reaching max retry limit."""
        from langchain_core.messages import AIMessage
        
        # Mock AI message without tool calls
        ai_message = AIMessage(content="I'm still thinking...")
        
        state = {
            "messages": [ai_message],
            "tool_call_retry_count": 2  # At max retries
        }
        
        result = kage_agent.should_continue(state)
        
        assert result == "end"
    
    def test_extract_final_answer_handles_complete_task_tool_calls(self, kage_agent):
        """Test _extract_final_answer extracts data from complete_task tool calls."""
        from langchain_core.messages import AIMessage, ToolCall
        
        # Mock complete_task tool call
        tool_call = ToolCall(
            name="complete_task", 
            args={
                "status": "success", 
                "result": "Found 3 Python frameworks", 
                "confidence": 0.9
            },
            id="test_call_3"
        )
        ai_message = AIMessage(content="", tool_calls=[tool_call])
        
        # Mock state manager with messages
        kage_agent.state_manager.current_state = {"messages": [ai_message]}
        
        result = kage_agent._extract_final_answer()
        
        assert result == "[SUCCESS] (confidence: 90%) Found 3 Python frameworks"
    
    def test_extract_final_answer_handles_complete_task_without_confidence(self, kage_agent):
        """Test _extract_final_answer handles complete_task without confidence score."""
        from langchain_core.messages import AIMessage, ToolCall
        
        # Mock complete_task tool call without confidence
        tool_call = ToolCall(
            name="complete_task", 
            args={
                "status": "partial", 
                "result": "Collected data from 2 of 3 sites"
            },
            id="test_call_4"
        )
        ai_message = AIMessage(content="", tool_calls=[tool_call])
        
        # Mock state manager with messages
        kage_agent.state_manager.current_state = {"messages": [ai_message]}
        
        result = kage_agent._extract_final_answer()
        
        assert result == "[PARTIAL] Collected data from 2 of 3 sites"
    
    def test_extract_final_answer_falls_back_to_state_manager_data(self, kage_agent):
        """Test _extract_final_answer uses state manager completion data as fallback."""
        from langchain_core.messages import HumanMessage
        
        # Mock state with no complete_task tool calls
        kage_agent.state_manager.current_state = {"messages": [HumanMessage(content="test")]}
        
        # Mock completion data in state manager
        kage_agent.state_manager.completion_data = {
            "status": "blocked",
            "result": "Authentication required",
            "confidence": 1.0
        }
        
        result = kage_agent._extract_final_answer()
        
        assert result == "[BLOCKED] (confidence: 100%) Authentication required"
    
    def test_extract_final_answer_supports_legacy_markers(self, kage_agent):
        """Test _extract_final_answer still supports legacy [FINAL ANSWER] markers."""
        from langchain_core.messages import AIMessage
        
        # Mock AI message with legacy marker
        ai_message = AIMessage(content="[FINAL ANSWER] Task completed successfully")
        
        # Mock state manager with messages
        kage_agent.state_manager.current_state = {"messages": [ai_message]}
        
        result = kage_agent._extract_final_answer()
        
        assert result == "Task completed successfully"
    
    def test_extract_final_answer_supports_legacy_final_message_marker(self, kage_agent):
        """Test _extract_final_answer supports legacy [FINAL MESSAGE] markers."""
        from langchain_core.messages import AIMessage
        
        # Mock AI message with legacy marker
        ai_message = AIMessage(content="[FINAL MESSAGE] Mission accomplished")
        
        # Mock state manager with messages
        kage_agent.state_manager.current_state = {"messages": [ai_message]}
        
        result = kage_agent._extract_final_answer()
        
        assert result == "Mission accomplished"
    
    def test_extract_final_answer_returns_default_when_no_content(self, kage_agent):
        """Test _extract_final_answer returns default message when no suitable content found."""
        from langchain_core.messages import HumanMessage
        
        # Mock state with only human messages (no AI responses)
        kage_agent.state_manager.current_state = {"messages": [HumanMessage(content="test")]}
        
        result = kage_agent._extract_final_answer()
        
        assert result == "Task completed, but no specific answer was provided."