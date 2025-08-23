"""
Unit tests for delegation system.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from kagebunshin.tools.delegation import _summarize_conversation_history, get_additional_tools
from kagebunshin.core.state import KageBunshinState


class TestSummarizeConversationHistory:
    """Test suite for conversation history summarization."""
    
    @pytest.mark.asyncio
    async def test_should_return_no_history_message_when_empty(self):
        """Test summarization with empty message list."""
        result = await _summarize_conversation_history([], "test_parent")
        
        assert result == "No prior conversation history."

    @pytest.mark.asyncio
    async def test_should_capture_initial_user_request(self):
        """Test that initial user request is captured in summary."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Search for Python tutorials"),
            AIMessage(content="I'll help you search")
        ]
        
        result = await _summarize_conversation_history(messages, "test_parent")
        
        assert "Initial request: Search for Python tutorials" in result

    @pytest.mark.asyncio
    async def test_should_skip_system_messages(self):
        """Test that system messages are skipped in summarization."""
        messages = [
            SystemMessage(content="Long system prompt that should be ignored"),
            HumanMessage(content="User request"),
            AIMessage(content="AI response")
        ]
        
        result = await _summarize_conversation_history(messages, "test_parent")
        
        assert "Long system prompt" not in result
        assert "User request" in result

    @pytest.mark.asyncio
    async def test_should_format_tool_calls_in_summary(self):
        """Test that AI tool calls are properly formatted."""
        ai_message = AIMessage(
            content="I'll click the button",
            tool_calls=[
                {"name": "click", "args": {"selector": "[data-ai-label='1']"}},
                {"name": "goto_url", "args": {"url": "https://example.com"}}
            ]
        )
        messages = [HumanMessage(content="Click something"), ai_message]
        
        result = await _summarize_conversation_history(messages, "test_parent")
        
        assert "AI called: click" in result
        assert "goto_url" in result

    @pytest.mark.asyncio
    async def test_should_handle_tool_messages(self):
        """Test that tool result messages are included."""
        messages = [
            HumanMessage(content="Navigate to site"),
            ToolMessage(content="Navigation successful", tool_call_id="123")
        ]
        
        result = await _summarize_conversation_history(messages, "test_parent")
        
        assert "Tool result: Navigation successful" in result

    @pytest.mark.asyncio
    async def test_should_limit_message_history(self):
        """Test that only recent messages are processed."""
        # Create more than 200 messages
        messages = [HumanMessage(content=f"Message {i}") for i in range(250)]
        
        result = await _summarize_conversation_history(messages, "test_parent")
        
        # Should only process last 200 messages
        assert "Message 49" not in result  # Early messages excluded
        assert "Message 249" in result  # Recent messages included

    @pytest.mark.asyncio
    async def test_should_shorten_long_text_content(self):
        """Test that long text content is truncated."""
        long_content = "x" * 500  # Longer than max_len
        messages = [HumanMessage(content=long_content)]
        
        result = await _summarize_conversation_history(messages, "test_parent")
        
        assert len(result) < len(long_content)
        assert "..." in result

    @pytest.mark.asyncio
    async def test_should_handle_malformed_tool_calls(self):
        """Test graceful handling of malformed tool calls."""
        ai_message = AIMessage(
            content="Response",
            tool_calls=[
                {"name": "click"},  # Missing args
                {"invalid": "structure"}  # Invalid structure
            ]
        )
        messages = [ai_message]
        
        result = await _summarize_conversation_history(messages, "test_parent")
        
        # Should not crash and should include some information
        assert "AI called:" in result or "AI:" in result


class TestGetAdditionalTools:
    """Test suite for the get_additional_tools function."""
    
    def test_should_create_tools_with_browser_context(self, mock_browser_context):
        """Test that additional tools are created with browser context."""
        tools = get_additional_tools(mock_browser_context)
        
        assert isinstance(tools, list)
        assert len(tools) > 0
        
        # Should contain delegate and post_groupchat tools
        tool_names = [tool.name for tool in tools]
        assert "delegate" in tool_names
        assert "post_groupchat" in tool_names

    def test_should_accept_optional_parameters(self, mock_browser_context):
        """Test that get_additional_tools accepts optional parameters."""
        tools = get_additional_tools(
            mock_browser_context, 
            username="test_user",
            group_room="test_room"
        )
        
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_should_create_different_tool_instances(self, mock_browser_context):
        """Test that multiple calls create separate tool instances."""
        tools1 = get_additional_tools(mock_browser_context)
        tools2 = get_additional_tools(mock_browser_context)
        
        # Should be separate instances
        assert tools1 is not tools2
        assert len(tools1) == len(tools2)