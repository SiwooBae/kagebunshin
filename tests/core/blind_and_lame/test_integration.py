"""
Integration tests for Blind and Lame architecture.

Tests cover:
- End-to-end task completion workflows
- Communication between Blind and Lame agents
- Real browser automation scenarios (with mocks)
- Factory function behavior
- Performance and error scenarios
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import asyncio

from kagebunshin.core.blind_and_lame import create_blind_and_lame_pair, LameAgent, BlindAgent
from kagebunshin.core.state import Annotation, BBox, BoundingBox, HierarchyInfo
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


class TestBlindAndLameFactory:
    """Test the factory function for creating agent pairs."""
    
    @pytest.mark.asyncio
    async def test_should_create_connected_agent_pair(self, mock_browser_context):
        """Test successful creation of connected Blind-Lame agent pair."""
        with patch('kagebunshin.core.blind_and_lame.LameAgent.create') as mock_lame_create:
            mock_lame_agent = Mock(spec=LameAgent)
            mock_lame_agent.get_act_tool_for_blind.return_value = Mock()
            mock_lame_create.return_value = mock_lame_agent
            
            with patch('kagebunshin.core.blind_and_lame.BlindAgent') as mock_blind_class:
                mock_blind_agent = Mock(spec=BlindAgent)
                mock_blind_class.return_value = mock_blind_agent
                
                blind_agent, lame_agent = await create_blind_and_lame_pair(mock_browser_context)
                
                assert blind_agent == mock_blind_agent
                assert lame_agent == mock_lame_agent
                
                # Verify Lame agent was created first with browser context
                mock_lame_create.assert_called_once_with(mock_browser_context)
                
                # Verify Blind agent was created with Lame agent reference
                mock_blind_class.assert_called_once_with(mock_lame_agent)
    
    @pytest.mark.asyncio
    async def test_should_handle_factory_errors_appropriately(self, mock_browser_context):
        """Test error handling in factory function."""
        with patch('kagebunshin.core.blind_and_lame.LameAgent.create', side_effect=Exception("Browser error")):
            with pytest.raises(Exception, match="Browser error"):
                await create_blind_and_lame_pair(mock_browser_context)


class TestBlindLameCommunication:
    """Test communication between Blind and Lame agents."""
    
    @pytest.fixture
    async def mock_agent_pair(self, mock_browser_context):
        """Create a mock agent pair for communication testing."""
        # Create mock Lame agent with act tool
        mock_lame = Mock(spec=LameAgent)
        
        # Track commands sent to Lame agent
        command_history = []
        
        async def mock_execute_command(command):
            command_history.append(command)
            if "navigate" in command.lower():
                return f"Navigated to the requested page. The page shows a search form with a text input field and submit button."
            elif "type" in command.lower():
                return f"Typed the requested text into the search field. The input now contains the search query."
            elif "click" in command.lower():
                return f"Clicked the submit button. The page now shows search results with 10 items."
            else:
                return f"Executed command: {command}"
        
        mock_lame.execute_command = mock_execute_command
        mock_lame.get_current_state_description = AsyncMock(return_value="Mock page state")
        mock_lame.dispose = Mock()
        
        # Create act tool that delegates to execute_command
        from langchain_core.tools import tool
        
        @tool
        async def act(command: str) -> str:
            """Execute browser command"""
            return await mock_execute_command(command)
        
        mock_lame.get_act_tool_for_blind.return_value = act
        
        # Create Blind agent with mocked LLM
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model') as mock_init_llm:
            mock_llm = AsyncMock()
            mock_init_llm.return_value = mock_llm
            
            blind_agent = BlindAgent(mock_lame)
            
            # Mock the compiled workflow to simulate reasoning and tool calling
            async def mock_workflow(initial_state):
                # Simulate Blind agent reasoning and issuing commands
                messages = initial_state["messages"].copy()
                
                # First reasoning: plan the task
                plan_message = AIMessage(
                    content="I need to search for information. Let me start by navigating to a search engine.",
                    tool_calls=[{"id": "1", "name": "act", "args": {"command": "Navigate to https://www.google.com"}}]
                )
                messages.append(plan_message)
                
                # Execute first action
                nav_result = await mock_execute_command("Navigate to https://www.google.com")
                messages.append(ToolMessage(content=nav_result, tool_call_id="1"))
                
                # Second reasoning: search for the information
                search_message = AIMessage(
                    content="Good, I'm now on the search page. Let me search for the requested information.",
                    tool_calls=[{"id": "2", "name": "act", "args": {"command": "Type 'transformers machine learning' in the search box"}}]
                )
                messages.append(search_message)
                
                # Execute second action
                type_result = await mock_execute_command("Type 'transformers machine learning' in the search box")
                messages.append(ToolMessage(content=type_result, tool_call_id="2"))
                
                # Third reasoning: submit search
                submit_message = AIMessage(
                    content="Perfect! Now let me submit the search to get results.",
                    tool_calls=[{"id": "3", "name": "act", "args": {"command": "Click the search button"}}]
                )
                messages.append(submit_message)
                
                # Execute third action
                click_result = await mock_execute_command("Click the search button")
                messages.append(ToolMessage(content=click_result, tool_call_id="3"))
                
                # Final reasoning: task completion
                completion_message = AIMessage(
                    content="Excellent! I have successfully completed the search task. The search results now show 10 relevant items about transformers in machine learning."
                )
                messages.append(completion_message)
                
                return {
                    "input": initial_state["input"],
                    "messages": messages,
                    "task_completed": True
                }
            
            blind_agent.agent.ainvoke = mock_workflow
            
            return blind_agent, mock_lame, command_history
    
    @pytest.mark.asyncio
    async def test_should_execute_multi_step_task_successfully(self, mock_agent_pair):
        """Test successful execution of multi-step task through agent communication."""
        blind_agent, mock_lame, command_history = mock_agent_pair
        
        result = await blind_agent.ainvoke("Search for information about transformers in machine learning")
        
        # Verify task completion
        assert "successfully completed" in result.lower()
        assert "search results" in result.lower()
        assert "transformers" in result.lower()
        
        # Verify command sequence was executed
        assert len(command_history) == 3
        assert "navigate" in command_history[0].lower()
        assert "type" in command_history[1].lower()
        assert "transformers machine learning" in command_history[1].lower()
        assert "click" in command_history[2].lower()
    
    @pytest.mark.asyncio
    async def test_should_handle_lame_agent_errors_gracefully(self, mock_browser_context):
        """Test error handling when Lame agent encounters issues."""
        # Create Lame agent that raises errors
        mock_lame = Mock(spec=LameAgent)
        mock_lame.execute_command = AsyncMock(side_effect=Exception("Browser automation failed"))
        mock_lame.dispose = Mock()
        
        from langchain_core.tools import tool
        
        @tool
        async def failing_act(command: str) -> str:
            """Act tool that fails"""
            return await mock_lame.execute_command(command)
        
        mock_lame.get_act_tool_for_blind.return_value = failing_act
        
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame)
            
            # Mock workflow that tries to use the failing tool
            async def failing_workflow(initial_state):
                messages = initial_state["messages"].copy()
                
                try:
                    # Try to execute a command that will fail
                    result = await failing_act.ainvoke({"command": "Navigate somewhere"})
                    messages.append(ToolMessage(content=result, tool_call_id="1"))
                except Exception as e:
                    messages.append(AIMessage(content=f"I encountered an error: {str(e)}. Let me try a different approach."))
                
                return {
                    "input": initial_state["input"],
                    "messages": messages,
                    "task_completed": False
                }
            
            blind_agent.agent.ainvoke = failing_workflow
            
            result = await blind_agent.ainvoke("Do something")
            
            # Should handle error gracefully
            assert "encountered an error" in result.lower()


class TestEndToEndScenarios:
    """Test complete end-to-end automation scenarios."""
    
    @pytest.fixture
    def realistic_page_progression(self):
        """Create realistic page state progression for testing."""
        # Initial search page
        search_page = Annotation(
            img="search_page_image",
            bboxes=[
                BBox(
                    x=300, y=200, text="", type="textbox", ariaLabel="Search",
                    selector='input[name="q"]',
                    hierarchy=HierarchyInfo(depth=2, hierarchy=[], siblingIndex=0, totalSiblings=2, 
                                          childrenCount=0, interactiveChildrenCount=0, semanticRole="textbox"),
                    boundingBox=BoundingBox(left=300, top=200, width=400, height=40),
                    globalIndex=0, isInteractive=True, elementRole="interactive"
                ),
                BBox(
                    x=720, y=200, text="Search", type="button", ariaLabel="Google Search",
                    selector='input[name="btnK"]',
                    hierarchy=HierarchyInfo(depth=2, hierarchy=[], siblingIndex=1, totalSiblings=2, 
                                          childrenCount=0, interactiveChildrenCount=0, semanticRole="button"),
                    boundingBox=BoundingBox(left=720, top=200, width=80, height=40),
                    globalIndex=1, isInteractive=True, elementRole="interactive"
                )
            ],
            markdown="# Google\nSearch box and button",
            totalElements=2
        )
        
        # Results page after search
        results_page = Annotation(
            img="results_page_image",
            bboxes=[
                BBox(
                    x=100, y=300, text="Transformers (machine learning) - Wikipedia", type="link", 
                    ariaLabel="Wikipedia article about transformers",
                    selector='a[href*="wikipedia.org/transformers"]',
                    hierarchy=HierarchyInfo(depth=3, hierarchy=[], siblingIndex=0, totalSiblings=10, 
                                          childrenCount=0, interactiveChildrenCount=0, semanticRole="link"),
                    boundingBox=BoundingBox(left=100, top=300, width=500, height=60),
                    globalIndex=0, isInteractive=True, elementRole="interactive"
                ),
                BBox(
                    x=100, y=400, text="Attention Is All You Need - Paper", type="link",
                    ariaLabel="Research paper link",
                    selector='a[href*="arxiv.org"]',
                    hierarchy=HierarchyInfo(depth=3, hierarchy=[], siblingIndex=1, totalSiblings=10, 
                                          childrenCount=0, interactiveChildrenCount=0, semanticRole="link"),
                    boundingBox=BoundingBox(left=100, top=400, width=450, height=60),
                    globalIndex=1, isInteractive=True, elementRole="interactive"
                )
            ],
            markdown="# Search Results\n1. Transformers (machine learning) - Wikipedia\n2. Attention Is All You Need - Paper",
            totalElements=2
        )
        
        return search_page, results_page
    
    @pytest.mark.asyncio
    async def test_complete_research_task_workflow(self, mock_browser_context, realistic_page_progression):
        """Test complete research workflow from search to results."""
        search_page, results_page = realistic_page_progression
        
        # Mock Lame agent with realistic browser interactions
        mock_lame = Mock(spec=LameAgent)
        
        # Track page state changes
        current_page_state = [search_page]  # Start with search page
        
        async def mock_execute_with_state_changes(command):
            if "navigate" in command.lower() and "google" in command.lower():
                current_page_state[0] = search_page
                return "Navigated to Google search page. I can see a search input field and a search button."
            elif "type" in command.lower() and "transformers" in command.lower():
                return "Typed 'transformers machine learning' into the search field. The text is now visible in the input box."
            elif "click" in command.lower() and ("search" in command.lower() or "submit" in command.lower()):
                current_page_state[0] = results_page
                return "Clicked the search button. The page now shows search results with multiple links about transformers."
            elif "click" in command.lower() and "wikipedia" in command.lower():
                return "Clicked on the Wikipedia link. Now viewing the Wikipedia article about transformers in machine learning."
            elif "extract" in command.lower():
                return "Extracted article content: Transformers are a type of neural network architecture that has revolutionized natural language processing..."
            else:
                return f"Executed: {command}"
        
        mock_lame.execute_command = mock_execute_with_state_changes
        mock_lame.get_current_state_description = AsyncMock(return_value="Current page state")
        mock_lame.dispose = Mock()
        
        # Create act tool
        from langchain_core.tools import tool
        
        @tool
        async def act(command: str) -> str:
            """Mock act tool for end-to-end testing."""
            return await mock_execute_with_state_changes(command)
        
        mock_lame.get_act_tool_for_blind.return_value = act
        
        # Create Blind agent with realistic workflow
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame)
            
            # Simulate complete research workflow
            async def research_workflow(initial_state):
                messages = initial_state["messages"].copy()
                query = initial_state["input"]
                
                steps = [
                    ("Navigate to https://www.google.com", "I need to start by going to Google to search for information."),
                    ("Type 'transformers machine learning' in the search box", "Now I'll search for the specific topic."),
                    ("Click the search button", "Let me submit the search to see results."),
                    ("Click on the Wikipedia link about transformers", "I'll click on the most authoritative source."),
                    ("Extract the main content from the article", "Now let me extract the key information from the article.")
                ]
                
                for command, reasoning in steps:
                    # Add reasoning message
                    reasoning_msg = AIMessage(
                        content=reasoning,
                        tool_calls=[{"id": f"step_{len(messages)}", "name": "act", "args": {"command": command}}]
                    )
                    messages.append(reasoning_msg)
                    
                    # Execute command
                    result = await mock_execute_with_state_changes(command)
                    messages.append(ToolMessage(content=result, tool_call_id=f"step_{len(messages)}"))
                
                # Final summary
                summary = AIMessage(
                    content="Task completed successfully! I have researched transformers in machine learning by:"
                            "\n1. Navigating to Google search"
                            "\n2. Searching for 'transformers machine learning'"
                            "\n3. Finding and accessing the Wikipedia article"
                            "\n4. Extracting the key information"
                            "\nTransformers are a revolutionary neural network architecture for natural language processing."
                )
                messages.append(summary)
                
                return {
                    "input": initial_state["input"],
                    "messages": messages,
                    "task_completed": True
                }
            
            blind_agent.agent.ainvoke = research_workflow
            
            result = await blind_agent.ainvoke("Research transformers in machine learning and provide key information")
            
            # Verify comprehensive task completion
            assert "task completed successfully" in result.lower()
            assert "neural network architecture" in result.lower()
            assert "natural language processing" in result.lower()
            assert "wikipedia" in result.lower()
            
            # Verify all steps were mentioned
            assert "navigating to google" in result.lower()
            assert "searching for" in result.lower()
            assert "extracting" in result.lower()


class TestPerformanceAndScalability:
    """Test performance characteristics and edge cases."""
    
    @pytest.mark.asyncio
    async def test_should_handle_long_conversation_history(self, mock_browser_context):
        """Test handling of long conversation with many messages."""
        mock_lame = Mock(spec=LameAgent)
        mock_lame.execute_command = AsyncMock(return_value="Action completed")
        mock_lame.dispose = Mock()
        
        from langchain_core.tools import tool
        
        @tool
        async def act(command: str) -> str:
            """Mock act tool for performance testing."""
            return "Command executed"
        
        mock_lame.get_act_tool_for_blind.return_value = act
        
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame)
            
            # Create state with many messages
            many_messages = [HumanMessage(content="Initial query")]
            for i in range(50):  # 50 back-and-forth interactions
                many_messages.append(AIMessage(content=f"Step {i} reasoning"))
                many_messages.append(ToolMessage(content=f"Step {i} result", tool_call_id=f"step_{i}"))
            
            test_state = {
                "input": "Complex task",
                "messages": many_messages,
                "task_completed": False
            }
            
            # Should handle large message history without crashing
            result = await blind_agent.check_task_completion(test_state)
            assert isinstance(result, dict)
            assert "task_completed" in result
    
    @pytest.mark.asyncio
    async def test_should_handle_rapid_sequential_commands(self, mock_browser_context):
        """Test handling of rapid command execution."""
        mock_lame = Mock(spec=LameAgent)
        
        command_count = 0
        
        async def fast_execute_command(command):
            nonlocal command_count
            command_count += 1
            await asyncio.sleep(0.001)  # Minimal delay
            return f"Rapid command {command_count} executed"
        
        mock_lame.execute_command = fast_execute_command
        mock_lame.dispose = Mock()
        
        from langchain_core.tools import tool
        
        @tool
        async def act(command: str) -> str:
            """Mock act tool for rapid command testing."""
            return await fast_execute_command(command)
        
        mock_lame.get_act_tool_for_blind.return_value = act
        
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame)
            
            # Simulate rapid command execution
            async def rapid_workflow(initial_state):
                messages = initial_state["messages"].copy()
                
                # Execute 10 rapid commands
                for i in range(10):
                    result = await fast_execute_command(f"Command {i}")
                    messages.append(AIMessage(content=f"Executed rapid command {i}"))
                
                return {
                    "input": initial_state["input"],
                    "messages": messages,
                    "task_completed": True
                }
            
            blind_agent.agent.ainvoke = rapid_workflow
            
            start_time = asyncio.get_event_loop().time()
            result = await blind_agent.ainvoke("Execute rapid commands")
            end_time = asyncio.get_event_loop().time()
            
            # Should complete quickly and handle all commands
            assert command_count == 10
            assert end_time - start_time < 1.0  # Should complete in less than 1 second
    
    def test_should_cleanup_resources_properly(self, mock_browser_context):
        """Test that all resources are cleaned up properly."""
        mock_lame = Mock(spec=LameAgent)
        mock_lame.dispose = Mock()
        
        # Create proper act tool
        from langchain_core.tools import tool
        
        @tool
        async def act(command: str) -> str:
            """Mock act tool for cleanup testing."""
            return "Command executed"
        
        mock_lame.get_act_tool_for_blind.return_value = act
        
        with patch('kagebunshin.core.blind_and_lame.blind_agent.init_chat_model'):
            blind_agent = BlindAgent(mock_lame)
            
            # Create some internal state
            blind_agent.agent = Mock()
            blind_agent.llm_with_tools = Mock()
            
            # Dispose should clean up everything
            blind_agent.dispose()
            
            # Verify Lame agent was disposed
            mock_lame.dispose.assert_called_once()
            
            # Multiple dispose calls should be safe
            blind_agent.dispose()
            assert mock_lame.dispose.call_count == 2  # Called twice, should be safe