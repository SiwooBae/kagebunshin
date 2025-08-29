"""
Data models and state definitions for KageBunshin system

This module defines the core state structures used throughout the KageBunshin
system, including web automation state, filesystem operation tracking,
and agent coordination data.

The state system supports:
- Web automation with browser context and page elements
- Filesystem operations with security tracking and auditing
- Agent delegation and coordination
- Conversation history and LLM interactions
"""
from typing import Annotated, List, Optional, Dict, Any
from typing_extensions import TypedDict
from datetime import datetime
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from playwright.async_api import Page, BrowserContext
from pydantic import BaseModel, Field, field_validator


class HierarchyInfo(BaseModel):
    """Hierarchical information about an element's position in the DOM tree."""
    depth: int = Field(description="Depth of the element in the DOM hierarchy")
    hierarchy: List[Dict[str, str]] = Field(default_factory=list, description="Path from root to element")
    siblingIndex: int = Field(description="Index among siblings")
    totalSiblings: int = Field(description="Total number of siblings")
    childrenCount: int = Field(description="Number of direct children")
    interactiveChildrenCount: int = Field(description="Number of interactive child elements")
    semanticRole: str = Field(description="Semantic role of the element")


class BoundingBox(BaseModel):
    """Detailed bounding box information."""
    left: float
    top: float
    width: float
    height: float


class FrameStats(BaseModel):
    """Statistics about iframe processing."""
    totalFrames: int = Field(description="Total number of frames found")
    accessibleFrames: int = Field(description="Number of frames that could be accessed")
    maxDepth: int = Field(description="Maximum iframe nesting depth")


class BBox(BaseModel):
    x: float
    y: float
    text: str
    type: str
    ariaLabel: str
    isCaptcha: Optional[bool] = Field(default=False)
    className: Optional[str] = None
    elementId: Optional[str] = None
    selector: str  # CSS selector pointing to the element (e.g., '[data-ai-label="42"]')
    
    # Enhanced properties for better LLM understanding
    hierarchy: Optional[HierarchyInfo] = Field(default=None, description="Hierarchical structure information")
    frameContext: str = Field(default="main", description="Context of which frame this element belongs to")
    viewportPosition: str = Field(default="in-viewport", description="Position relative to viewport")
    distanceFromViewport: float = Field(default=0, description="Distance from viewport edge in pixels")
    globalIndex: int = Field(description="Global index across all processed elements")
    boundingBox: BoundingBox = Field(description="Detailed bounding box information")
    
    # Unified representation fields
    isInteractive: bool = Field(default=True, description="Whether element is interactive (clickable, typeable, etc.)")
    elementRole: str = Field(default="interactive", description="Element role: 'interactive', 'content', 'structural', 'navigation'")
    focused: bool = Field(default=False, description="Whether this element currently has focus")
    
    # Content-specific fields (for non-interactive elements)
    contentType: Optional[str] = Field(default=None, description="Content type: 'heading', 'paragraph', 'list', 'image', etc.")
    headingLevel: Optional[int] = Field(default=None, description="For headings: 1-6")
    wordCount: Optional[int] = Field(default=None, description="Word count for text content")
    truncated: Optional[bool] = Field(default=False, description="Whether text was truncated")
    fullTextAvailable: Optional[bool] = Field(default=False, description="Whether full text can be extracted")
    
    # Semantic relationships
    parentId: Optional[int] = Field(default=None, description="Global index of parent element")
    childIds: List[int] = Field(default_factory=list, description="Global indices of direct children")
    labelFor: Optional[int] = Field(default=None, description="For labels: ID of associated input")
    describedBy: Optional[int] = Field(default=None, description="ID of element that describes this one")
    
    # Layout context
    isContainer: bool = Field(default=False, description="Whether this is a container element (section, div, etc.)")
    semanticSection: Optional[str] = Field(default=None, description="Semantic section: 'header', 'main', 'nav', 'footer', 'aside'")
    
    @field_validator('isCaptcha', mode='before')
    @classmethod
    def parse_is_captcha(cls, v):
        """Convert empty strings and other falsy values to False for isCaptcha"""
        if v == '' or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes')
        return bool(v)


