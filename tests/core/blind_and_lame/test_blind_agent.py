"""
Tests for BlindAgent - The agent with reasoning but no direct page access.

Tests cover:
- Agent initialization and LangGraph workflow setup
- Reasoning and planning through act() tool
- Task completion detection and workflow management
- Streaming capabilities
- Integration with LameAgent
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path

from kagebunshin.core.blind_and_lame.blind_agent import BlindAgent, BlindAgentState
from kagebunshin.core.blind_and_lame.lame_agent import LameAgent
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool


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


class TestBlindAgentWorkflow:
    """Test LangGraph workflow execution and routing."""
    
    @pytest.fixture
    def blind_agent_with_mocks(self, mock_lame_agent):
        """Create BlindAgent with mocked LLM for testing."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model') as mock_init_llm:
            mock_llm = Mock()
            mock_llm.bind_tools.return_value = Mock()
            mock_init_llm.return_value = mock_llm
            
            blind_agent = BlindAgent(mock_lame_agent)
            
            # Mock the LLM with tools for testing
            blind_agent.llm_with_tools = AsyncMock()
            
            return blind_agent
    
    @pytest.mark.asyncio
    async def test_call_agent_should_format_messages_correctly(self, blind_agent_with_mocks):
        """Test that call_agent formats messages with system prompt and conversation history."""
        mock_response = AIMessage(content="I need to navigate to the website first.")
        blind_agent_with_mocks.llm_with_tools.ainvoke.return_value = mock_response
        
        test_state = BlindAgentState(
            input="Find information about transformers",
            messages=[HumanMessage(content="Find information about transformers")],
            task_completed=False
        )
        
        result = await blind_agent_with_mocks.call_agent(test_state)
        
        # Verify LLM was called with system prompt and user message
        call_args = blind_agent_with_mocks.llm_with_tools.ainvoke.call_args[0][0]
        assert len(call_args) == 2  # System message + user message
        assert isinstance(call_args[0], SystemMessage)
        assert "blind agent" in call_args[0].content.lower()
        assert isinstance(call_args[1], HumanMessage)
        assert "transformers" in call_args[1].content.lower()
        
        # Verify return format
        assert result == {"messages": [mock_response]}
    
    def test_should_continue_with_tool_calls(self, blind_agent_with_mocks):
        """Test routing when AI message has tool calls."""
        test_state = BlindAgentState(
            input="test",
            messages=[
                HumanMessage(content="test"),
                AIMessage(content="", tool_calls=[{"id": "1", "name": "act", "args": {"command": "test"}}])
            ],
            task_completed=False
        )
        
        result = blind_agent_with_mocks.should_continue(test_state)
        
        assert result == "action"
    
    def test_should_end_without_tool_calls(self, blind_agent_with_mocks):
        """Test routing when AI message has no tool calls."""
        test_state = BlindAgentState(
            input="test",
            messages=[
                HumanMessage(content="test"),
                AIMessage(content="I have completed the task successfully.")
            ],
            task_completed=False
        )
        
        result = blind_agent_with_mocks.should_continue(test_state)
        
        assert result == "end"
    
    @pytest.mark.asyncio
    async def test_task_completion_check_should_detect_completion_indicators(self, blind_agent_with_mocks):
        """Test task completion detection based on message content."""
        test_state = BlindAgentState(
            input="test task",
            messages=[
                HumanMessage(content="test task"),
                AIMessage(content="I have successfully completed the task. All requirements have been fulfilled.")
            ],
            task_completed=False
        )
        
        result = await blind_agent_with_mocks.check_task_completion(test_state)
        
        assert result == {"task_completed": True}
    
    @pytest.mark.asyncio
    async def test_task_completion_check_should_not_detect_ongoing_work(self, blind_agent_with_mocks):
        """Test that ongoing work is not detected as completion."""
        test_state = BlindAgentState(
            input="test task",
            messages=[
                HumanMessage(content="test task"),
                AIMessage(content="I am currently working on the task. Let me navigate to the next page.")
            ],
            task_completed=False
        )
        
        result = await blind_agent_with_mocks.check_task_completion(test_state)
        
        assert result == {"task_completed": False}
    
    def test_route_after_action_should_end_when_task_completed(self, blind_agent_with_mocks):
        """Test routing to end when task is marked as completed."""
        test_state = BlindAgentState(
            input="test",
            messages=[],
            task_completed=True
        )
        
        result = blind_agent_with_mocks.route_after_action(test_state)
        
        assert result == "end"
    
    def test_route_after_action_should_continue_when_task_not_completed(self, blind_agent_with_mocks):
        """Test routing back to agent when task is not completed."""
        test_state = BlindAgentState(
            input="test",
            messages=[],
            task_completed=False
        )
        
        result = blind_agent_with_mocks.route_after_action(test_state)
        
        assert result == "agent"


