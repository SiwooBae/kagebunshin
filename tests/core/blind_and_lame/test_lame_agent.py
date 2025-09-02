"""
Tests for LameAgent - The agent with eyes and legs but limited reasoning.

Tests cover:
- Agent initialization and configuration
- Command execution through tool binding
- State change detection and description
- Act tool interface for Blind agent
- Error handling and edge cases
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path

from kagebunshin.core.blind_and_lame.lame_agent import LameAgent
from kagebunshin.core.state import Annotation, BBox, BoundingBox, HierarchyInfo
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool, BaseTool


class TestLameAgentInitialization:
    """Test LameAgent initialization and configuration."""
    
    @pytest.mark.asyncio
    async def test_should_create_lame_agent_successfully(self, mock_browser_context):
        """Test successful LameAgent creation with all components."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model') as mock_init_llm:
                mock_llm = Mock()
                mock_llm.bind_tools.return_value = Mock()
                mock_init_llm.return_value = mock_llm
                
                lame_agent = await LameAgent.create(mock_browser_context)
                
                assert lame_agent.context == mock_browser_context
                assert lame_agent.state_manager == mock_state_manager
                assert lame_agent.llm == mock_llm
                assert lame_agent.browser_tools is not None
                assert lame_agent.llm_with_tools is not None
                assert lame_agent.tool_node is not None
    
    @pytest.mark.asyncio
    async def test_should_load_prompts_from_files(self, mock_browser_context):
        """Test that LameAgent loads prompts from configuration files."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.side_effect = [
                        "System prompt content",
                        "Context template content"
                    ]
                    
                    lame_agent = await LameAgent.create(mock_browser_context)
                    
                    assert lame_agent.system_prompt == "System prompt content"
                    assert lame_agent.context_template == "Context template content"
    
    @pytest.mark.asyncio
    async def test_should_handle_missing_prompt_files_gracefully(self, mock_browser_context):
        """Test fallback behavior when prompt files are missing."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                with patch('builtins.open', side_effect=FileNotFoundError):
                    lame_agent = await LameAgent.create(mock_browser_context)
                    
                    assert "web automation assistant" in lame_agent.system_prompt.lower()
                    assert "{url}" in lame_agent.context_template
                    assert "{command}" in lame_agent.context_template


