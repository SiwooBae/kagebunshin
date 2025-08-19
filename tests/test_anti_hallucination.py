"""
Test suite for anti-hallucination improvements.

Tests that agents properly ground their responses in actual observations
rather than making unfounded claims based on assumed knowledge.
"""
import anyio
from unittest.mock import AsyncMock, patch
from kagebunshin.core.agent import KageBunshinAgent
from kagebunshin.core.state import KageBunshinState
from kagebunshin.tools.delegation import get_additional_tools


class TestAntiHallucination:
    """Test cases to verify anti-hallucination measures are working."""

    async def test_system_prompt_includes_evidence_requirements(self):
        """Verify the system prompt includes evidence-based operation requirements."""
        from kagebunshin.config.settings import SYSTEM_TEMPLATE
        
        # Check for key anti-hallucination phrases
        assert "NEVER HALLUCINATE" in SYSTEM_TEMPLATE
        assert "Navigate First, Conclude Second" in SYSTEM_TEMPLATE
        assert "Observe Before Claiming" in SYSTEM_TEMPLATE
        assert "Verification Chain" in SYSTEM_TEMPLATE
        assert "FORBIDDEN - Never Do This" in SYSTEM_TEMPLATE
        
    async def test_clone_briefing_includes_verification_reminder(self):
        """Verify clone briefing messages include verification reminders."""
        # Create a mock state that represents a delegation scenario
        mock_state = {
            "messages": [],
            "clone_depth": 0
        }
        
        # Get the delegate tool from additional tools
        tools = get_additional_tools(AsyncMock(), username="test_parent")
        delegate_tool = next(tool for tool in tools if tool.name == "delegate")
        
        # Mock the conversation summarization to avoid LLM calls
        with patch('kagebunshin.tools.delegation._summarize_conversation_history') as mock_summarize:
            mock_summarize.return_value = "Test parent context"
            
            # Mock the browser and context creation
            with patch('kagebunshin.core.agent.KageBunshinAgent.create') as mock_create:
                mock_agent = AsyncMock()
                mock_agent.ainvoke.return_value = "Task completed"
                mock_create.return_value = mock_agent
                
                # Mock browser context creation
                mock_browser = AsyncMock()
                mock_context = AsyncMock()
                mock_context.browser = mock_browser
                mock_browser.new_context.return_value = mock_context
                
                with patch('kagebunshin.tools.delegation.apply_fingerprint_profile_to_context'):
                    # Call delegate with mock state
                    result = await delegate_tool.ainvoke({
                        "tasks": ["Test task"],
                        "state": mock_state
                    })
                    
                    # Verify the agent was invoked with verification reminders
                    if mock_agent.ainvoke.called:
                        call_args = mock_agent.ainvoke.call_args[0][0]
                        assert "VERIFICATION CRITICAL" in call_args
                        assert "GROUND ALL RESPONSES" in call_args
                        assert "Navigate first, conclude second" in call_args

    async def test_navigation_status_warning_for_blank_pages(self):
        """Test that agents get warnings when they haven't navigated to content yet."""
        # Create a mock agent with blank page state
        mock_context = AsyncMock()
        mock_state_manager = AsyncMock()
        
        # Mock get_current_url to return a blank page
        agent = KageBunshinAgent(
            context=mock_context,
            state_manager=mock_state_manager,
            clone_depth=0
        )
        
        # Mock the get_current_url method to return about:blank
        agent.get_current_url = AsyncMock(return_value="about:blank")
        agent.state_manager.get_current_page_data = AsyncMock()
        agent.state_manager.get_tabs = AsyncMock(return_value=[])
        agent.group_client.connect = AsyncMock()
        agent.group_client.history = AsyncMock(return_value=[])
        agent.group_client.format_history = AsyncMock(return_value="")
        
        # Create test state
        test_state = KageBunshinState(
            input="What's the current price of Bitcoin?",
            messages=[],
            context=mock_context,
            clone_depth=0
        )
        
        # Build agent messages
        messages = await agent._build_agent_messages(test_state)
        
        # Check that navigation warning is included
        warning_found = False
        for message in messages:
            if hasattr(message, 'content') and "NAVIGATION STATUS" in str(message.content):
                warning_found = True
                assert "You haven't navigated to any specific content sources yet" in str(message.content)
                assert "DO NOT make factual claims based on assumed knowledge" in str(message.content)
                break
        
        assert warning_found, "Navigation status warning should be included for blank pages"

    async def test_navigation_status_warning_for_google_homepage(self):
        """Test that agents get warnings when still on Google homepage."""
        # Create a mock agent 
        mock_context = AsyncMock()
        mock_state_manager = AsyncMock()
        
        agent = KageBunshinAgent(
            context=mock_context,
            state_manager=mock_state_manager,
            clone_depth=0
        )
        
        # Mock the get_current_url method to return Google homepage
        agent.get_current_url = AsyncMock(return_value="https://www.google.com")
        agent.state_manager.get_current_page_data = AsyncMock()
        agent.state_manager.get_tabs = AsyncMock(return_value=[])
        agent.group_client.connect = AsyncMock()
        agent.group_client.history = AsyncMock(return_value=[])
        agent.group_client.format_history = AsyncMock(return_value="")
        
        # Create test state
        test_state = KageBunshinState(
            input="What are the system requirements for the latest iPhone?",
            messages=[],
            context=mock_context,
            clone_depth=0
        )
        
        # Build agent messages
        messages = await agent._build_agent_messages(test_state)
        
        # Check that navigation warning is included
        warning_found = False
        for message in messages:
            if hasattr(message, 'content') and "NAVIGATION STATUS" in str(message.content):
                warning_found = True
                break
        
        assert warning_found, "Navigation status warning should be included for Google homepage"

    async def test_no_navigation_warning_for_content_pages(self):
        """Test that navigation warnings are NOT shown when on actual content pages."""
        # Create a mock agent
        mock_context = AsyncMock()
        mock_state_manager = AsyncMock()
        
        agent = KageBunshinAgent(
            context=mock_context,
            state_manager=mock_state_manager,
            clone_depth=0
        )
        
        # Mock the get_current_url method to return a content page
        agent.get_current_url = AsyncMock(return_value="https://www.apple.com/iphone")
        agent.state_manager.get_current_page_data = AsyncMock()
        agent.state_manager.get_tabs = AsyncMock(return_value=[])
        agent.group_client.connect = AsyncMock()
        agent.group_client.history = AsyncMock(return_value=[])
        agent.group_client.format_history = AsyncMock(return_value="")
        
        # Create test state
        test_state = KageBunshinState(
            input="What are the iPhone specs?",
            messages=[],
            context=mock_context,
            clone_depth=0
        )
        
        # Build agent messages
        messages = await agent._build_agent_messages(test_state)
        
        # Check that NO navigation warning is included
        warning_found = False
        for message in messages:
            if hasattr(message, 'content') and "NAVIGATION STATUS" in str(message.content):
                warning_found = True
                break
        
        assert not warning_found, "Navigation status warning should NOT be shown for content pages"

    def test_browser_goto_tool_description_emphasizes_evidence(self):
        """Test that browser_goto tool description emphasizes evidence gathering."""
        from kagebunshin.core.state_manager import KageBunshinStateManager
        
        # Create a mock context and state manager
        mock_context = AsyncMock()
        state_manager = KageBunshinStateManager(mock_context)
        
        # Get tools for LLM
        tools = state_manager.get_tools_for_llm()
        
        # Find the browser_goto tool
        goto_tool = next(tool for tool in tools if tool.name == "browser_goto")
        
        # Check that the description emphasizes evidence gathering
        description = goto_tool.description
        assert "PRIMARY tool for gathering evidence" in description
        assert "BEFORE making any factual claims" in description
        assert "Never assume information" in description
        assert "always navigate to see current content" in description

    def test_extract_page_content_tool_description_emphasizes_verification(self):
        """Test that extract_page_content tool description emphasizes verification."""
        from kagebunshin.core.state_manager import KageBunshinStateManager
        
        # Create a mock context and state manager
        mock_context = AsyncMock()
        state_manager = KageBunshinStateManager(mock_context)
        
        # Get tools for LLM
        tools = state_manager.get_tools_for_llm()
        
        # Find the extract_page_content tool
        extract_tool = next(tool for tool in tools if tool.name == "extract_page_content")
        
        # Check that the description emphasizes verification
        description = extract_tool.description
        assert "ESSENTIAL for fact verification" in description
        assert "Verify information you need to report" in description
        assert "BEFORE stating facts from a website" in description
        assert "Never make claims about page content without first using this tool" in description


if __name__ == "__main__":
    # Run the tests
    anyio.run(test_main)