class TestBlindAgentExecution:
    """Test main execution methods (ainvoke and astream)."""
    
    @pytest.fixture
    def blind_agent_with_workflow_mock(self, mock_lame_agent):
        """Create BlindAgent with mocked workflow for execution testing."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame_agent)
            
            # Mock the compiled workflow
            blind_agent.agent = AsyncMock()
            
            return blind_agent
    
    @pytest.mark.asyncio
    async def test_ainvoke_should_process_query_and_return_final_answer(self, blind_agent_with_workflow_mock):
        """Test successful query processing through ainvoke."""
        # Mock workflow execution result
        final_state = BlindAgentState(
            input="Search for Python tutorials",
            messages=[
                HumanMessage(content="Search for Python tutorials"),
                AIMessage(content="I found several excellent Python tutorials on the website.", 
                         tool_calls=[{"id": "1", "name": "act", "args": {"command": "search"}}]),
                ToolMessage(content="Search results displayed", tool_call_id="1"),
                AIMessage(content="Task completed successfully. I have found Python tutorials for you.")
            ],
            task_completed=True
        )
        
        blind_agent_with_workflow_mock.agent.ainvoke.return_value = final_state
        
        result = await blind_agent_with_workflow_mock.ainvoke("Search for Python tutorials")
        
        assert "task completed successfully" in result.lower()
        assert "python tutorials" in result.lower()
        
        # Verify workflow was called with proper initial state
        call_args = blind_agent_with_workflow_mock.agent.ainvoke.call_args[0][0]
        assert call_args["input"] == "Search for Python tutorials"
        assert len(call_args["messages"]) == 1
        assert isinstance(call_args["messages"][0], HumanMessage)
        assert call_args["task_completed"] is False
    
    @pytest.mark.asyncio
    async def test_ainvoke_should_handle_workflow_errors_gracefully(self, blind_agent_with_workflow_mock):
        """Test error handling during workflow execution."""
        blind_agent_with_workflow_mock.agent.ainvoke.side_effect = Exception("Workflow error")
        
        result = await blind_agent_with_workflow_mock.ainvoke("Do something")
        
        assert "error processing request" in result.lower()
        assert "workflow error" in result.lower()
    
    @pytest.mark.asyncio
    async def test_astream_should_yield_workflow_updates(self, blind_agent_with_workflow_mock):
        """Test streaming execution yields intermediate results."""
        # Mock streaming workflow results
        mock_chunks = [
            {"agent": {"messages": [AIMessage(content="Planning the task...")]}},
            {"action": {"messages": [ToolMessage(content="Navigated to website", tool_call_id="1")]}},
            {"agent": {"messages": [AIMessage(content="Task completed")]}}
        ]
        
        async def mock_astream(*args, **kwargs):
            for chunk in mock_chunks:
                yield chunk
        
        blind_agent_with_workflow_mock.agent.astream = mock_astream
        
        chunks = []
        async for chunk in blind_agent_with_workflow_mock.astream("Test query"):
            chunks.append(chunk)
        
        assert len(chunks) == 3
        assert "agent" in chunks[0]
        assert "action" in chunks[1]
        assert "planning the task" in chunks[0]["agent"]["messages"][0].content.lower()
    
    @pytest.mark.asyncio
    async def test_astream_should_handle_streaming_errors(self, blind_agent_with_workflow_mock):
        """Test error handling during streaming execution."""
        async def mock_astream_error(*args, **kwargs):
            raise Exception("Streaming error")
            yield  # Unreachable but makes it a generator
        
        blind_agent_with_workflow_mock.agent.astream = mock_astream_error
        
        chunks = []
        async for chunk in blind_agent_with_workflow_mock.astream("Test query"):
            chunks.append(chunk)
        
        assert len(chunks) == 1
        assert "error" in chunks[0]
        assert "streaming error" in chunks[0]["error"].lower()


class TestBlindAgentAnswerExtraction:
    """Test final answer extraction from conversation."""
    
    @pytest.fixture
    def blind_agent_for_extraction(self, mock_lame_agent):
        """Create BlindAgent for testing answer extraction."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            return BlindAgent(mock_lame_agent)
    
    def test_should_extract_most_recent_substantial_ai_response(self, blind_agent_for_extraction):
        """Test extraction of the most recent meaningful AI response."""
        final_state = BlindAgentState(
            input="test",
            messages=[
                HumanMessage(content="Do a task"),
                AIMessage(content="I need to start by navigating..."),
                ToolMessage(content="Navigated successfully", tool_call_id="1"),
                AIMessage(content="Perfect! I have successfully completed your request and found the information you needed.")
            ],
            task_completed=True
        )
        
        result = blind_agent_for_extraction._extract_final_answer(final_state)
        
        assert "successfully completed" in result.lower()
        assert "information you needed" in result.lower()
    
    def test_should_skip_planning_messages_in_extraction(self, blind_agent_for_extraction):
        """Test that planning/intermediate messages are skipped in favor of final results."""
        final_state = BlindAgentState(
            input="test",
            messages=[
                HumanMessage(content="Find product prices"),
                AIMessage(content="I need to search for the products first"),
                ToolMessage(content="Search results loaded", tool_call_id="1"),
                AIMessage(content="The product costs $29.99 and is available for immediate shipping.")
            ],
            task_completed=True
        )
        
        result = blind_agent_for_extraction._extract_final_answer(final_state)
        
        assert "$29.99" in result
        assert "available for immediate shipping" in result
        # Should not include the planning message
        assert "need to search" not in result.lower()
    
    def test_should_provide_fallback_when_no_substantial_content(self, blind_agent_for_extraction):
        """Test fallback response when no substantial content is found."""
        final_state = BlindAgentState(
            input="test",
            messages=[
                HumanMessage(content="Do something"),
                AIMessage(content="I need to..."),
                AIMessage(content="")
            ],
            task_completed=True
        )
        
        result = blind_agent_for_extraction._extract_final_answer(final_state)
        
        assert result == "Task completed."


