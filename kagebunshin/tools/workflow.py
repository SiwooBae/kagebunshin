"""
Workflow management tools for KageBunshin.

These tools handle task completion and note-taking functionality,
decoupled from the browser automation state manager. They operate
on the LangGraph state flow for proper workflow orchestration.
"""

import time
import logging
from typing import Annotated, Dict, Any, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from ..core.state import KageBunshinState


logger = logging.getLogger(__name__)


@tool
def take_note(note: str) -> str:
    """Record important information or observations for future reference.
    
    This tool provides a way to maintain context and memory throughout
    a browsing session by recording key findings, progress updates,
    and important observations that may be useful later.
    
    Use take_note to:
    - Record important findings or data discovered during browsing
    - Track progress through multi-step tasks or workflows
    - Note down URLs, contact information, or reference data
    - Record error conditions or issues encountered
    - Mark successful completion of subtasks or milestones
    - Document patterns or insights discovered during research
    - Create reminders for follow-up actions
    - Log decision points and reasoning
    
    Args:
        note (str): The note content to record. Can include:
                  - Factual observations ("Found price: $29.99")
                  - Progress updates ("Completed login successfully")
                  - Reference information ("Contact email: support@example.com")
                  - Error details ("Submit button not working, trying alternative")
                  - Strategy notes ("Need to scroll down to load more products")
                  - Timestamps or sequence information
                  - Any other contextual information
    
    Returns:
        str: Confirmation message "Note recorded." indicating the note
             has been successfully logged.
    
    Note Behavior:
    - Notes persist for the duration of the current session
    - Notes help maintain context across long browsing sessions
    
    Best Practices:
    - Use clear, descriptive language in notes
    - Include relevant context (page URLs, element descriptions)
    - Note both successes and failures for complete picture
    - Use consistent formatting for similar types of notes
    - Record timestamps or sequence information when relevant
    - Include specific data values when discovered
    
    Note Categories:
    - **Progress**: "Completed login process", "Navigated to products page"
    - **Findings**: "Price: $29.99", "Contact: support@example.com"
    - **Issues**: "Button not responsive", "Page loading slowly"
    - **Strategy**: "Will try alternative search approach"
    - **Context**: "This is the checkout page", "User logged in successfully"
    """
    logger.info(f"Agent note: {note}")
    return "Note recorded."


@tool
async def complete_task(
    status: str, 
    result: str, 
    confidence: Optional[float] = None,
    state: Annotated[Dict[str, Any], InjectedState] = None
) -> str:
    """Complete the current task with structured output and terminate the agent workflow.
    
    This tool provides explicit, intentional task completion with structured output.
    Use this tool when you have finished your mission, encountered an insurmountable obstacle,
    or need to provide a final answer to the user. This will be the final message shown to the user.
    
    ## Purpose & Use Cases
    
    **Primary Completion Scenarios:**
    - Successfully completed the user's request
    - Task partially completed with clear limitations
    - Unable to continue due to technical barriers
    - Blocked by authentication, permissions, or access issues
    
    ## Arguments
    
    **status** (str, required):
    - "success": Task completed successfully as requested.
    - "partial": Task partially completed with limitations.
    - "failure": Task failed due to technical issues.
    - "blocked": Unable to proceed due to external constraints.
    
    **result** (str, required):
    - Final answer, explanation, or summary of outcomes in **markdown format**.
    - This can be AS LONG AS YOU WANT! Do not truncate/summarize the result.
    - Should be comprehensive and user-facing.
    - Include relevant data, findings, or completed actions.
    - Explain any limitations or next steps if applicable.
    
    **confidence** (float, optional):
    - Confidence score between 0.0 (low) and 1.0 (high).
    - Only provide if you can meaningfully assess certainty.
    - Consider factors like data completeness, verification level.
    - Omit if confidence assessment isn't applicable.
    
    ## Note: there is no length limit for **result**. If you need to provide a long answer, provide a long answer.
    
    ## Returns
    
    **Confirmation message** and terminates the agent workflow.
    The structured completion data is stored in the conversation state
    for extraction by the orchestrator and downstream systems.
    
    ## Behavior Details
    
    **Workflow Termination:**
    - Sets completion data in the workflow state
    - Triggers workflow routing to END state
    - Enables structured result extraction by orchestrator
    - Provides final status and confidence metrics
    
    **Data Structure:**
    - Status classification for automated processing
    - Comprehensive result content for user display
    - Optional confidence scoring for quality assessment
    - Timestamp for completion tracking and debugging
    
    ## Important Notes
    
    **Status Guidelines:**
    - Use "success" only when task is fully completed as requested
    - Use "partial" when significant progress made but constraints exist
    - Use "failure" for technical issues that prevent completion
    - Use "blocked" for external factors (auth, permissions, access)
    
    **Result Content:**
    - Write for the end user, not for debugging
    - Include all relevant findings and data
    - Explain any limitations or assumptions
    - Provide next steps if applicable
    - Use markdown formatting for readability
    
    **Confidence Assessment:**
    - Consider data source reliability
    - Factor in verification completeness  
    - Account for assumptions and limitations
    - Only provide if you can meaningfully assess
    
    ## Integration with KageBunshin Workflow
    
    **State Management:**
    - Completion data flows through LangGraph state
    - Agent routing checks state for completion signal
    - Orchestrator extracts structured completion data
    - Supports both single-shot and REPL modes
    
    **Multi-Agent Coordination:**
    - Parent agents can detect clone completion
    - Enables hierarchical task decomposition
    - Supports parallel execution with structured results
    - Facilitates swarm intelligence coordination
    """
    # Validate status
    valid_statuses = {"success", "partial", "failure", "blocked"}
    if status not in valid_statuses:
        return f"Error: status must be one of {valid_statuses}, got '{status}'"
    
    # Validate confidence if provided
    if confidence is not None:
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            return f"Error: confidence must be a number between 0.0 and 1.0, got {confidence}"
    
    # Store completion data in workflow state for orchestrator extraction
    if state is not None:
        completion_data = {
            "status": status,
            "result": result,
            "confidence": confidence,
            "completed_at": time.time()
        }
        state["completion_data"] = completion_data
    
    # Format confirmation message
    confidence_text = f" (confidence: {confidence:.0%})" if confidence is not None else ""
    return f"Task completed with status '{status}'{confidence_text}. Result: {result}"