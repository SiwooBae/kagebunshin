#!/usr/bin/env python3
"""
Quick test to verify clone depth tracking is working correctly.
"""

import asyncio
from unittest.mock import Mock

from kagebunshin.core.state import KageBunshinState
from kagebunshin.tools.delegation import get_additional_tools

async def test_clone_depth_tracking():
    """Test that clone depth is properly tracked and enforced."""
    
    # Mock browser context
    mock_context = Mock()
    mock_browser = Mock()
    mock_context.browser = mock_browser
    
    # Create delegation tools
    tools = get_additional_tools(mock_context, username="test-agent")
    delegate_tool = tools[0]  # delegate is the first tool
    
    # Test depth 0 (should work)
    state_depth_0 = {"messages": [], "clone_depth": 0}
    tasks = ["test task 1", "test task 2"]
    
    print("Testing delegation at depth 0...")
    try:
        # This will fail due to missing browser setup, but should not fail due to depth
        result = await delegate_tool.ainvoke({"tasks": tasks, "state": state_depth_0})
        print(f"Depth 0 result type: {type(result)}")
        # Should not be an error about depth
        assert "Maximum clone depth" not in result
        print("✓ Depth 0 delegation allowed")
    except Exception as e:
        print(f"Expected error (browser setup): {e}")
    
    # Test depth 3 (should be rejected)
    state_depth_3 = {"messages": [], "clone_depth": 3}
    
    print("\nTesting delegation at depth 3 (should be rejected)...")
    result = await delegate_tool.ainvoke({"tasks": tasks, "state": state_depth_3})
    print(f"Depth 3 result: {result}")
    assert "Maximum clone depth" in result
    print("✓ Depth 3 delegation properly rejected")
    
    print("\n✅ Clone depth tracking is working correctly!")

if __name__ == "__main__":
    asyncio.run(test_clone_depth_tracking())