class TestBlindAgentIntegration:
    """Test integration with LameAgent and context retrieval."""
    
    @pytest.mark.asyncio
    async def test_should_retrieve_current_context_from_lame_agent(self, mock_lame_agent):
        """Test context retrieval for debugging/monitoring."""
        mock_lame_agent.get_current_state_description.return_value = "Current page: GitHub homepage with search box and sign-in button"
        
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame_agent)
            
            context = await blind_agent.get_current_context()
            
            assert "github homepage" in context.lower()
            assert "search box" in context.lower()
            mock_lame_agent.get_current_state_description.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_should_handle_context_retrieval_errors(self, mock_lame_agent):
        """Test error handling when context retrieval fails."""
        mock_lame_agent.get_current_state_description.side_effect = Exception("Context error")
        
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame_agent)
            
            context = await blind_agent.get_current_context()
            
            assert "could not get current context" in context.lower()
            assert "context error" in context.lower()
    
    def test_should_dispose_cleanly_including_lame_agent(self, mock_lame_agent):
        """Test that dispose method cleans up both agents."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame_agent)
            
            blind_agent.dispose()
            
            mock_lame_agent.dispose.assert_called_once()


class TestBlindAgentEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_should_handle_empty_messages_in_completion_check(self, mock_lame_agent):
        """Test task completion check with empty message history."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame_agent)
            
            test_state = BlindAgentState(
                input="test",
                messages=[],
                task_completed=False
            )
            
            # Should not crash with empty messages
            result = asyncio.run(blind_agent.check_task_completion(test_state))
            assert result == {"task_completed": False}
    
    def test_should_handle_malformed_messages_gracefully(self, mock_lame_agent):
        """Test handling of malformed or unexpected message types."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame_agent)
            
            # Create state with various message types including empty content
            test_state = BlindAgentState(
                input="test",
                messages=[
                    HumanMessage(content="test"),
                    AIMessage(content=""),  # Empty content instead of None
                    Mock()  # Unexpected message type
                ],
                task_completed=False
            )
            
            # Should not crash, should handle gracefully
            result = blind_agent._extract_final_answer(test_state)
            assert isinstance(result, str)
    
    def test_should_handle_missing_lame_agent_gracefully(self):
        """Test behavior when LameAgent is None or missing."""
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            # BlindAgent requires a LameAgent, so None should raise an error
            with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'get_act_tool_for_blind'"):
                BlindAgent(None)