class TabInfo(TypedDict):
    """Information about a browser tab."""
    
    # The playwright page object
    page: Page
    # Tab index (0-based)
    tab_index: int
    # Tab title
    title: str
    # Tab URL
    url: str
    # Whether this is the currently active tab
    is_active: bool


class FilesystemOperation(BaseModel):
    """
    Record of a filesystem operation performed by the agent.
    
    This model tracks all filesystem operations for security auditing,
    debugging, and coordination between agents. Each operation is
    timestamped and includes detailed metadata about what was performed.
    
    The tracking system helps with:
    - Security monitoring and compliance
    - Debugging agent behaviors
    - Performance analysis and optimization  
    - Coordination between multiple agents
    - Recovery and rollback capabilities
    """
    
    # Core operation details
    operation_id: str = Field(description="Unique identifier for this operation")
    operation_type: str = Field(description="Type of operation: read_file, write_file, list_directory, etc.")
    file_path: str = Field(description="Relative path within sandbox that was operated on")
    timestamp: datetime = Field(description="When the operation was performed")
    
    # Operation status and results
    success: bool = Field(description="Whether the operation completed successfully")
    error_message: Optional[str] = Field(default=None, description="Error message if operation failed")
    error_type: Optional[str] = Field(default=None, description="Category of error if failed")
    
    # Operation metadata
    bytes_affected: Optional[int] = Field(default=None, description="Number of bytes read, written, or deleted")
    duration_ms: Optional[float] = Field(default=None, description="Operation duration in milliseconds")
    sandbox_path: str = Field(description="Absolute path to the sandbox root")
    
    # Agent context
    agent_name: str = Field(description="Name of the agent that performed the operation")
    clone_depth: int = Field(default=0, description="Delegation depth of the performing agent")
    
    # Security and validation
    security_validated: bool = Field(default=True, description="Whether operation passed security validation")
    path_traversal_attempted: bool = Field(default=False, description="Whether path traversal was attempted")
    
    # Additional context (stored as JSON-serializable dict)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional operation-specific metadata")