class TestLameAgentCommandExecution:
    """Test command execution through tool-bound LLM."""
    
    @pytest.fixture
    async def lame_agent_with_mocks(self, mock_browser_context):
        """Create LameAgent with mocked dependencies."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            
            # Mock the page and page data
            mock_page = Mock()
            mock_page.url = "https://example.com"
            mock_page.title = AsyncMock(return_value="Example Page")
            mock_state_manager.get_current_page = Mock(return_value=mock_page)
            
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                # Create sample page data
                sample_bbox = BBox(
                    x=100, y=200, text="Click me", type="button", ariaLabel="Submit button",
                    selector='[data-ai-label="0"]',
                    hierarchy=HierarchyInfo(depth=1, hierarchy=[], siblingIndex=0, totalSiblings=1, 
                                          childrenCount=0, interactiveChildrenCount=0, semanticRole="button"),
                    boundingBox=BoundingBox(left=100, top=200, width=80, height=30),
                    globalIndex=0, isInteractive=True, elementRole="interactive"
                )
                
                sample_annotation = Annotation(
                    img="base64image", 
                    bboxes=[sample_bbox], 
                    markdown="# Example Page\nClick me button",
                    totalElements=1
                )
                
                lame_agent.state_manager.get_current_page_data.return_value = sample_annotation
                
                return lame_agent, mock_state_manager, mock_page, sample_annotation
    
    @pytest.mark.asyncio
    async def test_should_execute_simple_command_successfully(self, lame_agent_with_mocks):
        """Test successful execution of a simple command."""
        lame_agent, mock_state_manager, mock_page, sample_annotation = lame_agent_with_mocks
        
        # Mock LLM response with tool calls
        mock_response = AIMessage(
            content="I'll click the button",
            tool_calls=[{"id": "call1", "name": "click", "args": {"bbox_id": 0}}]
        )
        lame_agent.llm_with_tools.ainvoke = AsyncMock(return_value=mock_response)
        
        # Mock tool execution result
        tool_result_message = ToolMessage(content="Successfully clicked element 0.", tool_call_id="call1")
        lame_agent.tool_node.ainvoke = AsyncMock(return_value={"messages": [tool_result_message]})
        
        result = await lame_agent.execute_command("Click the submit button")
        
        assert "successfully clicked" in result.lower()
        lame_agent.llm_with_tools.ainvoke.assert_called_once()
        lame_agent.tool_node.ainvoke.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_should_handle_command_without_tool_calls(self, lame_agent_with_mocks):
        """Test handling of LLM response without tool calls."""
        lame_agent, mock_state_manager, mock_page, sample_annotation = lame_agent_with_mocks
        
        # Mock LLM response without tool calls
        mock_response = AIMessage(content="I cannot find the element you mentioned.")
        lame_agent.llm_with_tools.ainvoke = AsyncMock(return_value=mock_response)
        
        result = await lame_agent.execute_command("Click the non-existent button")
        
        assert "cannot find the element" in result.lower()
        # Since no tool calls were made, tool_node shouldn't be called
        # Note: tool_node.ainvoke would need to be mocked as AsyncMock if it were called
    
    @pytest.mark.asyncio
    async def test_should_handle_command_execution_errors_gracefully(self, lame_agent_with_mocks):
        """Test error handling during command execution."""
        lame_agent, mock_state_manager, mock_page, sample_annotation = lame_agent_with_mocks
        
        # Mock LLM to raise an exception
        lame_agent.llm_with_tools.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        
        result = await lame_agent.execute_command("Click something")
        
        assert "error executing command" in result.lower()
        assert "llm error" in result.lower()
    
    @pytest.mark.asyncio
    async def test_should_include_page_context_in_llm_request(self, lame_agent_with_mocks):
        """Test that page context is properly included in LLM requests."""
        lame_agent, mock_state_manager, mock_page, sample_annotation = lame_agent_with_mocks
        
        mock_response = AIMessage(content="No action needed")
        lame_agent.llm_with_tools.ainvoke = AsyncMock(return_value=mock_response)
        
        await lame_agent.execute_command("Describe the page")
        
        # Verify LLM was called with proper context
        call_args = lame_agent.llm_with_tools.ainvoke.call_args[0][0]
        
        # Should have system message and human message with context
        assert len(call_args) == 2
        assert isinstance(call_args[0], SystemMessage)
        assert isinstance(call_args[1], HumanMessage)
        
        # Human message should contain page context
        human_message_content = call_args[1].content
        assert "example.com" in human_message_content.lower()
        assert "click me" in human_message_content.lower()
        assert "describe the page" in human_message_content.lower()


class TestLameAgentActTool:
    """Test the act() tool interface for Blind agent."""
    
    @pytest.mark.asyncio
    async def test_should_create_act_tool_successfully(self, mock_browser_context):
        """Test that act tool is created and callable."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                act_tool = lame_agent.get_act_tool_for_blind()
                
                assert act_tool is not None
                assert callable(act_tool)
                assert act_tool.name == "act"
                assert "natural language browser command" in act_tool.description.lower()
    
    @pytest.mark.asyncio
    async def test_act_tool_should_delegate_to_execute_command(self, mock_browser_context):
        """Test that act tool properly delegates to execute_command."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                # Mock execute_command
                lame_agent.execute_command = AsyncMock(return_value="Command executed successfully")
                
                act_tool = lame_agent.get_act_tool_for_blind()
                result = await act_tool.ainvoke({"command": "Click the search button"})
                
                assert result == "Command executed successfully"
                lame_agent.execute_command.assert_called_once_with("Click the search button")


class TestLameAgentStateDescription:
    """Test state description and context building."""
    
    @pytest.mark.asyncio
    async def test_should_generate_current_state_description(self, mock_browser_context):
        """Test generation of current page state description."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                # Mock page and annotation data - set up before assigning to state_manager
                mock_page = Mock()
                mock_page.url = "https://github.com"
                mock_page.title = AsyncMock(return_value="GitHub")
                # Ensure the mock is set up correctly on the state_manager
                lame_agent.state_manager.get_current_page = Mock(return_value=mock_page)
                
                sample_bboxes = [
                    BBox(
                        x=50, y=100, text="Sign in", type="button", ariaLabel="Sign in button",
                        selector='[data-ai-label="0"]',
                        hierarchy=HierarchyInfo(depth=1, hierarchy=[], siblingIndex=0, totalSiblings=2, 
                                              childrenCount=0, interactiveChildrenCount=0, semanticRole="button"),
                        boundingBox=BoundingBox(left=50, top=100, width=60, height=25),
                        globalIndex=0, isInteractive=True, elementRole="interactive"
                    ),
                    BBox(
                        x=150, y=100, text="Search", type="textbox", ariaLabel="Search repositories",
                        selector='[data-ai-label="1"]',
                        hierarchy=HierarchyInfo(depth=1, hierarchy=[], siblingIndex=1, totalSiblings=2, 
                                              childrenCount=0, interactiveChildrenCount=0, semanticRole="textbox"),
                        boundingBox=BoundingBox(left=150, top=100, width=200, height=30),
                        globalIndex=1, isInteractive=True, elementRole="interactive"
                    )
                ]
                
                mock_annotation = Annotation(
                    img="base64image", 
                    bboxes=sample_bboxes, 
                    markdown="# GitHub\nSign in\nSearch repositories",
                    totalElements=2
                )
                lame_agent.state_manager.get_current_page_data.return_value = mock_annotation
                
                description = await lame_agent.get_current_state_description()
                
                assert "github" in description.lower()
                assert "2 interactive elements" in description.lower()
                assert "sign in" in description.lower()
                assert "search" in description.lower()
    
    @pytest.mark.asyncio
    async def test_should_handle_state_description_errors(self, mock_browser_context):
        """Test error handling in state description generation."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                # Make state manager raise an error
                lame_agent.state_manager.get_current_page_data = AsyncMock(side_effect=Exception("Page error"))
                
                description = await lame_agent.get_current_state_description()
                
                assert "error getting current state" in description.lower()
                assert "page error" in description.lower()


class TestLameAgentOutcomeGeneration:
    """Test outcome description generation after command execution."""
    
    @pytest.mark.asyncio
    async def test_should_generate_meaningful_outcome_description(self, mock_browser_context):
        """Test generation of outcome descriptions after actions."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                # Create before and after states
                before_bbox = BBox(
                    x=100, y=200, text="Submit", type="button", ariaLabel="Submit form",
                    selector='[data-ai-label="0"]',
                    hierarchy=HierarchyInfo(depth=1, hierarchy=[], siblingIndex=0, totalSiblings=1, 
                                          childrenCount=0, interactiveChildrenCount=0, semanticRole="button"),
                    boundingBox=BoundingBox(left=100, top=200, width=80, height=30),
                    globalIndex=0, isInteractive=True, elementRole="interactive"
                )
                
                before_state = Annotation(
                    img="before_image", 
                    bboxes=[before_bbox], 
                    markdown="Submit button",
                    totalElements=1
                )
                
                # After state has additional elements (form submitted, results shown)
                # Create additional mock bboxes
                additional_bboxes = []
                for i in range(3):
                    additional_bboxes.append(BBox(
                        x=200 + i*50, y=250, text=f"Result {i+1}", type="text", ariaLabel=f"Result {i+1}",
                        selector=f'[data-ai-label="{i+1}"]',
                        hierarchy=HierarchyInfo(depth=1, hierarchy=[], siblingIndex=i+1, totalSiblings=4, 
                                              childrenCount=0, interactiveChildrenCount=0, semanticRole="text"),
                        boundingBox=BoundingBox(left=200+i*50, top=250, width=80, height=20),
                        globalIndex=i+1, isInteractive=False, elementRole="text"
                    ))
                
                after_state = Annotation(
                    img="after_image", 
                    bboxes=[before_bbox] + additional_bboxes,
                    markdown="Submit button\nResults shown",
                    totalElements=4
                )
                
                # Mock page for URL access
                mock_page = Mock()
                mock_page.url = "https://example.com/results"
                lame_agent.state_manager.get_current_page = Mock(return_value=mock_page)
                
                tool_outputs = ["Successfully clicked Submit button."]
                
                description = await lame_agent._generate_outcome_description(
                    "Click the submit button", before_state, after_state, tool_outputs
                )
                
                assert "successfully clicked submit button" in description.lower()
                assert "3 additional interactive elements" in description.lower()
                assert "currently visible" in description.lower()


class TestLameAgentEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_should_handle_uninitialized_agent_gracefully(self, mock_browser_context):
        """Test behavior when agent is not properly initialized."""
        lame_agent = LameAgent(mock_browser_context)  # Not using create() method
        
        result = await lame_agent.execute_command("Do something")
        
        assert "error" in result.lower()
        assert "not properly initialized" in result.lower()
    
    @pytest.mark.asyncio
    async def test_should_handle_empty_commands(self, mock_browser_context):
        """Test handling of empty or None commands."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                # Setup minimal mocks
                empty_annotation = Annotation(
                    img="", bboxes=[], markdown="", totalElements=0
                )
                lame_agent.state_manager.get_current_page_data = AsyncMock(return_value=empty_annotation)
                
                empty_page = Mock()
                empty_page.url = ""
                empty_page.title = AsyncMock(return_value="")
                lame_agent.state_manager.get_current_page.return_value = empty_page
                
                result = await lame_agent.execute_command("")
                
                # Should not crash, should handle gracefully
                assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_should_dispose_cleanly(self, mock_browser_context):
        """Test that dispose method works without errors."""
        with patch('kagebunshin.core.blind_and_lame.lame_agent.KageBunshinStateManager') as mock_sm:
            mock_state_manager = AsyncMock()
            # get_tools_for_llm is synchronous and returns a list
            @tool
            def mock_click_tool(bbox_id: int) -> str:
                """Mock click tool for testing."""
                return f"Clicked element {bbox_id}"
            
            mock_state_manager.get_tools_for_llm = Mock(return_value=[mock_click_tool])
            mock_sm.create = AsyncMock(return_value=mock_state_manager)
            
            with patch('kagebunshin.core.blind_and_lame.lame_agent.init_chat_model'):
                lame_agent = await LameAgent.create(mock_browser_context)
                
                # Should not raise any exceptions
                lame_agent.dispose()