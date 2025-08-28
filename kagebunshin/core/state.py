"""Data models and state definitions for KageBunshinV2 system"""
from typing import Annotated, List, Optional, Dict, Any
from typing_extensions import TypedDict
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


class KageBunshinState(TypedDict):
    """The optimized state of the KageBunshin agent.
    
    Contains only the truly essential data that cannot be derived:
    - User's query and conversation history (core agent state)
    - Browser context and current page index (essential browser state)
    - Clone depth for delegation hierarchy tracking
    
    All other data (screenshots, bboxes, markdown, etc.) is derived on-demand.
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