class FilesystemState(BaseModel):
    """
    Current filesystem state and configuration for an agent.
    
    This model tracks the current filesystem configuration and
    accumulated operations for an agent instance. It provides
    a consolidated view of filesystem activity and settings.
    """
    
    # Configuration
    sandbox_base: str = Field(description="Absolute path to the sandbox root directory")
    enabled: bool = Field(description="Whether filesystem operations are enabled")
    max_file_size: int = Field(description="Maximum allowed file size in bytes")
    allowed_extensions: List[str] = Field(description="List of permitted file extensions")
    
    # Operation tracking
    operations_performed: List[FilesystemOperation] = Field(
        default_factory=list,
        description="List of all filesystem operations performed by this agent"
    )
    
    # Statistics
    total_operations: int = Field(default=0, description="Total number of operations performed")
    successful_operations: int = Field(default=0, description="Number of successful operations")
    failed_operations: int = Field(default=0, description="Number of failed operations")
    total_bytes_read: int = Field(default=0, description="Total bytes read across all operations")
    total_bytes_written: int = Field(default=0, description="Total bytes written across all operations")
    
    # Performance metrics
    average_operation_duration: Optional[float] = Field(default=None, description="Average operation duration in ms")
    last_operation_time: Optional[datetime] = Field(default=None, description="Timestamp of last operation")
    
    def add_operation(self, operation: FilesystemOperation) -> None:
        """
        Add a filesystem operation to the tracking history.
        
        This method updates both the operation log and the aggregate
        statistics for performance monitoring and auditing.
        
        Args:
            operation (FilesystemOperation): The operation to record
        """
        self.operations_performed.append(operation)
        self.total_operations += 1
        
        if operation.success:
            self.successful_operations += 1
            if operation.bytes_affected:
                if operation.operation_type == "read_file":
                    self.total_bytes_read += operation.bytes_affected
                elif operation.operation_type in ["write_file", "create_directory"]:
                    self.total_bytes_written += operation.bytes_affected
        else:
            self.failed_operations += 1
        
        # Update timing statistics
        self.last_operation_time = operation.timestamp
        if operation.duration_ms and self.total_operations > 0:
            # Calculate rolling average (simplified)
            if self.average_operation_duration is None:
                self.average_operation_duration = operation.duration_ms
            else:
                # Weighted average - more recent operations have slightly more weight
                weight = 0.1  # 10% weight for new operation
                self.average_operation_duration = (
                    (1 - weight) * self.average_operation_duration + 
                    weight * operation.duration_ms
                )
    
    def get_recent_operations(self, limit: int = 10) -> List[FilesystemOperation]:
        """
        Get the most recent filesystem operations.
        
        Args:
            limit (int): Maximum number of operations to return
            
        Returns:
            List[FilesystemOperation]: Recent operations in reverse chronological order
        """
        return sorted(
            self.operations_performed[-limit:], 
            key=lambda op: op.timestamp, 
            reverse=True
        )
    
    def get_operations_by_type(self, operation_type: str) -> List[FilesystemOperation]:
        """
        Get all operations of a specific type.
        
        Args:
            operation_type (str): Type of operation to filter by
            
        Returns:
            List[FilesystemOperation]: Operations of the specified type
        """
        return [op for op in self.operations_performed if op.operation_type == operation_type]
    
    def get_security_violations(self) -> List[FilesystemOperation]:
        """
        Get operations that had security violations.
        
        Returns:
            List[FilesystemOperation]: Operations with security issues
        """
        return [
            op for op in self.operations_performed 
            if not op.security_validated or op.path_traversal_attempted
        ]


class KageBunshinState(TypedDict):
    """
    The comprehensive state of the KageBunshin agent.
    
    Contains essential data that flows through the LangGraph workflow:
    - User's query and conversation history (core agent state)
    - Browser context and web automation state
    - Filesystem operations and security tracking
    - Clone depth for delegation hierarchy tracking
    - Performance and debugging information
    
    The state is designed to support:
    - Multi-turn conversations with persistent context
    - Web automation with full browser control
    - Secure filesystem operations with auditing
    - Agent delegation and coordination
    - Comprehensive debugging and monitoring
    """
    
    # Core agent state
    input: str                              # User's query - drives the agent
    messages: Annotated[List[BaseMessage], add_messages]  # Conversation history
    
    # Essential browser state  
    context: BrowserContext                 # Browser context with all tabs
    # current_page_index: int                 # Which tab is currently active (0-based)
    
    # Clone hierarchy tracking
    clone_depth: int                        # Current depth in delegation hierarchy (0 = root agent)
    
    # Termination tracking
    tool_call_retry_count: int              # Number of times reminded to make tool call
    
    # Filesystem state tracking (optional - only present if filesystem is enabled)
    filesystem_state: Optional[FilesystemState]  # Filesystem operations and configuration
    
    # Agent coordination and metadata
    agent_id: Optional[str]                 # Unique identifier for this agent instance  
    parent_agent_id: Optional[str]          # ID of parent agent (for clones)
    sandbox_path: Optional[str]             # Path to this agent's filesystem sandbox

class Annotation(BaseModel):
    img: str = Field(description="Base64 encoded image of the current page")
    bboxes: List[BBox] = Field(description="List of bounding boxes on the page")
    markdown: str = Field(description="Markdown representation of the page")
    
    # Enhanced annotation data
    viewportCategories: Optional[Dict[str, int]] = Field(
        default=None, 
        description="Count of elements by viewport position"
    )
    frameStats: Optional[FrameStats] = Field(
        default=None, 
        description="Statistics about iframe processing"
    )
    totalElements: int = Field(default=0, description="Total number of interactive elements found")