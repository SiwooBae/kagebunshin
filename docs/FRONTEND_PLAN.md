# KageBunshin Frontend MVP Plan

## Overview
Create a simple, effective React + TypeScript + Vite frontend that replicates the full functionality of `uv run -m kagebunshin --repl`. The design will be minimalist black and white (#ffffff background, #121414 text) with focus on functionality and clarity.

## Core Requirements Analysis

### CLI REPL Functionality to Replicate
Based on analysis of `kagebunshin/cli/runner.py:run_loop()`:

1. **Persistent Session Management**
   - Maintains single browser context across multiple queries
   - Uses stable thread_id for conversation continuity
   - Preserves message history in LangGraph MemorySaver
   - Session survives until explicit exit

2. **Streaming Response System**
   - Real-time streaming via `KageBunshinAgent.astream()`
   - Chunks contain 'agent' and 'summarizer' keys
   - Messages have content, tool_calls with name/args
   - Progressive display of tool execution and results

3. **Visual Feedback Components**
   - Color-coded step types (INIT, TOOL, MESSAGE, ANSWER, ERROR, etc.)
   - Timestamp display for each action
   - Step counter with emoji indicators
   - Final answer highlighting with banner formatting

4. **Status Information Display**
   - Current URL and page title
   - Action count tracking
   - Browser state indicators
   - Session information

## Technical Architecture

### Backend API Layer
**Primary File: `server/api_server.py`**

#### FastAPI Server Architecture

**Core Dependencies:**
```python
# server/requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
pydantic>=2.5.0
python-multipart>=0.0.6
redis>=5.0.0  # Optional for distributed sessions
```

**Server Configuration:**
```python
# server/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class ServerSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True
    log_level: str = "info"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    max_sessions: int = 100
    session_timeout: int = 3600  # seconds
    redis_url: Optional[str] = None  # "redis://localhost:6379"
    openai_api_key: str
    anthropic_api_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
```

**Main Server Structure:**
```python
# server/api_server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from .config import ServerSettings
from .session_manager import SessionManager, Session
from .websocket_manager import WebSocketManager
from .models import SessionCreateRequest, SessionResponse, StatusResponse
from .exceptions import SessionNotFoundError, SessionLimitError
```

#### Session Management Architecture

**Session Model:**
```python
# server/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

class SessionStatus(str, Enum):
    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    CLOSING = "closing" 
    CLOSED = "closed"
    ERROR = "error"

class SessionCreateRequest(BaseModel):
    session_name: Optional[str] = None
    initial_message: Optional[str] = None
    browser_config: Optional[Dict[str, Any]] = None

class SessionResponse(BaseModel):
    session_id: str
    status: SessionStatus
    created_at: datetime
    last_activity: datetime
    message_count: int
    current_url: Optional[str] = None
    page_title: Optional[str] = None

class MessageRequest(BaseModel):
    content: str
    message_type: str = "user"
    
class StatusResponse(BaseModel):
    session_id: str
    status: SessionStatus
    browser_active: bool
    current_url: Optional[str]
    page_title: Optional[str]
    action_count: int
    uptime_seconds: float
    memory_usage_mb: Optional[float]
```

**Session Manager Implementation:**
```python
# server/session_manager.py
import asyncio
import weakref
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from kagebunshin.core.agent import KageBunshinAgent
from kagebunshin.core.state_manager import KageBunshinStateManager
from .models import SessionStatus, SessionResponse
from .exceptions import SessionNotFoundError, SessionLimitError

@dataclass
class Session:
    session_id: str
    agent: KageBunshinAgent
    state_manager: KageBunshinStateManager
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    status: SessionStatus = SessionStatus.INITIALIZING
    message_count: int = 0
    websocket_connections: Set[Any] = field(default_factory=set)
    
    def update_activity(self):
        self.last_activity = datetime.now()
    
    def is_expired(self, timeout_seconds: int) -> bool:
        return datetime.now() - self.last_activity > timedelta(seconds=timeout_seconds)

class SessionManager:
    def __init__(self, max_sessions: int = 100, session_timeout: int = 3600):
        self.sessions: Dict[str, Session] = {}
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the session manager and cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
    
    async def stop(self):
        """Stop the session manager and cleanup resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all active sessions
        tasks = [self.close_session(sid) for sid in list(self.sessions.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def create_session(
        self, 
        session_name: Optional[str] = None,
        browser_config: Optional[Dict] = None
    ) -> Session:
        """Create a new KageBunshin session."""
        if len(self.sessions) >= self.max_sessions:
            raise SessionLimitError(f"Maximum sessions ({self.max_sessions}) reached")
        
        session_id = str(uuid.uuid4())
        
        # Initialize KageBunshin components
        state_manager = KageBunshinStateManager()
        await state_manager.initialize_browser(browser_config or {})
        
        agent = KageBunshinAgent(
            state_manager=state_manager,
            thread_id=session_id
        )
        
        session = Session(
            session_id=session_id,
            agent=agent,
            state_manager=state_manager,
            status=SessionStatus.ACTIVE
        )
        
        self.sessions[session_id] = session
        return session
    
    async def get_session(self, session_id: str) -> Session:
        """Get session by ID, raising error if not found."""
        session = self.sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        session.update_activity()
        return session
    
    async def close_session(self, session_id: str):
        """Close and cleanup a session."""
        session = self.sessions.pop(session_id, None)
        if not session:
            return
        
        session.status = SessionStatus.CLOSING
        
        # Close WebSocket connections
        for ws in list(session.websocket_connections):
            try:
                await ws.close()
            except Exception:
                pass
        
        # Cleanup browser context
        try:
            await session.state_manager.cleanup()
        except Exception as e:
            print(f"Error cleaning up session {session_id}: {e}")
        
        session.status = SessionStatus.CLOSED
    
    async def _cleanup_expired_sessions(self):
        """Background task to cleanup expired sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                expired_sessions = [
                    sid for sid, session in self.sessions.items()
                    if session.is_expired(self.session_timeout)
                ]
                
                for session_id in expired_sessions:
                    await self.close_session(session_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in session cleanup: {e}")
    
    def get_session_info(self, session_id: str) -> SessionResponse:
        """Get session information for API response."""
        session = self.sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        return SessionResponse(
            session_id=session_id,
            status=session.status,
            created_at=session.created_at,
            last_activity=session.last_activity,
            message_count=session.message_count,
            current_url=getattr(session.state_manager, 'current_url', None),
            page_title=getattr(session.state_manager, 'page_title', None)
        )
```

#### WebSocket Implementation for Streaming

**WebSocket Manager:**
```python
# server/websocket_manager.py
import json
import asyncio
from typing import Dict, Set, Any, Optional
from fastapi import WebSocket
from datetime import datetime

from .session_manager import SessionManager, Session
from .models import MessageRequest

class WebSocketManager:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept WebSocket connection and add to session."""
        await websocket.accept()
        
        try:
            session = await self.session_manager.get_session(session_id)
            
            # Add to session's WebSocket connections
            if session_id not in self.active_connections:
                self.active_connections[session_id] = set()
            
            self.active_connections[session_id].add(websocket)
            session.websocket_connections.add(websocket)
            
            # Send initial status
            await self._send_status_update(websocket, session)
            
        except Exception as e:
            await websocket.close(code=4000, reason=str(e))
            raise
    
    async def disconnect(self, websocket: WebSocket, session_id: str):
        """Remove WebSocket connection from session."""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        
        try:
            session = await self.session_manager.get_session(session_id)
            session.websocket_connections.discard(websocket)
        except:
            pass  # Session might be gone
    
    async def handle_message(self, websocket: WebSocket, session_id: str, message: dict):
        """Process incoming WebSocket message."""
        try:
            session = await self.session_manager.get_session(session_id)
            
            if message.get("type") == "user_message":
                content = message.get("content", "")
                if not content.strip():
                    return
                
                session.message_count += 1
                session.update_activity()
                
                # Stream KageBunshin response
                await self._stream_agent_response(session, content)
                
            elif message.get("type") == "status_request":
                await self._send_status_update(websocket, session)
                
        except Exception as e:
            await self._send_error(websocket, str(e))
    
    async def _stream_agent_response(self, session: Session, user_input: str):
        """Stream KageBunshinAgent response to all session WebSockets."""
        try:
            # Send user message to all connections
            user_message = {
                "type": "user_message",
                "content": user_input,
                "timestamp": datetime.now().isoformat()
            }
            await self._broadcast_to_session(session.session_id, user_message)
            
            # Stream agent response
            async for chunk in session.agent.astream({
                "input": user_input,
                "messages": []
            }):
                # Format chunk according to KageBunshinAgent.astream() output
                stream_message = {
                    "type": "agent_stream",
                    "data": chunk,
                    "timestamp": datetime.now().isoformat()
                }
                await self._broadcast_to_session(session.session_id, stream_message)
            
            # Send final status update
            for ws in session.websocket_connections:
                await self._send_status_update(ws, session)
                
        except Exception as e:
            error_message = {
                "type": "error", 
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
            await self._broadcast_to_session(session.session_id, error_message)
    
    async def _broadcast_to_session(self, session_id: str, message: dict):
        """Send message to all WebSockets in a session."""
        if session_id not in self.active_connections:
            return
        
        message_str = json.dumps(message)
        disconnected = set()
        
        for websocket in self.active_connections[session_id]:
            try:
                await websocket.send_text(message_str)
            except:
                disconnected.add(websocket)
        
        # Remove disconnected WebSockets
        for ws in disconnected:
            self.active_connections[session_id].discard(ws)
    
    async def _send_status_update(self, websocket: WebSocket, session: Session):
        """Send current session status to WebSocket."""
        try:
            status = {
                "type": "status_update",
                "data": {
                    "session_id": session.session_id,
                    "status": session.status.value,
                    "message_count": session.message_count,
                    "current_url": getattr(session.state_manager, 'current_url', None),
                    "page_title": getattr(session.state_manager, 'page_title', None),
                    "browser_active": hasattr(session.state_manager, 'page') and session.state_manager.page is not None,
                    "uptime_seconds": (datetime.now() - session.created_at).total_seconds()
                },
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_text(json.dumps(status))
        except Exception as e:
            print(f"Error sending status update: {e}")
    
    async def _send_error(self, websocket: WebSocket, error_message: str):
        """Send error message to WebSocket."""
        try:
            error = {
                "type": "error",
                "message": error_message,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_text(json.dumps(error))
        except:
            pass
```

#### KageBunshinAgent Integration Patterns

**Agent Wrapper Service:**
```python
# server/agent_service.py
from typing import AsyncIterator, Dict, Any, Optional
import asyncio
from contextlib import asynccontextmanager

from kagebunshin.core.agent import KageBunshinAgent
from kagebunshin.core.state_manager import KageBunshinStateManager
from kagebunshin.core.state import KageBunshinState

class AgentService:
    """Service layer for KageBunshinAgent integration."""
    
    @staticmethod
    async def create_agent_with_browser(
        thread_id: str,
        browser_config: Optional[Dict[str, Any]] = None
    ) -> tuple[KageBunshinAgent, KageBunshinStateManager]:
        """Create KageBunshinAgent with initialized browser."""
        
        # Default browser configuration for server environment
        default_config = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor"
            ]
        }
        
        if browser_config:
            default_config.update(browser_config)
        
        # Initialize state manager with browser
        state_manager = KageBunshinStateManager()
        await state_manager.initialize_browser(default_config)
        
        # Create agent with persistent thread_id for session continuity
        agent = KageBunshinAgent(
            state_manager=state_manager,
            thread_id=thread_id
        )
        
        return agent, state_manager
    
    @staticmethod
    async def stream_agent_response(
        agent: KageBunshinAgent,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream agent response with proper error handling."""
        
        # Prepare initial state
        initial_state: KageBunshinState = {
            "input": user_input,
            "messages": context.get("messages", []) if context else [],
            # Add any additional context fields
        }
        
        try:
            async for chunk in agent.astream(initial_state):
                # Add metadata to chunks
                enhanced_chunk = {
                    **chunk,
                    "metadata": {
                        "thread_id": agent.thread_id,
                        "timestamp": datetime.now().isoformat(),
                        "session_active": True
                    }
                }
                yield enhanced_chunk
                
        except Exception as e:
            # Stream error information
            error_chunk = {
                "error": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                }
            }
            yield error_chunk
    
    @staticmethod
    async def get_agent_status(
        state_manager: KageBunshinStateManager
    ) -> Dict[str, Any]:
        """Get current agent/browser status."""
        
        try:
            # Extract browser state information
            browser_info = {}
            if hasattr(state_manager, 'page') and state_manager.page:
                try:
                    browser_info = {
                        "url": state_manager.page.url,
                        "title": await state_manager.page.title(),
                        "is_closed": state_manager.page.is_closed()
                    }
                except:
                    browser_info = {"error": "Could not fetch page info"}
            
            return {
                "browser_active": hasattr(state_manager, 'context') and state_manager.context is not None,
                "page_active": hasattr(state_manager, 'page') and state_manager.page is not None,
                **browser_info
            }
            
        except Exception as e:
            return {"error": str(e)}
```

#### Error Handling and Logging

**Custom Exceptions:**
```python
# server/exceptions.py
class KageBunshinServerError(Exception):
    """Base exception for server errors."""
    pass

class SessionNotFoundError(KageBunshinServerError):
    """Session not found."""
    pass

class SessionLimitError(KageBunshinServerError):
    """Session limit exceeded."""
    pass

class BrowserInitializationError(KageBunshinServerError):
    """Browser initialization failed."""
    pass

class AgentError(KageBunshinServerError):
    """Agent execution error."""
    pass
```

**Logging Configuration:**
```python
# server/logging_config.py
import logging
import sys
from datetime import datetime
from typing import Optional

class ColoredFormatter(logging.Formatter):
    """Colored log formatter for better visibility."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green  
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)

def setup_logging(log_level: str = "INFO"):
    """Configure server logging."""
    
    # Create formatter
    formatter = ColoredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # File handler for errors
    file_handler = logging.FileHandler(
        f'server_{datetime.now().strftime("%Y%m%d")}.log'
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    file_handler.setLevel(logging.WARNING)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Suppress noisy loggers
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("chromium").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
```

#### CORS and Security Considerations

**Security Configuration:**
```python
# server/security.py
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import time
import hashlib
import hmac

class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = {}
    
    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        minute = int(now // 60)
        
        if client_ip not in self.requests:
            self.requests[client_ip] = {}
        
        client_requests = self.requests[client_ip]
        
        # Clean old entries
        client_requests = {
            k: v for k, v in client_requests.items() 
            if k >= minute - 1
        }
        self.requests[client_ip] = client_requests
        
        current_count = client_requests.get(minute, 0)
        
        if current_count >= self.requests_per_minute:
            return False
        
        client_requests[minute] = current_count + 1
        return True

# Rate limiter middleware
rate_limiter = RateLimiter(requests_per_minute=120)

async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded"
        )
    
    response = await call_next(request)
    return response

# Optional API key authentication
class APIKeyAuth(HTTPBearer):
    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key
    
    async def __call__(self, request: Request) -> Optional[str]:
        if not self.api_key:
            return None  # No auth required
        
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        
        if not credentials or credentials.credentials != self.api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        return credentials.credentials
```

**CORS Configuration:**
```python
# In api_server.py
from fastapi.middleware.cors import CORSMiddleware

def configure_cors(app: FastAPI, settings: ServerSettings):
    """Configure CORS for frontend integration."""
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type", 
            "Authorization",
            "X-Requested-With",
            "X-Session-ID"
        ],
        expose_headers=["X-Session-ID", "X-Rate-Limit-Remaining"]
    )
```

#### Database/Persistence Layer (Optional)

**Session Persistence with Redis:**
```python
# server/persistence.py
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from redis.asyncio import Redis
from dataclasses import asdict

class SessionPersistence:
    """Optional Redis-based session persistence."""
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url
        self.redis: Optional[Redis] = None
    
    async def connect(self):
        """Connect to Redis if configured."""
        if self.redis_url:
            self.redis = Redis.from_url(self.redis_url, decode_responses=True)
            try:
                await self.redis.ping()
                return True
            except:
                self.redis = None
                return False
        return False
    
    async def save_session_metadata(self, session_id: str, metadata: Dict[str, Any]):
        """Save session metadata to Redis."""
        if not self.redis:
            return
        
        try:
            key = f"session:{session_id}:metadata"
            await self.redis.setex(
                key, 
                timedelta(hours=24), 
                json.dumps(metadata, default=str)
            )
        except Exception as e:
            print(f"Error saving session metadata: {e}")
    
    async def get_session_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session metadata from Redis."""
        if not self.redis:
            return None
        
        try:
            key = f"session:{session_id}:metadata"
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"Error getting session metadata: {e}")
            return None
    
    async def save_message_history(self, session_id: str, messages: list):
        """Save message history to Redis."""
        if not self.redis:
            return
        
        try:
            key = f"session:{session_id}:messages"
            await self.redis.lpush(key, *[json.dumps(msg, default=str) for msg in messages])
            await self.redis.expire(key, timedelta(hours=24))
        except Exception as e:
            print(f"Error saving message history: {e}")
    
    async def get_message_history(self, session_id: str, limit: int = 100) -> list:
        """Get message history from Redis."""
        if not self.redis:
            return []
        
        try:
            key = f"session:{session_id}:messages"
            messages = await self.redis.lrange(key, 0, limit - 1)
            return [json.loads(msg) for msg in messages]
        except Exception as e:
            print(f"Error getting message history: {e}")
            return []
```

#### Main Server Implementation

**Complete FastAPI Application:**
```python
# server/api_server.py (main implementation)
import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .config import ServerSettings
from .session_manager import SessionManager
from .websocket_manager import WebSocketManager  
from .models import SessionCreateRequest, SessionResponse, MessageRequest, StatusResponse
from .exceptions import SessionNotFoundError, SessionLimitError
from .security import rate_limit_middleware, APIKeyAuth
from .logging_config import setup_logging
from .persistence import SessionPersistence

# Global managers
session_manager: Optional[SessionManager] = None
websocket_manager: Optional[WebSocketManager] = None  
settings: Optional[ServerSettings] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global session_manager, websocket_manager, settings
    
    # Startup
    settings = ServerSettings()
    setup_logging(settings.log_level)
    
    session_manager = SessionManager(
        max_sessions=settings.max_sessions,
        session_timeout=settings.session_timeout
    )
    websocket_manager = WebSocketManager(session_manager)
    
    await session_manager.start()
    
    yield
    
    # Shutdown
    if session_manager:
        await session_manager.stop()

# Create FastAPI app
app = FastAPI(
    title="KageBunshin Backend API",
    description="Backend API server for KageBunshin frontend",
    version="1.0.0",
    lifespan=lifespan
)

# Configure middleware
settings_instance = ServerSettings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_instance.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.middleware("http")(rate_limit_middleware)

# Optional API key auth
api_key_auth = APIKeyAuth(getattr(settings_instance, 'api_key', None))

# REST API Endpoints
@app.post("/api/session", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    auth: Optional[str] = Depends(api_key_auth)
):
    """Create a new KageBunshin session."""
    try:
        session = await session_manager.create_session(
            session_name=request.session_name,
            browser_config=request.browser_config
        )
        return session_manager.get_session_info(session.session_id)
    
    except SessionLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session creation failed: {e}")

@app.get("/api/session/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    auth: Optional[str] = Depends(api_key_auth)
):
    """Get session information."""
    try:
        return session_manager.get_session_info(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/api/session/{session_id}")
async def delete_session(
    session_id: str,
    auth: Optional[str] = Depends(api_key_auth)
):
    """Close and delete a session."""
    try:
        await session_manager.close_session(session_id)
        return {"message": f"Session {session_id} closed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{session_id}", response_model=StatusResponse)
async def get_status(
    session_id: str,
    auth: Optional[str] = Depends(api_key_auth)
):
    """Get current session status."""
    try:
        session = await session_manager.get_session(session_id)
        
        # Get detailed browser status
        browser_status = {}
        if hasattr(session.state_manager, 'page') and session.state_manager.page:
            try:
                browser_status = {
                    "current_url": session.state_manager.page.url,
                    "page_title": await session.state_manager.page.title()
                }
            except:
                pass
        
        return StatusResponse(
            session_id=session_id,
            status=session.status,
            browser_active=hasattr(session.state_manager, 'context') and session.state_manager.context is not None,
            current_url=browser_status.get("current_url"),
            page_title=browser_status.get("page_title"),
            action_count=session.message_count,
            uptime_seconds=(datetime.now() - session.created_at).total_seconds()
        )
        
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_sessions": len(session_manager.sessions),
        "timestamp": datetime.now().isoformat()
    }

# WebSocket endpoint
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Main WebSocket endpoint for streaming communication."""
    try:
        await websocket_manager.connect(websocket, session_id)
        
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle message
                await websocket_manager.handle_message(websocket, session_id, message)
                
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON message"
                }))
            except Exception as e:
                await websocket.send_text(json.dumps({
                    "type": "error", 
                    "message": str(e)
                }))
                
    except Exception as e:
        print(f"WebSocket connection error: {e}")
    finally:
        await websocket_manager.disconnect(websocket, session_id)

# Development server runner
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api_server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
```

#### Deployment Configuration

**Docker Configuration:**
```dockerfile
# server/Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright browsers
RUN pip install playwright && playwright install chromium

WORKDIR /app

# Copy requirements and install Python dependencies  
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY . .

# Expose port
EXPOSE 8000

# Run server
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Production ASGI Configuration:**
```python
# server/gunicorn.conf.py
bind = "0.0.0.0:8000"
workers = 1  # Single worker due to Playwright browser context
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 0
max_requests_jitter = 0
timeout = 300
keepalive = 2
preload_app = True
```

### Frontend Architecture

**Technology Stack:**
- React 18 + TypeScript + Vite
- TailwindCSS for styling
- WebSocket client for real-time communication
- Local storage for session persistence

**Core Architecture Patterns:**

#### State Management Pattern
```typescript
// Global State Structure
interface AppState {
  session: SessionState;
  messages: MessageHistory;
  status: AgentStatus;
  ui: UIState;
}

// Context-based state management with useReducer
interface AppContextType {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
  websocket: WebSocketService;
}
```

#### Component Hierarchy & Props Flow
```
App.tsx (Context Provider)
├── Layout.tsx
│   ├── Header.tsx
│   │   ├── SessionControls (new/restart/clear)
│   │   └── StatusIndicator (connection/agent status)  
│   └── ChatInterface.tsx
│       ├── StatusPanel.tsx
│       │   ├── SessionInfo.tsx
│       │   ├── ActionCounter.tsx
│       │   └── BrowserStatus.tsx
│       ├── MessageList.tsx
│       │   ├── MessageGroup.tsx (groups by timestamp)
│       │   └── MessageBubble.tsx
│       │       ├── MessageContent.tsx
│       │       ├── ToolCallDisplay.tsx
│       │       └── MessageActions.tsx (copy/etc)
│       ├── StreamingMessage.tsx (active/pending messages)
│       └── InputBar.tsx
│           ├── TextArea.tsx (auto-resize, history)
│           └── InputControls.tsx (send/clear buttons)
```

#### TypeScript Interface Architecture
```typescript
// Core Message System
interface BaseMessage {
  id: string;
  timestamp: Date;
  sessionId: string;
  type: MessageType;
}

interface UserMessage extends BaseMessage {
  type: 'user';
  content: string;
  inputHistory?: number; // For navigation
}

interface AgentMessage extends BaseMessage {
  type: 'agent' | 'tool' | 'system' | 'error';
  content: string;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
  streamingContent?: string;
  metadata?: MessageMetadata;
}

interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  result?: any;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  timestamp: Date;
}

interface MessageMetadata {
  stepNumber?: number;
  emoji?: string;
  phase?: string;
  url?: string;
  duration?: number;
}
```

#### Data Flow Architecture
```typescript
// Unidirectional data flow pattern
WebSocket → MessageQueue → StateReducer → React Components → UI Updates
                ↑                                      ↓
        ReconnectionHandler ← NetworkLayer ← User Interactions
```

#### State Management Patterns
```typescript
// useReducer-based state management for complex state transitions
const [state, dispatch] = useReducer(appReducer, initialState);

// Custom hooks for feature-specific state
const useMessageHistory = () => {
  const { state, dispatch } = useAppContext();
  
  const addMessage = useCallback((message: Message) => {
    dispatch({ type: 'ADD_MESSAGE', payload: message });
  }, [dispatch]);
  
  const updateStreamingMessage = useCallback((id: string, content: string) => {
    dispatch({ type: 'UPDATE_STREAMING_MESSAGE', payload: { id, content } });
  }, [dispatch]);
  
  return { messages: state.messages, addMessage, updateStreamingMessage };
};
```

#### Component Lifecycle & Performance Optimization
```typescript
// Virtualization for large message lists
const MessageList: React.FC<MessageListProps> = ({ messages }) => {
  const listRef = useRef<HTMLDivElement>(null);
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 50 });
  
  // Auto-scroll management
  const shouldAutoScroll = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  
  // Memoized message rendering
  const renderedMessages = useMemo(() => 
    messages.slice(visibleRange.start, visibleRange.end).map(message => 
      <MessageBubble key={message.id} message={message} />
    ), [messages, visibleRange]);
  
  // Intersection Observer for auto-scroll detection
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => setIsAtBottom(entry.isIntersecting),
      { root: listRef.current, threshold: 1.0 }
    );
    // Implementation...
  }, []);
  
  return (
    <div ref={listRef} className="message-list">
      {renderedMessages}
    </div>
  );
};
```

#### Event Handling & User Interaction Patterns
```typescript
// Input handling with keyboard shortcuts
interface InputBarProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

const InputBar: React.FC<InputBarProps> = ({ onSubmit, disabled, placeholder }) => {
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Enter to submit (Shift+Enter for newline)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
    
    // History navigation with arrow keys
    if (e.key === 'ArrowUp' && e.ctrlKey) {
      e.preventDefault();
      navigateHistory('up');
    }
    
    if (e.key === 'ArrowDown' && e.ctrlKey) {
      e.preventDefault();
      navigateHistory('down');
    }
  }, [input, history, historyIndex]);
  
  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);
  
  return (
    <div className="input-bar">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        className="input-textarea"
      />
      <button onClick={handleSubmit} disabled={disabled || !input.trim()}>
        Send
      </button>
    </div>
  );
};
```

#### Styling Architecture with TailwindCSS
```typescript
// Design system configuration
const theme = {
  colors: {
    primary: {
      bg: '#ffffff',
      text: '#121414',
      border: '#e5e7eb',
    },
    accent: {
      success: '#22c55e',
      warning: '#f59e0b', 
      error: '#ef4444',
      tool: '#3b82f6',
      system: '#6b7280',
    }
  },
  typography: {
    fontFamily: {
      sans: ['Inter', 'system-ui', 'sans-serif'],
      mono: ['JetBrains Mono', 'Courier New', 'monospace'],
    },
    fontSize: {
      'header': '1.5rem',
      'body': '1rem',
      'code': '0.875rem',
      'small': '0.75rem',
    }
  }
};

// Component styling patterns
const messageStyles = {
  base: 'p-4 border-b border-gray-100 hover:bg-gray-50 transition-colors',
  user: 'bg-blue-50 border-l-4 border-l-blue-500',
  agent: 'bg-gray-50',
  tool: 'bg-yellow-50 border-l-4 border-l-yellow-500',
  error: 'bg-red-50 border-l-4 border-l-red-500',
  system: 'bg-gray-100 text-gray-600 text-sm',
};
```

#### Accessibility Considerations
```typescript
// ARIA labels and semantic HTML
interface AccessibilityProps {
  ariaLabel?: string;
  ariaDescribedBy?: string;
  role?: string;
}

const MessageBubble: React.FC<MessageBubbleProps & AccessibilityProps> = ({
  message,
  ariaLabel,
  ...accessibilityProps
}) => {
  return (
    <div
      role="article"
      aria-label={ariaLabel || `${message.type} message from ${message.timestamp}`}
      tabIndex={0}
      className="message-bubble focus:outline-none focus:ring-2 focus:ring-blue-500"
      {...accessibilityProps}
    >
      {/* Message content with proper heading hierarchy */}
      <header className="message-header">
        <h3 className="sr-only">
          {message.type === 'user' ? 'User message' : 'Agent response'}
        </h3>
        <time dateTime={message.timestamp.toISOString()}>
          {formatTimestamp(message.timestamp)}
        </time>
      </header>
      
      <div className="message-content" aria-live="polite">
        {message.content}
      </div>
      
      {message.toolCalls && (
        <div className="tool-calls" role="region" aria-label="Tool executions">
          {message.toolCalls.map(toolCall => (
            <ToolCallDisplay key={toolCall.id} toolCall={toolCall} />
          ))}
        </div>
      )}
    </div>
  );
};

// Keyboard navigation support
const useKeyboardNavigation = (messages: Message[]) => {
  const [focusedIndex, setFocusedIndex] = useState(-1);
  
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'j' && e.ctrlKey) {
        e.preventDefault();
        setFocusedIndex(prev => Math.min(prev + 1, messages.length - 1));
      }
      if (e.key === 'k' && e.ctrlKey) {
        e.preventDefault(); 
        setFocusedIndex(prev => Math.max(prev - 1, 0));
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [messages.length]);
  
  return focusedIndex;
};
```

#### WebSocket Integration Architecture
```typescript
// WebSocket service with reconnection and error handling
class WebSocketService {
  private ws: WebSocket | null = null;
  private messageQueue: QueuedMessage[] = [];
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  
  connect(sessionId: string, onMessage: MessageHandler, onStatusChange: StatusHandler) {
    const wsUrl = `${import.meta.env.VITE_WS_BASE_URL}/ws/${sessionId}`;
    
    this.ws = new WebSocket(wsUrl);
    
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      onStatusChange({ connected: true, reconnecting: false });
      this.flushMessageQueue();
    };
    
    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
    
    this.ws.onclose = (event) => {
      if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.attemptReconnect(sessionId, onMessage, onStatusChange);
      } else {
        onStatusChange({ connected: false, reconnecting: false });
      }
    };
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      onStatusChange({ connected: false, error: true });
    };
  }
  
  private attemptReconnect(sessionId: string, onMessage: MessageHandler, onStatusChange: StatusHandler) {
    this.reconnectAttempts++;
    onStatusChange({ connected: false, reconnecting: true });
    
    setTimeout(() => {
      this.connect(sessionId, onMessage, onStatusChange);
    }, this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1));
  }
}

### Key Components Structure

```
src/
├── components/
│   ├── chat/
│   │   ├── ChatInterface.tsx      # Main chat container
│   │   ├── MessageList.tsx        # Virtualized message list
│   │   ├── StreamingMessage.tsx   # Real-time streaming display
│   │   ├── InputBar.tsx           # Command input with history
│   │   ├── MessageBubble.tsx      # Individual message rendering
│   │   ├── MessageGroup.tsx       # Grouped messages by time
│   │   ├── MessageContent.tsx     # Message content rendering
│   │   ├── ToolCallDisplay.tsx    # Tool call visualization
│   │   └── MessageActions.tsx     # Copy/share message actions
│   ├── status/
│   │   ├── StatusPanel.tsx        # Agent/browser status panel
│   │   ├── SessionInfo.tsx        # Session details display
│   │   ├── ActionCounter.tsx      # Step counter with emojis
│   │   ├── BrowserStatus.tsx      # Browser state indicators
│   │   └── ConnectionStatus.tsx   # WebSocket connection status
│   ├── layout/
│   │   ├── Header.tsx             # App header with navigation
│   │   ├── Layout.tsx             # Main application layout
│   │   ├── Sidebar.tsx            # Optional session sidebar
│   │   └── Footer.tsx             # Status footer
│   ├── ui/
│   │   ├── Button.tsx             # Reusable button component
│   │   ├── TextArea.tsx           # Auto-resize text input
│   │   ├── Loading.tsx            # Loading states
│   │   ├── ErrorBoundary.tsx      # Error boundary wrapper
│   │   └── Toast.tsx              # Toast notifications
│   └── accessibility/
│       ├── ScreenReader.tsx       # Screen reader announcements
│       └── FocusManager.tsx       # Focus management utilities
├── services/
│   ├── websocket.ts               # WebSocket service class
│   ├── session.ts                 # Session management API
│   ├── message.ts                 # Message processing utilities
│   ├── storage.ts                 # Local storage management
│   └── api.ts                     # REST API client
├── types/
│   ├── api.ts                     # API interfaces
│   ├── message.ts                 # Message type definitions
│   ├── session.ts                 # Session interfaces
│   ├── state.ts                   # Application state types
│   └── websocket.ts               # WebSocket message types
├── hooks/
│   ├── useWebSocket.ts            # WebSocket connection management
│   ├── useSession.ts              # Session lifecycle hooks
│   ├── useMessageHistory.ts       # Message history management
│   ├── useLocalStorage.ts         # Persistent storage hook
│   ├── useAutoScroll.ts           # Auto-scroll behavior
│   ├── useKeyboardShortcuts.ts    # Keyboard navigation
│   └── usePerformance.ts          # Performance monitoring
├── context/
│   ├── AppContext.tsx             # Global application context
│   ├── SessionContext.tsx         # Session-specific context
│   └── ThemeContext.tsx           # Theme/styling context
├── utils/
│   ├── formatting.ts              # Text/date formatting utilities
│   ├── colors.ts                  # Color scheme constants
│   ├── constants.ts               # Application constants
│   ├── validation.ts              # Input validation helpers
│   ├── accessibility.ts           # A11y helper functions
│   └── performance.ts             # Performance utilities
└── styles/
    ├── globals.css                # Global styles and Tailwind
    ├── components.css             # Component-specific styles
    └── animations.css             # CSS animations
```

#### Detailed Component Specifications

**Core Chat Components:**

```typescript
// ChatInterface.tsx - Main orchestrator component
interface ChatInterfaceProps {
  sessionId: string;
  className?: string;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ sessionId, className }) => {
  const { messages, isLoading } = useMessageHistory(sessionId);
  const { status } = useSession(sessionId);
  const { sendMessage } = useWebSocket(sessionId);
  
  return (
    <div className={`chat-interface ${className}`}>
      <StatusPanel session={status} />
      <MessageList 
        messages={messages}
        isLoading={isLoading}
        sessionId={sessionId}
      />
      <InputBar 
        onSubmit={sendMessage}
        disabled={!status.connected || isLoading}
        placeholder="Enter your message..."
      />
    </div>
  );
};
```

```typescript
// MessageList.tsx - Virtualized message container
interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  sessionId: string;
  className?: string;
}

export const MessageList: React.FC<MessageListProps> = ({ 
  messages, 
  isLoading, 
  sessionId,
  className 
}) => {
  const listRef = useRef<HTMLDivElement>(null);
  const { isAtBottom, scrollToBottom } = useAutoScroll(listRef);
  const focusedIndex = useKeyboardNavigation(messages);
  
  // Virtualization for performance with large message lists
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 50 });
  
  const renderedMessages = useMemo(() => {
    return messages
      .slice(visibleRange.start, visibleRange.end)
      .map((message, index) => (
        <MessageBubble
          key={message.id}
          message={message}
          focused={index === focusedIndex}
          onFocus={() => setFocusedIndex(index)}
        />
      ));
  }, [messages, visibleRange, focusedIndex]);
  
  return (
    <div
      ref={listRef}
      className={`message-list ${className}`}
      role="log"
      aria-label="Chat messages"
      aria-live="polite"
    >
      {renderedMessages}
      {isLoading && <StreamingMessage sessionId={sessionId} />}
      <div className="message-list-anchor" />
    </div>
  );
};
```

```typescript
// StreamingMessage.tsx - Real-time message display
interface StreamingMessageProps {
  sessionId: string;
  className?: string;
}

export const StreamingMessage: React.FC<StreamingMessageProps> = ({ 
  sessionId, 
  className 
}) => {
  const [streamingContent, setStreamingContent] = useState('');
  const [currentTool, setCurrentTool] = useState<ToolCall | null>(null);
  const { websocket } = useWebSocket(sessionId);
  
  useEffect(() => {
    const handleStreamChunk = (chunk: StreamChunk) => {
      if (chunk.agent?.messages) {
        const latestMessage = chunk.agent.messages[chunk.agent.messages.length - 1];
        setStreamingContent(latestMessage.content);
        
        if (latestMessage.tool_calls && latestMessage.tool_calls.length > 0) {
          setCurrentTool({
            id: crypto.randomUUID(),
            name: latestMessage.tool_calls[0].name,
            args: latestMessage.tool_calls[0].args,
            status: 'executing',
            timestamp: new Date(),
          });
        }
      }
    };
    
    websocket?.addEventListener('message', handleStreamChunk);
    return () => websocket?.removeEventListener('message', handleStreamChunk);
  }, [websocket]);
  
  return (
    <div className={`streaming-message ${className}`} aria-live="assertive">
      {streamingContent && (
        <MessageBubble
          message={{
            id: 'streaming',
            type: 'agent',
            content: streamingContent,
            timestamp: new Date(),
            sessionId,
            isStreaming: true,
            toolCalls: currentTool ? [currentTool] : undefined,
          }}
        />
      )}
    </div>
  );
};
```

```typescript
// ToolCallDisplay.tsx - Tool execution visualization
interface ToolCallDisplayProps {
  toolCall: ToolCall;
  compact?: boolean;
}

export const ToolCallDisplay: React.FC<ToolCallDisplayProps> = ({ 
  toolCall, 
  compact = false 
}) => {
  const statusIcon = {
    pending: '⏳',
    executing: '⚡',
    completed: '✅',
    failed: '❌',
  };
  
  const statusColor = {
    pending: 'text-yellow-600',
    executing: 'text-blue-600',
    completed: 'text-green-600',
    failed: 'text-red-600',
  };
  
  return (
    <div 
      className="tool-call-display border-l-4 border-l-blue-500 pl-4 py-2 bg-blue-50"
      role="region"
      aria-label={`Tool call: ${toolCall.name}`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-lg ${statusColor[toolCall.status]}`}>
          {statusIcon[toolCall.status]}
        </span>
        <h4 className="font-mono text-sm font-semibold">
          {toolCall.name}
        </h4>
        <time className="text-xs text-gray-500">
          {formatTimestamp(toolCall.timestamp)}
        </time>
      </div>
      
      {!compact && (
        <>
          <details className="mb-2">
            <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-800">
              Arguments
            </summary>
            <pre className="mt-2 p-2 bg-gray-100 rounded text-xs overflow-x-auto">
              {JSON.stringify(toolCall.args, null, 2)}
            </pre>
          </details>
          
          {toolCall.result && (
            <details>
              <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-800">
                Result
              </summary>
              <pre className="mt-2 p-2 bg-gray-100 rounded text-xs overflow-x-auto">
                {typeof toolCall.result === 'string' 
                  ? toolCall.result 
                  : JSON.stringify(toolCall.result, null, 2)}
              </pre>
            </details>
          )}
        </>
      )}
    </div>
  );
};
```

**Status and Information Components:**

```typescript
// StatusPanel.tsx - Comprehensive status display
interface StatusPanelProps {
  session: SessionState;
  className?: string;
}

export const StatusPanel: React.FC<StatusPanelProps> = ({ session, className }) => {
  const { connectionStatus } = useWebSocket(session.id);
  
  return (
    <div className={`status-panel border-b border-gray-200 p-4 ${className}`}>
      <div className="flex items-center justify-between">
        <SessionInfo session={session} />
        <div className="flex items-center gap-4">
          <ActionCounter count={session.actionCount} />
          <BrowserStatus status={session.browserStatus} />
          <ConnectionStatus status={connectionStatus} />
        </div>
      </div>
    </div>
  );
};
```

```typescript
// ActionCounter.tsx - Step counter with visual feedback
interface ActionCounterProps {
  count: number;
  maxSteps?: number;
}

export const ActionCounter: React.FC<ActionCounterProps> = ({ count, maxSteps }) => {
  const progress = maxSteps ? (count / maxSteps) * 100 : null;
  
  return (
    <div 
      className="action-counter flex items-center gap-2"
      role="status"
      aria-label={`${count} actions completed`}
    >
      <span className="text-2xl">📋</span>
      <div className="text-sm">
        <span className="font-semibold">{count}</span>
        <span className="text-gray-500"> actions</span>
      </div>
      {progress !== null && (
        <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div 
            className="h-full bg-blue-500 transition-all duration-300"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
};
```

**Service Layer Architecture:**

```typescript
// services/session.ts - Session management
export class SessionManager {
  private sessions = new Map<string, SessionState>();
  
  async createSession(): Promise<SessionState> {
    const sessionId = crypto.randomUUID();
    const session: SessionState = {
      id: sessionId,
      created: new Date(),
      actionCount: 0,
      browserStatus: {
        connected: false,
        currentUrl: null,
        pageTitle: null,
      },
      connected: false,
    };
    
    this.sessions.set(sessionId, session);
    await this.persistSession(session);
    
    return session;
  }
  
  private async persistSession(session: SessionState) {
    localStorage.setItem(`session_${session.id}`, JSON.stringify(session));
  }
  
  async restoreSession(sessionId: string): Promise<SessionState | null> {
    const stored = localStorage.getItem(`session_${sessionId}`);
    if (stored) {
      const session = JSON.parse(stored) as SessionState;
      this.sessions.set(sessionId, session);
      return session;
    }
    return null;
  }
}
```

**Custom Hooks Architecture:**

```typescript
// hooks/useAutoScroll.ts - Smart auto-scrolling behavior  
export const useAutoScroll = (containerRef: RefObject<HTMLElement>) => {
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  
  const scrollToBottom = useCallback(() => {
    if (containerRef.current && shouldAutoScroll) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [containerRef, shouldAutoScroll]);
  
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    
    const handleScroll = () => {
      const isScrolledToBottom = 
        container.scrollHeight - container.scrollTop <= container.clientHeight + 5;
      setIsAtBottom(isScrolledToBottom);
      setShouldAutoScroll(isScrolledToBottom);
    };
    
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [containerRef]);
  
  return { isAtBottom, scrollToBottom, shouldAutoScroll, setShouldAutoScroll };
};
```

```typescript
// hooks/useKeyboardShortcuts.ts - Global keyboard navigation
export const useKeyboardShortcuts = () => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + Enter to send message
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        document.dispatchEvent(new CustomEvent('submit-message'));
      }
      
      // Escape to cancel current action
      if (e.key === 'Escape') {
        document.dispatchEvent(new CustomEvent('cancel-action'));
      }
      
      // Ctrl/Cmd + K to focus search
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.dispatchEvent(new CustomEvent('focus-input'));
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);
};
```

## Detailed Implementation Plan

### Phase 1: Project Setup & Basic Structure
1. **Initialize Vite + React + TypeScript project**
   - Create `frontend/` directory
   - Setup Vite with React template
   - Configure TypeScript with strict settings
   - Install and configure TailwindCSS
   - Setup black/white color scheme

2. **Backend API Server**
   - Create FastAPI server in `server/api_server.py`
   - Implement WebSocket endpoint for streaming
   - Wrap KageBunshinAgent with proper session management
   - Add CORS configuration for frontend

### Phase 2: Core Chat Interface
1. **Basic Chat Components**
   - ChatInterface: Main container with input/output areas
   - MessageList: Scrollable container for message history
   - InputBar: Multi-line input with submit handling
   - MessageBubble: Individual message rendering

2. **WebSocket Integration**
   - WebSocket client service with React hooks integration
   - Connection management with exponential backoff reconnection
   - Message parsing and routing for different chunk types
   - Connection health monitoring and status indication
   - Message buffering and ordering for reliable streaming
   - Session synchronization with WebSocket connection lifecycle

### Phase 3: Advanced Features
1. **Streaming Message Display**
   - Real-time message updates with React state reconciliation
   - Incremental content building for partial message chunks
   - Tool call visualization with interactive execution badges
   - Step-by-step progress indication with animation
   - Message type-aware formatting and styling
   - Smooth auto-scrolling with user scroll preservation
   - Message virtualization for performance with large histories

2. **Session Management & State Persistence**
   - Session lifecycle management (creation, persistence, cleanup)
   - Local storage strategies and data serialization
   - State synchronization between frontend and backend
   - Browser tab management and session recovery
   - Performance optimization for large session data
   - Data migration and versioning strategies

### Phase 4: Status & Monitoring
1. **Status Panel Implementation**
   - Current URL and page title display
   - Action counter with step tracking
   - Browser state indicators
   - Agent activity status

2. **Enhanced User Experience**
   - Input history with up/down navigation
   - Keyboard shortcuts (Enter to send, Shift+Enter for newline)
   - Auto-scroll to latest messages
   - Copy functionality for messages

## Message Types & Formatting

### CLI Message Types to Replicate
```typescript
interface MessageType {
  INIT: "🚀"      // Browser/agent initialization
  TOOL: "🔧"      // Tool execution
  MESSAGE: "💬"   // Agent messages
  ANSWER: "✅"    // Final answers
  ERROR: "❌"     // Error states
  PHASE: "📋"     // Phase transitions
  OBSERVATION: "👀" // Observations
  DIALOG: "📢"    // Dialog interactions
  SUCCESS: "🎯"   // Success indicators
}
```

### Streaming Chunk Structure
Based on `KageBunshinAgent.astream()`:
```typescript
interface StreamChunk {
  agent?: {
    messages: Array<{
      content: string;
      tool_calls?: Array<{
        name: string;
        args: Record<string, any>;
      }>;
    }>;
  };
  summarizer?: {
    messages: Array<{
      content: string;
    }>;
  };
}
```

## Design System

### Core Design Principles
- **Minimalism**: Clean, uncluttered interface focusing on functionality
- **Accessibility First**: WCAG 2.1 AA compliance with keyboard navigation
- **Performance**: Lightweight animations and optimized rendering
- **Consistency**: Unified design language across all components
- **Clarity**: Clear visual hierarchy and information architecture

### Color Palette & CSS Custom Properties

#### Primary Colors
```css
:root {
  /* Primary colors */
  --color-bg-primary: #ffffff;
  --color-text-primary: #121414;
  --color-text-secondary: #4a5568;
  --color-text-muted: #718096;
  
  /* Surface colors */
  --color-bg-secondary: #f7fafc;
  --color-bg-elevated: #ffffff;
  --color-border-subtle: #e2e8f0;
  --color-border-default: #cbd5e0;
  
  /* Interactive states */
  --color-bg-hover: #f1f5f9;
  --color-bg-active: #e2e8f0;
  --color-bg-focus: #ddd6fe;
}
```

#### Semantic Colors
```css
:root {
  /* Status colors */
  --color-success: #22c55e;
  --color-success-bg: #dcfce7;
  --color-success-border: #86efac;
  
  --color-warning: #f59e0b;
  --color-warning-bg: #fef3c7;
  --color-warning-border: #fcd34d;
  
  --color-error: #ef4444;
  --color-error-bg: #fee2e2;
  --color-error-border: #fca5a5;
  
  --color-info: #3b82f6;
  --color-info-bg: #dbeafe;
  --color-info-border: #93c5fd;
  
  --color-tool: #8b5cf6;
  --color-tool-bg: #f3e8ff;
  --color-tool-border: #c4b5fd;
}
```

### TailwindCSS Configuration

#### Complete tailwind.config.js
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Primary palette
        primary: {
          50: '#f8fafc',
          100: '#f1f5f9',
          500: '#64748b',
          900: '#121414',
        },
        // Semantic colors
        success: '#22c55e',
        warning: '#f59e0b',
        error: '#ef4444',
        tool: '#8b5cf6',
        info: '#3b82f6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.875rem', { lineHeight: '1.25rem' }],
        base: ['1rem', { lineHeight: '1.5rem' }],
        lg: ['1.125rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
      },
      spacing: {
        18: '4.5rem',
        88: '22rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-subtle': 'pulseSubtle 2s infinite',
        'typing': 'typing 1s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        pulseSubtle: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.8' },
        },
        typing: {
          '0%': { opacity: '0.4' },
          '50%': { opacity: '1' },
          '100%': { opacity: '0.4' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
```

### Typography System

#### Font Loading Strategy
```css
/* Preload critical fonts */
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

#### Typography Scale
```css
.text-display-lg {
  @apply text-2xl font-semibold tracking-tight;
}
.text-display-base {
  @apply text-xl font-semibold tracking-tight;
}
.text-body-lg {
  @apply text-lg font-normal leading-relaxed;
}
.text-body-base {
  @apply text-base font-normal leading-normal;
}
.text-body-sm {
  @apply text-sm font-normal leading-tight;
}
.text-caption {
  @apply text-xs font-medium tracking-wide uppercase;
}
.text-code {
  @apply font-mono text-sm leading-tight;
}
```

### Component Styling Guidelines

#### Layout Components
```css
/* Main Layout */
.layout-container {
  @apply min-h-screen bg-white flex flex-col;
}

.layout-header {
  @apply border-b border-gray-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10;
}

.layout-main {
  @apply flex-1 flex overflow-hidden;
}

.layout-sidebar {
  @apply w-64 bg-gray-50 border-r border-gray-200 overflow-y-auto;
}

.layout-content {
  @apply flex-1 overflow-hidden flex flex-col;
}
```

#### Chat Interface Components
```css
/* Chat Container */
.chat-container {
  @apply flex flex-col h-full bg-white;
}

.chat-messages {
  @apply flex-1 overflow-y-auto px-4 py-6 space-y-4;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e0 transparent;
}

.chat-input-area {
  @apply border-t border-gray-200 bg-white p-4;
}

/* Message Bubbles */
.message-bubble {
  @apply rounded-lg px-4 py-3 max-w-4xl animate-slide-up;
}

.message-user {
  @apply bg-gray-50 border border-gray-200 ml-12;
}

.message-assistant {
  @apply bg-white border border-gray-100 mr-12;
}

.message-system {
  @apply bg-blue-50 border border-blue-200 text-blue-800;
}

.message-tool {
  @apply bg-purple-50 border border-purple-200 text-purple-800;
}

.message-error {
  @apply bg-red-50 border border-red-200 text-red-800;
}
```

#### Form Components
```css
/* Input Fields */
.input-base {
  @apply w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm;
  @apply focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500;
  @apply placeholder-gray-400 text-gray-900 bg-white;
}

.input-textarea {
  @apply input-base resize-none min-h-[2.5rem] max-h-32;
}

/* Buttons */
.btn-base {
  @apply inline-flex items-center justify-center px-4 py-2 border border-transparent;
  @apply text-sm font-medium rounded-md shadow-sm cursor-pointer;
  @apply focus:outline-none focus:ring-2 focus:ring-offset-2;
  @apply disabled:opacity-50 disabled:cursor-not-allowed;
  @apply transition-colors duration-150 ease-in-out;
}

.btn-primary {
  @apply btn-base bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500;
}

.btn-secondary {
  @apply btn-base bg-gray-200 text-gray-800 hover:bg-gray-300 focus:ring-gray-500;
}

.btn-ghost {
  @apply btn-base bg-transparent text-gray-600 hover:bg-gray-100 focus:ring-gray-500;
}
```

### Animation & Transition Specifications

#### Micro-interactions
```css
/* Hover Effects */
.hover-lift {
  @apply transition-transform duration-150 ease-out hover:-translate-y-0.5;
}

.hover-glow {
  @apply transition-shadow duration-200 ease-out hover:shadow-md;
}

/* Loading States */
.loading-pulse {
  @apply animate-pulse bg-gradient-to-r from-gray-200 via-gray-300 to-gray-200;
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

/* Typing Indicator */
.typing-indicator::after {
  content: '';
  @apply inline-block w-1 h-4 bg-gray-400 animate-typing ml-1;
}
```

#### Page Transitions
```css
.page-enter {
  @apply opacity-0 translate-y-4;
}

.page-enter-active {
  @apply opacity-100 translate-y-0 transition-all duration-300 ease-out;
}

.page-exit {
  @apply opacity-100 translate-y-0;
}

.page-exit-active {
  @apply opacity-0 -translate-y-4 transition-all duration-200 ease-in;
}
```

### Responsive Design Breakpoints

#### Mobile-First Approach
```css
/* Custom breakpoints */
@screen xs {
  /* 475px and up */
}

@screen sm {
  /* 640px and up - Small tablets */
}

@screen md {
  /* 768px and up - Large tablets */
}

@screen lg {
  /* 1024px and up - Laptops */
}

@screen xl {
  /* 1280px and up - Desktops */
}

@screen 2xl {
  /* 1536px and up - Large desktops */
}
```

#### Component Responsive Behavior
```css
/* Chat Interface Responsive */
.chat-container {
  @apply px-2 sm:px-4 lg:px-6;
}

.message-bubble {
  @apply max-w-full sm:max-w-2xl lg:max-w-4xl;
}

.chat-input-area {
  @apply p-2 sm:p-4;
}

/* Navigation Responsive */
.layout-sidebar {
  @apply hidden lg:block lg:w-64 xl:w-72;
}

.mobile-nav {
  @apply lg:hidden fixed inset-0 z-50 bg-gray-900/50;
}
```

### Accessibility Standards (WCAG 2.1 AA)

#### Color Contrast Requirements
```css
/* Ensure 4.5:1 contrast ratio for normal text */
.text-high-contrast {
  color: #121414; /* 15.8:1 ratio on white */
}

.text-medium-contrast {
  color: #374151; /* 8.9:1 ratio on white */
}

.text-low-contrast {
  color: #6b7280; /* 4.6:1 ratio on white */
}

/* Link contrast and focus states */
.link-accessible {
  @apply text-blue-600 underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2;
  @apply hover:text-blue-800 visited:text-purple-600;
}
```

#### Focus Management
```css
/* Skip link for keyboard navigation */
.skip-link {
  @apply absolute -top-full left-4 bg-blue-600 text-white px-4 py-2 rounded-md;
  @apply focus:top-4 transition-all duration-200 z-50;
}

/* Focus trap for modals */
.focus-trap {
  @apply focus-within:outline-none focus-within:ring-2 focus-within:ring-blue-500;
}

/* High-contrast focus indicators */
.focus-visible {
  @apply outline-none ring-2 ring-blue-500 ring-offset-2;
}
```

#### Screen Reader Support
```css
/* Screen reader only text */
.sr-only {
  @apply absolute w-px h-px p-0 -m-px overflow-hidden whitespace-nowrap border-0;
  clip: rect(0, 0, 0, 0);
}

.sr-only-focusable:focus {
  @apply static w-auto h-auto p-1 m-0 overflow-visible whitespace-normal;
  clip: auto;
}
```

### User Interaction Patterns

#### Loading States
```typescript
// Loading state component patterns
interface LoadingState {
  skeleton: 'pulse' | 'shimmer' | 'dots';
  message: string;
  progress?: number;
}

// Usage examples:
// - Message loading: shimmer skeleton
// - Tool execution: dots with progress
// - Page transitions: pulse skeleton
```

#### Feedback Patterns
```css
/* Success feedback */
.feedback-success {
  @apply bg-green-50 border-green-200 text-green-800 px-4 py-3 rounded-lg;
  @apply animate-slide-up;
}

/* Error feedback */
.feedback-error {
  @apply bg-red-50 border-red-200 text-red-800 px-4 py-3 rounded-lg;
  @apply animate-slide-up;
}

/* Toast notifications */
.toast {
  @apply fixed bottom-4 right-4 bg-white border border-gray-200 shadow-lg rounded-lg p-4;
  @apply transform translate-y-full animate-slide-up;
}

.toast-enter {
  @apply translate-y-0;
}

.toast-exit {
  @apply translate-y-full opacity-0;
}
```

### Visual Hierarchy Implementation

#### Content Hierarchy
```css
/* Page hierarchy */
.hierarchy-h1 {
  @apply text-2xl font-bold text-gray-900 mb-6;
}

.hierarchy-h2 {
  @apply text-xl font-semibold text-gray-800 mb-4;
}

.hierarchy-h3 {
  @apply text-lg font-medium text-gray-700 mb-3;
}

.hierarchy-body {
  @apply text-base text-gray-600 leading-relaxed mb-4;
}

.hierarchy-caption {
  @apply text-sm text-gray-500 font-medium;
}
```

#### Information Architecture
```css
/* Primary actions */
.action-primary {
  @apply bg-blue-600 text-white font-medium px-6 py-2 rounded-lg;
  @apply hover:bg-blue-700 focus:ring-2 focus:ring-blue-500;
}

/* Secondary actions */
.action-secondary {
  @apply bg-gray-100 text-gray-700 font-medium px-4 py-2 rounded-md;
  @apply hover:bg-gray-200 focus:ring-2 focus:ring-gray-500;
}

/* Tertiary actions */
.action-tertiary {
  @apply text-blue-600 font-medium px-2 py-1 rounded;
  @apply hover:bg-blue-50 focus:ring-2 focus:ring-blue-500;
}
```

### Component State Specifications

#### Interactive States
```css
/* Button states */
.btn-state-default {
  @apply bg-white border-gray-300 text-gray-700;
}

.btn-state-hover {
  @apply bg-gray-50 border-gray-400 text-gray-800;
}

.btn-state-active {
  @apply bg-gray-100 border-gray-500 text-gray-900;
}

.btn-state-focus {
  @apply ring-2 ring-blue-500 ring-offset-2;
}

.btn-state-disabled {
  @apply bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed;
}
```

#### Data States
```css
/* Loading state */
.data-loading {
  @apply animate-pulse bg-gray-200 rounded;
}

/* Empty state */
.data-empty {
  @apply text-center py-12 text-gray-500;
}

/* Error state */
.data-error {
  @apply text-center py-8 text-red-600 bg-red-50 rounded-lg;
}
```

## API Endpoints Specification

### WebSocket Endpoints
- `WS /ws/{session_id}` - Main streaming connection
  - Send: `{type: "message", content: string}`
  - Receive: `{type: "stream", data: StreamChunk}`
  - Receive: `{type: "status", data: StatusUpdate}`
  - Receive: `{type: "error", message: string}`

### REST Endpoints
- `POST /api/session` - Create new session
- `GET /api/session/{session_id}` - Get session info
- `DELETE /api/session/{session_id}` - End session
- `GET /api/status/{session_id}` - Get current status

## WebSocket Integration Implementation

### WebSocket Client Architecture

#### Core WebSocket Service (`services/websocket.ts`)

```typescript
interface WebSocketConfig {
  url: string;
  sessionId: string;
  reconnectInterval: number;
  maxReconnectAttempts: number;
  heartbeatInterval: number;
  messageBufferSize: number;
}

interface WebSocketMessage {
  type: 'stream' | 'status' | 'error' | 'heartbeat' | 'user_input';
  data?: any;
  timestamp?: number;
  sequence?: number;
}

class KageBunshinWebSocket {
  private ws: WebSocket | null = null;
  private config: WebSocketConfig;
  private connectionState: 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';
  private messageBuffer: WebSocketMessage[] = [];
  private heartbeatTimer: NodeJS.Timer | null = null;
  private reconnectTimer: NodeJS.Timer | null = null;
  private reconnectAttempts = 0;
  private sequenceNumber = 0;
  private messageHandlers = new Map<string, (data: any) => void>();
  private stateHandlers = new Map<string, (state: string) => void>();

  connect(): Promise<void>;
  disconnect(): void;
  send(message: WebSocketMessage): void;
  onMessage(type: string, handler: (data: any) => void): void;
  onStateChange(handler: (state: string) => void): void;
  private handleReconnect(): void;
  private startHeartbeat(): void;
  private handleMessage(event: MessageEvent): void;
}
```

#### React Hook Integration (`hooks/useWebSocket.ts`)

```typescript
interface UseWebSocketOptions {
  sessionId: string;
  autoConnect?: boolean;
  reconnectOnError?: boolean;
  bufferMessages?: boolean;
}

interface WebSocketHookReturn {
  connectionState: 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';
  lastMessage: WebSocketMessage | null;
  connect: () => void;
  disconnect: () => void;
  sendMessage: (message: WebSocketMessage) => void;
  messageHistory: WebSocketMessage[];
  error: Error | null;
  isConnected: boolean;
  reconnectAttempts: number;
}

const useWebSocket = (options: UseWebSocketOptions): WebSocketHookReturn => {
  // Implementation with proper cleanup, state management, and error handling
  // Uses useEffect for connection lifecycle management
  // Implements exponential backoff for reconnection attempts
  // Manages message buffering during disconnection periods
  // Provides connection health monitoring with heartbeat mechanism
};
```

### Connection Management Strategies

#### Exponential Backoff Reconnection

```typescript
class ReconnectionStrategy {
  private baseDelay = 1000; // 1 second
  private maxDelay = 30000; // 30 seconds
  private maxAttempts = 10;
  private backoffMultiplier = 2;

  calculateDelay(attemptNumber: number): number {
    const delay = Math.min(
      this.baseDelay * Math.pow(this.backoffMultiplier, attemptNumber),
      this.maxDelay
    );
    // Add jitter to prevent thundering herd
    return delay + Math.random() * 1000;
  }

  shouldAttemptReconnect(attemptNumber: number): boolean {
    return attemptNumber < this.maxAttempts;
  }
}
```

#### Connection Health Monitoring

```typescript
interface ConnectionHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  latency: number;
  lastHeartbeat: Date;
  messagesSent: number;
  messagesReceived: number;
  reconnectCount: number;
}

class ConnectionHealthMonitor {
  private health: ConnectionHealth;
  private heartbeatInterval = 30000; // 30 seconds
  private healthCheckCallbacks: ((health: ConnectionHealth) => void)[] = [];

  startMonitoring(): void;
  stopMonitoring(): void;
  onHealthChange(callback: (health: ConnectionHealth) => void): void;
  private sendHeartbeat(): void;
  private updateHealth(): void;
}
```

### Message Protocol Specification

#### Stream Message Types

```typescript
// Based on KageBunshinAgent.astream() output format
interface StreamChunk {
  agent?: {
    messages: Array<{
      content: string;
      tool_calls?: Array<{
        name: string;
        args: Record<string, any>;
        id?: string;
      }>;
      type?: 'ai' | 'human' | 'system' | 'tool';
      id?: string;
    }>;
  };
  summarizer?: {
    messages: Array<{
      content: string;
      type?: 'ai';
      id?: string;
    }>;
  };
}

interface StatusUpdate {
  sessionId: string;
  browserStatus: {
    currentUrl: string;
    currentTitle: string;
    actionCount: number;
    isNavigating: boolean;
  };
  agentStatus: {
    isProcessing: boolean;
    currentStep: string;
    stepCount: number;
  };
  timestamp: number;
}

interface WebSocketProtocol {
  // Client to Server Messages
  user_input: {
    content: string;
    sessionId: string;
    timestamp: number;
  };
  
  // Server to Client Messages
  stream: StreamChunk;
  status: StatusUpdate;
  error: {
    message: string;
    code?: string;
    timestamp: number;
  };
  session_created: {
    sessionId: string;
    timestamp: number;
  };
  session_ended: {
    sessionId: string;
    timestamp: number;
  };
}
```

#### Message Parsing and Routing

```typescript
class MessageRouter {
  private handlers = new Map<keyof WebSocketProtocol, Array<(data: any) => void>>();

  registerHandler<T extends keyof WebSocketProtocol>(
    type: T, 
    handler: (data: WebSocketProtocol[T]) => void
  ): void;

  unregisterHandler<T extends keyof WebSocketProtocol>(
    type: T, 
    handler: (data: WebSocketProtocol[T]) => void
  ): void;

  routeMessage(message: WebSocketMessage): void;
  
  private validateMessage(message: WebSocketMessage): boolean;
  private parseStreamChunk(data: StreamChunk): void;
  private handleStatusUpdate(data: StatusUpdate): void;
  private handleError(data: { message: string; code?: string }): void;
}
```

### Error Handling and Recovery

#### Error Categories and Responses

```typescript
enum WebSocketErrorType {
  CONNECTION_FAILED = 'connection_failed',
  CONNECTION_LOST = 'connection_lost',
  INVALID_MESSAGE = 'invalid_message',
  SESSION_EXPIRED = 'session_expired',
  SERVER_ERROR = 'server_error',
  RATE_LIMITED = 'rate_limited'
}

interface WebSocketError {
  type: WebSocketErrorType;
  message: string;
  timestamp: Date;
  canRetry: boolean;
  retryAfter?: number;
}

class ErrorHandler {
  handleError(error: WebSocketError): void {
    switch (error.type) {
      case WebSocketErrorType.CONNECTION_FAILED:
        this.handleConnectionFailure(error);
        break;
      case WebSocketErrorType.CONNECTION_LOST:
        this.handleConnectionLoss(error);
        break;
      case WebSocketErrorType.SESSION_EXPIRED:
        this.handleSessionExpiration(error);
        break;
      // ... other error types
    }
  }

  private handleConnectionFailure(error: WebSocketError): void;
  private handleConnectionLoss(error: WebSocketError): void;
  private handleSessionExpiration(error: WebSocketError): void;
}
```

## Streaming Message Display Implementation

### Streaming Display Architecture

#### Message State Management (`hooks/useStreamingMessages.ts`)

```typescript
interface StreamingMessage {
  id: string;
  type: 'agent' | 'summarizer' | 'tool_call' | 'status';
  content: string;
  isComplete: boolean;
  isStreaming: boolean;
  timestamp: Date;
  toolCalls?: ToolCall[];
  metadata?: Record<string, any>;
}

interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  result?: any;
  startTime?: Date;
  endTime?: Date;
}

const useStreamingMessages = () => {
  const [messages, setMessages] = useState<StreamingMessage[]>([]);
  const [currentStreamingMessage, setCurrentStreamingMessage] = useState<StreamingMessage | null>(null);

  const addMessage = useCallback((chunk: StreamChunk) => {
    // Handle incremental message building
    // Manage message completion detection
    // Update tool call statuses
  }, []);

  const updateCurrentMessage = useCallback((content: string) => {
    // Handle partial content updates
    // Implement smooth content transitions
  }, []);

  return {
    messages,
    currentStreamingMessage,
    addMessage,
    updateCurrentMessage,
    clearMessages: () => setMessages([]),
    getLatestMessage: () => messages[messages.length - 1],
  };
};
```

#### Incremental Content Building

```typescript
class StreamingContentBuilder {
  private contentBuffer = new Map<string, string>();
  private messageStates = new Map<string, 'building' | 'complete'>();

  buildIncrementalContent(messageId: string, newChunk: string): {
    content: string;
    isComplete: boolean;
    hasChanged: boolean;
  } {
    const currentContent = this.contentBuffer.get(messageId) || '';
    const updatedContent = currentContent + newChunk;
    
    this.contentBuffer.set(messageId, updatedContent);
    
    // Detect message completion patterns
    const isComplete = this.detectMessageCompletion(updatedContent);
    if (isComplete) {
      this.messageStates.set(messageId, 'complete');
    }

    return {
      content: updatedContent,
      isComplete,
      hasChanged: updatedContent !== currentContent
    };
  }

  private detectMessageCompletion(content: string): boolean {
    // Implement heuristics for detecting complete messages
    // Check for end-of-message markers, tool call completions, etc.
    return false; // Placeholder
  }
}
```

### Real-Time UI Updates with React

#### Streaming Message Component (`components/chat/StreamingMessage.tsx`)

```typescript
interface StreamingMessageProps {
  message: StreamingMessage;
  isActive: boolean;
  onComplete?: (message: StreamingMessage) => void;
}

const StreamingMessage: React.FC<StreamingMessageProps> = ({ 
  message, 
  isActive, 
  onComplete 
}) => {
  const [displayContent, setDisplayContent] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  
  // Implement typewriter effect for streaming content
  useEffect(() => {
    if (message.isStreaming && isActive) {
      // Animate content appearance with smooth transitions
      const animateContent = async () => {
        setIsAnimating(true);
        // Implement character-by-character or word-by-word animation
        for (let i = displayContent.length; i < message.content.length; i++) {
          setDisplayContent(message.content.substring(0, i + 1));
          await new Promise(resolve => setTimeout(resolve, 10)); // Adjust timing
        }
        setIsAnimating(false);
        if (message.isComplete) {
          onComplete?.(message);
        }
      };
      
      animateContent();
    } else {
      setDisplayContent(message.content);
    }
  }, [message.content, message.isStreaming, isActive]);

  return (
    <div className={`message ${isActive ? 'active' : ''} ${isAnimating ? 'animating' : ''}`}>
      <MessageHeader type={message.type} timestamp={message.timestamp} />
      <MessageContent content={displayContent} isStreaming={message.isStreaming} />
      {message.toolCalls && (
        <ToolCallsDisplay toolCalls={message.toolCalls} />
      )}
    </div>
  );
};
```

#### Tool Call Visualization (`components/chat/ToolCallsDisplay.tsx`)

```typescript
const ToolCallsDisplay: React.FC<{ toolCalls: ToolCall[] }> = ({ toolCalls }) => {
  return (
    <div className="tool-calls-container">
      {toolCalls.map(toolCall => (
        <ToolCallBadge
          key={toolCall.id}
          toolCall={toolCall}
          onStatusChange={(status) => handleToolStatusChange(toolCall.id, status)}
        />
      ))}
    </div>
  );
};

const ToolCallBadge: React.FC<{ 
  toolCall: ToolCall; 
  onStatusChange: (status: ToolCall['status']) => void;
}> = ({ toolCall, onStatusChange }) => {
  const statusColors = {
    pending: 'bg-yellow-100 text-yellow-800',
    executing: 'bg-blue-100 text-blue-800 animate-pulse',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800'
  };

  return (
    <div className={`tool-call-badge ${statusColors[toolCall.status]}`}>
      <span className="tool-name">{toolCall.name}</span>
      <span className="tool-status">{toolCall.status}</span>
      {toolCall.status === 'executing' && (
        <div className="execution-spinner" />
      )}
    </div>
  );
};
```

### Message Buffering and Performance Optimization

#### Message Buffer Management

```typescript
class MessageBuffer {
  private buffer: StreamChunk[] = [];
  private maxBufferSize = 1000;
  private flushThreshold = 10;
  private flushTimer: NodeJS.Timer | null = null;
  private onFlush: (chunks: StreamChunk[]) => void;

  constructor(onFlush: (chunks: StreamChunk[]) => void) {
    this.onFlush = onFlush;
  }

  addChunk(chunk: StreamChunk): void {
    this.buffer.push(chunk);
    
    if (this.buffer.length >= this.flushThreshold) {
      this.flushBuffer();
    } else {
      this.scheduleFlush();
    }
  }

  private scheduleFlush(): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
    }
    
    this.flushTimer = setTimeout(() => {
      this.flushBuffer();
    }, 100); // Flush after 100ms of inactivity
  }

  private flushBuffer(): void {
    if (this.buffer.length > 0) {
      const chunksToFlush = [...this.buffer];
      this.buffer = [];
      this.onFlush(chunksToFlush);
    }
    
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
  }

  clear(): void {
    this.buffer = [];
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
  }
}
```

#### Message Virtualization for Large Histories

```typescript
interface VirtualizedMessageListProps {
  messages: StreamingMessage[];
  height: number;
  messageHeight: number;
  overscan?: number;
}

const VirtualizedMessageList: React.FC<VirtualizedMessageListProps> = ({
  messages,
  height,
  messageHeight,
  overscan = 5
}) => {
  const [scrollTop, setScrollTop] = useState(0);
  const [isUserScrolling, setIsUserScrolling] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const visibleRange = useMemo(() => {
    const startIndex = Math.floor(scrollTop / messageHeight);
    const endIndex = Math.min(
      startIndex + Math.ceil(height / messageHeight) + overscan,
      messages.length
    );
    
    return {
      start: Math.max(0, startIndex - overscan),
      end: endIndex
    };
  }, [scrollTop, height, messageHeight, overscan, messages.length]);

  const visibleMessages = messages.slice(visibleRange.start, visibleRange.end);

  // Auto-scroll to bottom for new messages (unless user is scrolling)
  useEffect(() => {
    if (!isUserScrolling && containerRef.current) {
      const container = containerRef.current;
      const shouldAutoScroll = 
        container.scrollTop + container.clientHeight >= container.scrollHeight - 100;
      
      if (shouldAutoScroll) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }, [messages.length, isUserScrolling]);

  return (
    <div
      ref={containerRef}
      className="virtualized-message-list"
      style={{ height, overflow: 'auto' }}
      onScroll={handleScroll}
    >
      <div style={{ height: visibleRange.start * messageHeight }} />
      {visibleMessages.map((message, index) => (
        <StreamingMessage
          key={message.id}
          message={message}
          isActive={visibleRange.start + index === messages.length - 1}
        />
      ))}
      <div style={{ height: (messages.length - visibleRange.end) * messageHeight }} />
    </div>
  );
};
```

### Integration with KageBunshinAgent Format

#### Stream Chunk Processing Pipeline

```typescript
class StreamChunkProcessor {
  private messageBuilder = new StreamingContentBuilder();
  private sequenceTracker = new Map<string, number>();

  processStreamChunk(chunk: StreamChunk): ProcessedMessage[] {
    const processed: ProcessedMessage[] = [];

    // Process agent messages
    if (chunk.agent?.messages) {
      for (const message of chunk.agent.messages) {
        processed.push(this.processAgentMessage(message));
      }
    }

    // Process summarizer messages
    if (chunk.summarizer?.messages) {
      for (const message of chunk.summarizer.messages) {
        processed.push(this.processSummarizerMessage(message));
      }
    }

    return processed;
  }

  private processAgentMessage(message: any): ProcessedMessage {
    const messageId = message.id || this.generateMessageId();
    
    return {
      id: messageId,
      type: 'agent',
      content: message.content || '',
      toolCalls: message.tool_calls?.map(this.processToolCall) || [],
      timestamp: new Date(),
      isComplete: this.isMessageComplete(message),
      isStreaming: !this.isMessageComplete(message)
    };
  }

  private processToolCall(toolCall: any): ToolCall {
    return {
      id: toolCall.id || this.generateToolCallId(),
      name: toolCall.name,
      args: toolCall.args || {},
      status: 'pending',
      startTime: new Date()
    };
  }

  private isMessageComplete(message: any): boolean {
    // Implement logic to determine if a message is complete
    // This could be based on message structure, content analysis, etc.
    return !message.tool_calls || message.tool_calls.length === 0;
  }
}
```

## Development Phases

### Phase 1: Foundation & Setup (Days 1-3)

#### Day 1: Project Initialization
- [x] Analyze CLI functionality and requirements
- [ ] **Frontend Setup**
  - [ ] Create `frontend/` directory structure
  - [ ] Initialize Vite + React + TypeScript project
  - [ ] Configure TailwindCSS with black/white theme
  - [ ] Setup ESLint, Prettier for code quality
  - [ ] Configure TypeScript with strict settings
  - [ ] Setup testing environment (Vitest + React Testing Library)

#### Day 2: Backend API Foundation
- [ ] **FastAPI Server Implementation**
  - [ ] Create `server/api_server.py` with FastAPI setup
  - [ ] Implement WebSocket endpoint for streaming
  - [ ] Add session lifecycle management
  - [ ] Configure CORS for frontend communication
  - [ ] Setup proper error handling and logging
  - [ ] Create health check endpoint

#### Day 3: Core Infrastructure
- [ ] **WebSocket Communication Layer**
  - [ ] Implement WebSocket client service
  - [ ] Add connection management with auto-reconnection
  - [ ] Create message parsing and routing logic
  - [ ] Setup heartbeat mechanism for connection health
  - [ ] Implement error handling and status indication
- [ ] **Basic Testing Setup**
  - [ ] Configure Jest/Vitest for unit testing
  - [ ] Setup Playwright for E2E testing
  - [ ] Create initial test fixtures and mocks
  - [ ] Implement CI/CD pipeline skeleton

### Phase 2: Core Chat Interface (Days 4-6)

#### Day 4: Basic Chat Components
- [ ] **Core UI Components**
  - [ ] ChatInterface: Main container with layout
  - [ ] MessageList: Virtualized scrollable container
  - [ ] InputBar: Multi-line input with auto-resize
  - [ ] MessageBubble: Individual message rendering
  - [ ] StatusIndicator: Connection and agent status

#### Day 5: Message System
- [ ] **Message Handling**
  - [ ] StreamingMessage: Real-time message updates
  - [ ] Tool call visualization with badges
  - [ ] Step-by-step progress indication
  - [ ] Message type formatting (INIT, TOOL, MESSAGE, etc.)
  - [ ] Emoji integration for visual feedback

#### Day 6: Session Management
- [ ] **Session Infrastructure**
  - [ ] Session creation and persistence
  - [ ] Local storage for session continuity
  - [ ] Session cleanup and restart functionality
  - [ ] Browser state synchronization
  - [ ] Multiple session support foundation

### Phase 3: Advanced Features (Days 7-9)

#### Day 7: Streaming & Real-time Features
- [ ] **Advanced Streaming**
  - [ ] Chunk processing optimization
  - [ ] Backpressure handling for fast streams
  - [ ] Message ordering and deduplication
  - [ ] Typing indicators and progress animations
  - [ ] Stream reconnection with state recovery

#### Day 8: Status & Monitoring
- [ ] **Status Panel Implementation**
  - [ ] Current URL and page title display
  - [ ] Action counter with step tracking
  - [ ] Browser state indicators (tabs, cookies, etc.)
  - [ ] Agent activity status and health metrics
  - [ ] Resource usage monitoring (memory, connections)

#### Day 9: User Experience Enhancements
- [ ] **UX Improvements**
  - [ ] Input history with up/down navigation
  - [ ] Keyboard shortcuts (Enter, Shift+Enter, Ctrl+C)
  - [ ] Auto-scroll to latest messages with smart behavior
  - [ ] Copy functionality for messages and code blocks
  - [ ] Message search and filtering
  - [ ] Export conversation functionality

### Phase 4: Testing & Optimization (Days 10-12)

#### Day 10: Unit & Integration Testing
- [ ] **Comprehensive Testing Implementation**
  - [ ] Unit tests for all React components
  - [ ] Integration tests for WebSocket communication
  - [ ] Service layer testing with mocks
  - [ ] Custom hooks testing with React Testing Library
  - [ ] Error boundary testing

#### Day 11: End-to-End Testing
- [ ] **E2E Test Scenarios**
  - [ ] Complete user workflows (session creation to completion)
  - [ ] WebSocket connection scenarios
  - [ ] Error handling and recovery testing
  - [ ] Cross-browser compatibility testing
  - [ ] Mobile responsiveness testing

#### Day 12: Performance Optimization
- [ ] **Performance Tuning**
  - [ ] Bundle size optimization
  - [ ] Component lazy loading
  - [ ] Message virtualization for large histories
  - [ ] WebSocket connection pooling
  - [ ] Memory leak detection and fixes

### Phase 5: Production Readiness (Days 13-15)

#### Day 13: Deployment Preparation
- [ ] **Production Configuration**
  - [ ] Docker containerization
  - [ ] Environment configuration management
  - [ ] Production build optimization
  - [ ] Security headers and CORS configuration
  - [ ] Logging and monitoring setup

#### Day 14: CI/CD & Infrastructure
- [ ] **DevOps Implementation**
  - [ ] GitHub Actions workflows
  - [ ] Automated testing in CI pipeline
  - [ ] Docker image building and registry push
  - [ ] Deployment scripts and health checks
  - [ ] Environment-specific configuration

#### Day 15: Documentation & Polish
- [ ] **Final Touches**
  - [ ] Comprehensive documentation
  - [ ] API documentation with OpenAPI/Swagger
  - [ ] User guide and troubleshooting
  - [ ] Performance benchmarks
  - [ ] Security audit and penetration testing

## Testing Strategy

### Test Pyramid Structure
Following the test pyramid principle with emphasis on unit tests, supported by integration tests, and validated by end-to-end tests.

#### Unit Testing (70% of test coverage)
**Framework**: Vitest + React Testing Library + MSW (Mock Service Worker)

**React Component Testing**:
```typescript
// Example: ChatInterface.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import ChatInterface from './ChatInterface'
import { WebSocketProvider } from '../contexts/WebSocketContext'

describe('ChatInterface', () => {
  it('should render input field and send button', () => {
    render(
      <WebSocketProvider>
        <ChatInterface />
      </WebSocketProvider>
    )
    
    expect(screen.getByPlaceholderText(/enter your message/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument()
  })
  
  it('should handle message submission', async () => {
    const mockSend = vi.fn()
    render(
      <WebSocketProvider value={{ send: mockSend, connected: true }}>
        <ChatInterface />
      </WebSocketProvider>
    )
    
    const input = screen.getByPlaceholderText(/enter your message/i)
    const sendButton = screen.getByRole('button', { name: /send/i })
    
    fireEvent.change(input, { target: { value: 'Test message' } })
    fireEvent.click(sendButton)
    
    await waitFor(() => {
      expect(mockSend).toHaveBeenCalledWith({
        type: 'message',
        content: 'Test message'
      })
    })
  })
})
```

**Component Test Coverage**:
- [ ] **ChatInterface**: Message sending, state management, error handling
- [ ] **MessageList**: Message rendering, virtualization, auto-scroll
- [ ] **StreamingMessage**: Real-time updates, tool call display, progress indicators
- [ ] **InputBar**: Multi-line input, keyboard shortcuts, history navigation
- [ ] **MessageBubble**: Different message types, formatting, copy functionality
- [ ] **StatusPanel**: Status updates, connection indicators, session info
- [ ] **SessionInfo**: Session persistence, cleanup, multiple sessions

**Service Layer Testing**:
```typescript
// Example: websocket.service.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { WebSocketService } from './websocket.service'
import WS from 'jest-websocket-mock'

describe('WebSocketService', () => {
  let server: WS
  let service: WebSocketService
  
  beforeEach(async () => {
    server = new WS('ws://localhost:8000/ws/test-session')
    service = new WebSocketService('test-session')
    await service.connect()
  })
  
  afterEach(() => {
    WS.clean()
  })
  
  it('should establish WebSocket connection', async () => {
    await server.connected
    expect(service.isConnected()).toBe(true)
  })
  
  it('should handle reconnection on failure', async () => {
    server.close()
    
    // Wait for reconnection attempt
    await new Promise(resolve => setTimeout(resolve, 1100))
    
    expect(service.getConnectionAttempts()).toBeGreaterThan(1)
  })
})
```

**Custom Hooks Testing**:
```typescript
// Example: useWebSocket.test.ts
import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useWebSocket } from './useWebSocket'

describe('useWebSocket', () => {
  it('should manage WebSocket connection state', () => {
    const { result } = renderHook(() => useWebSocket('test-session'))
    
    expect(result.current.connected).toBe(false)
    
    act(() => {
      result.current.connect()
    })
    
    expect(result.current.connecting).toBe(true)
  })
})
```

#### Integration Testing (20% of test coverage)
**Framework**: Vitest + MSW + Supertest

**WebSocket Communication Testing**:
```typescript
// Example: websocket-integration.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { WebSocketService } from '../services/websocket'
import { APIServer } from '../server/api_server'

describe('WebSocket Integration', () => {
  let server: APIServer
  let wsService: WebSocketService
  
  beforeAll(async () => {
    server = new APIServer()
    await server.start(8001)
    wsService = new WebSocketService('test-session', 'ws://localhost:8001')
  })
  
  afterAll(async () => {
    await server.stop()
  })
  
  it('should handle full message flow', async () => {
    await wsService.connect()
    
    const messagePromise = new Promise(resolve => {
      wsService.onMessage((message) => {
        if (message.type === 'stream') {
          resolve(message.data)
        }
      })
    })
    
    wsService.send({
      type: 'message',
      content: 'Test query'
    })
    
    const response = await messagePromise
    expect(response).toHaveProperty('agent')
  })
})
```

**API Integration Testing**:
```typescript
// Example: api-integration.test.ts
import { describe, it, expect } from 'vitest'
import request from 'supertest'
import { app } from '../server/api_server'

describe('API Integration', () => {
  it('should create new session', async () => {
    const response = await request(app)
      .post('/api/session')
      .expect(201)
    
    expect(response.body).toHaveProperty('session_id')
    expect(response.body).toHaveProperty('thread_id')
  })
  
  it('should handle session lifecycle', async () => {
    // Create session
    const createResponse = await request(app)
      .post('/api/session')
      .expect(201)
    
    const sessionId = createResponse.body.session_id
    
    // Get session info
    await request(app)
      .get(`/api/session/${sessionId}`)
      .expect(200)
    
    // Delete session
    await request(app)
      .delete(`/api/session/${sessionId}`)
      .expect(204)
    
    // Verify session is gone
    await request(app)
      .get(`/api/session/${sessionId}`)
      .expect(404)
  })
})
```

#### End-to-End Testing (10% of test coverage)
**Framework**: Playwright with TypeScript

**Complete User Workflows**:
```typescript
// Example: e2e/chat-flow.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Chat Interface E2E', () => {
  test('should complete full chat session', async ({ page }) => {
    await page.goto('http://localhost:3000')
    
    // Wait for WebSocket connection
    await expect(page.locator('[data-testid="connection-status"]'))
      .toHaveText('Connected')
    
    // Send a message
    const input = page.locator('[data-testid="message-input"]')
    await input.fill('Navigate to example.com')
    await input.press('Enter')
    
    // Wait for streaming response
    await expect(page.locator('[data-testid="streaming-message"]'))
      .toBeVisible()
    
    // Verify tool call visualization
    await expect(page.locator('[data-testid="tool-call-badge"]'))
      .toContainText('goto_url')
    
    // Wait for completion
    await expect(page.locator('[data-testid="final-answer"]'))
      .toBeVisible({ timeout: 30000 })
    
    // Verify status panel updates
    await expect(page.locator('[data-testid="current-url"]'))
      .toContainText('example.com')
  })
  
  test('should handle connection errors gracefully', async ({ page }) => {
    // Start with server down
    await page.goto('http://localhost:3000')
    
    // Should show connection error
    await expect(page.locator('[data-testid="error-message"]'))
      .toContainText('Connection failed')
    
    // Should show retry button
    await expect(page.locator('[data-testid="retry-button"]'))
      .toBeVisible()
    
    // Simulate server recovery and retry
    await page.locator('[data-testid="retry-button"]').click()
    
    await expect(page.locator('[data-testid="connection-status"]'))
      .toHaveText('Connected', { timeout: 10000 })
  })
})
```

**Cross-Browser Testing**:
```typescript
// Example: e2e/browser-compatibility.spec.ts
import { test, expect, devices } from '@playwright/test'

const browsers = ['chromium', 'firefox', 'webkit']
const devices_list = [devices['iPhone 12'], devices['iPad Pro'], devices['Desktop Chrome']]

browsers.forEach(browserName => {
  test.describe(`${browserName} compatibility`, () => {
    test('should work across different browsers', async ({ page }) => {
      await page.goto('http://localhost:3000')
      
      // Test basic functionality
      await expect(page.locator('[data-testid="chat-interface"]'))
        .toBeVisible()
      
      // Test WebSocket connection
      await expect(page.locator('[data-testid="connection-status"]'))
        .toHaveText('Connected', { timeout: 5000 })
    })
  })
})
```

### Performance Testing

#### Load Testing
**Framework**: Artillery.js + Custom WebSocket Load Testing

```yaml
# load-test/websocket-load.yml
config:
  target: 'ws://localhost:8000'
  phases:
    - duration: 60
      arrivalRate: 10
      name: "Warm up"
    - duration: 120
      arrivalRate: 50
      name: "Sustained load"
    - duration: 60
      arrivalRate: 100
      name: "Peak load"
  engines:
    ws:
      timeout: 30
      
scenarios:
  - name: "WebSocket session test"
    weight: 100
    engine: ws
    flow:
      - connect:
          url: "/ws/{{ $uuid }}"
      - send:
          payload: '{"type": "message", "content": "Test query"}'
      - think: 5
      - send:
          payload: '{"type": "message", "content": "Another query"}'
      - think: 10
```

**WebSocket Performance Testing**:
```typescript
// Example: performance/websocket-perf.test.ts
import { describe, it, expect } from 'vitest'
import { performance } from 'perf_hooks'
import { WebSocketService } from '../services/websocket'

describe('WebSocket Performance', () => {
  it('should handle concurrent connections efficiently', async () => {
    const connectionCount = 100
    const connections: WebSocketService[] = []
    
    const startTime = performance.now()
    
    // Create concurrent connections
    await Promise.all(
      Array.from({ length: connectionCount }, async (_, i) => {
        const ws = new WebSocketService(`session-${i}`)
        connections.push(ws)
        return ws.connect()
      })
    )
    
    const connectionTime = performance.now() - startTime
    
    expect(connectionTime).toBeLessThan(5000) // 5 seconds max
    expect(connections.every(ws => ws.isConnected())).toBe(true)
    
    // Cleanup
    await Promise.all(connections.map(ws => ws.disconnect()))
  })
  
  it('should maintain low latency under load', async () => {
    const ws = new WebSocketService('perf-test')
    await ws.connect()
    
    const messageCount = 1000
    const latencies: number[] = []
    
    for (let i = 0; i < messageCount; i++) {
      const startTime = performance.now()
      
      await new Promise(resolve => {
        ws.send({ type: 'ping', id: i })
        ws.onMessage((msg) => {
          if (msg.type === 'pong' && msg.id === i) {
            latencies.push(performance.now() - startTime)
            resolve(msg)
          }
        })
      })
    }
    
    const avgLatency = latencies.reduce((a, b) => a + b) / latencies.length
    const p95Latency = latencies.sort()[Math.floor(latencies.length * 0.95)]
    
    expect(avgLatency).toBeLessThan(100) // 100ms average
    expect(p95Latency).toBeLessThan(200) // 200ms p95
  })
})
```

#### Bundle Size Analysis
```typescript
// Example: scripts/analyze-bundle.ts
import { analyzeBundleSize } from 'vite-bundle-analyzer'

const analysis = await analyzeBundleSize({
  buildPath: './dist',
  thresholds: {
    total: '500kb',
    chunks: '200kb',
    assets: '100kb'
  }
})

if (analysis.violations.length > 0) {
  console.error('Bundle size violations:', analysis.violations)
  process.exit(1)
}
```

### Test Automation & CI/CD

**GitHub Actions Workflow**:
```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'
          cache-dependency-path: 'frontend/package-lock.json'
      
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Run unit tests
        run: |
          cd frontend
          npm run test:unit -- --coverage --reporter=json
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./frontend/coverage/coverage-final.json

  integration-tests:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      
      - name: Install Python dependencies
        run: |
          pip install uv
          uv sync
          uv run playwright install chromium
      
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'
          cache-dependency-path: 'frontend/package-lock.json'
      
      - name: Install frontend dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Start backend server
        run: |
          uv run python server/api_server.py &
          sleep 5
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      
      - name: Run integration tests
        run: |
          cd frontend
          npm run test:integration

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      
      - name: Install Playwright
        run: |
          cd frontend
          npm ci
          npx playwright install --with-deps
      
      - name: Start full stack
        run: |
          cd frontend
          npm run build
          npm run start:prod &
          sleep 10
      
      - name: Run E2E tests
        run: |
          cd frontend
          npx playwright test
      
      - name: Upload E2E artifacts
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report/

  performance-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Run performance tests
        run: |
          cd frontend
          npm run test:performance
          npm run lighthouse-ci
```

### Test Data Management

**Fixtures and Mock Data**:
```typescript
// Example: test-utils/fixtures.ts
export const mockChatSession = {
  session_id: 'test-session-123',
  thread_id: 'test-thread-456',
  created_at: '2025-08-27T10:00:00Z',
  status: 'active',
  browser_context: {
    url: 'https://example.com',
    title: 'Test Page',
    tabs: [{
      id: 0,
      url: 'https://example.com',
      title: 'Test Page',
      active: true
    }]
  }
}

export const mockStreamingMessages = [
  {
    type: 'stream',
    data: {
      agent: {
        messages: [{
          content: 'Navigating to the website...',
          tool_calls: [{
            name: 'goto_url',
            args: { url: 'https://example.com' }
          }]
        }]
      }
    }
  },
  {
    type: 'stream',
    data: {
      summarizer: {
        messages: [{
          content: 'Successfully navigated to example.com'
        }]
      }
    }
  }
]
```

### Quality Gates

**Coverage Requirements**:
- Unit test coverage: minimum 80%
- Integration test coverage: minimum 70%
- E2E critical path coverage: 100%
- Performance regression threshold: 10%

**Automated Quality Checks**:
```json
// package.json scripts for quality gates
{
  "scripts": {
    "test:unit": "vitest run --coverage",
    "test:unit:watch": "vitest --coverage",
    "test:integration": "vitest run --config vitest.integration.config.ts",
    "test:e2e": "playwright test",
    "test:e2e:debug": "playwright test --debug",
    "test:performance": "vitest run --config vitest.performance.config.ts",
    "test:all": "npm run test:unit && npm run test:integration && npm run test:e2e",
    "quality:lint": "eslint src --ext .ts,.tsx",
    "quality:type-check": "tsc --noEmit",
    "quality:format": "prettier --check src/**/*.{ts,tsx}",
    "quality:audit": "npm audit --audit-level moderate",
    "quality:bundle-size": "bundlesize",
    "quality:all": "npm run quality:lint && npm run quality:type-check && npm run quality:format && npm run quality:audit && npm run quality:bundle-size"
  }
}
```

## Deployment Strategy

### Container Architecture

#### Frontend Container
```dockerfile
# frontend/Dockerfile
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:80/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

#### Backend Container
```dockerfile
# server/Dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose Configuration

```yaml
# docker-compose.yml
version: '3.8'

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    environment:
      - REACT_APP_API_URL=http://backend:8000
      - REACT_APP_WS_URL=ws://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  backend:
    build:
      context: .
      dockerfile: server/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - KAGE_REDIS_HOST=redis
      - KAGE_REDIS_PORT=6379
      - KAGE_GROUPCHAT_ROOM=production
      - KAGE_MAX_KAGEBUNSHIN_INSTANCES=10
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    volumes:
      - browser_data:/app/.cache/ms-playwright

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    restart: unless-stopped
    volumes:
      - redis_data:/data

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - frontend
      - backend
    restart: unless-stopped

volumes:
  redis_data:
  browser_data:

networks:
  default:
    driver: bridge
```

### Environment Configuration

#### Production Environment Variables
```bash
# .env.production
# API Configuration
OPENAI_API_KEY=your-production-openai-key
ANTHROPIC_API_KEY=your-production-anthropic-key

# Redis Configuration
KAGE_REDIS_HOST=redis
KAGE_REDIS_PORT=6379
KAGE_REDIS_PASSWORD=your-redis-password
KAGE_GROUPCHAT_ROOM=production

# Application Settings
KAGE_MAX_KAGEBUNSHIN_INSTANCES=10
KAGE_ENABLE_SUMMARIZATION=1
KAGE_LOG_LEVEL=INFO

# Security
CORS_ALLOWED_ORIGINS=https://yourdomain.com
SECURE_HEADERS=true
SSL_REDIRECT=true

# Monitoring
SENTRY_DSN=your-sentry-dsn
NEW_RELIC_LICENSE_KEY=your-newrelic-key

# Frontend Configuration
REACT_APP_API_URL=https://api.yourdomain.com
REACT_APP_WS_URL=wss://api.yourdomain.com
REACT_APP_ENVIRONMENT=production
REACT_APP_VERSION=${CI_COMMIT_SHA:-latest}
```

#### Staging Environment
```bash
# .env.staging
# Similar to production but with staging-specific values
OPENAI_API_KEY=your-staging-openai-key
KAGE_GROUPCHAT_ROOM=staging
KAGE_MAX_KAGEBUNSHIN_INSTANCES=3
CORS_ALLOWED_ORIGINS=https://staging.yourdomain.com
REACT_APP_API_URL=https://staging-api.yourdomain.com
```

### CI/CD Pipeline

#### GitHub Actions Deployment Workflow
```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [ main ]
  release:
    types: [ published ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    uses: ./.github/workflows/test.yml
    secrets: inherit

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    strategy:
      matrix:
        component: [frontend, backend]
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-${{ matrix.component }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix=sha-
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ${{ matrix.component == 'frontend' && './frontend' || '.' }}
          file: ${{ matrix.component == 'frontend' && './frontend/Dockerfile' || './server/Dockerfile' }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: build-and-push
    runs-on: ubuntu-latest
    environment: staging
    
    steps:
      - name: Deploy to staging
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: ${{ secrets.STAGING_USER }}
          key: ${{ secrets.STAGING_SSH_KEY }}
          script: |
            cd /opt/kagebunshin
            docker-compose -f docker-compose.staging.yml pull
            docker-compose -f docker-compose.staging.yml up -d
            docker system prune -f
      
      - name: Run smoke tests
        run: |
          sleep 30
          curl -f https://staging.yourdomain.com/health || exit 1

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    if: github.event_name == 'release'
    
    steps:
      - name: Deploy to production
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.PRODUCTION_HOST }}
          username: ${{ secrets.PRODUCTION_USER }}
          key: ${{ secrets.PRODUCTION_SSH_KEY }}
          script: |
            cd /opt/kagebunshin
            docker-compose pull
            docker-compose up -d --force-recreate
            docker system prune -f
      
      - name: Run production health checks
        run: |
          sleep 60
          curl -f https://yourdomain.com/health || exit 1
          curl -f https://api.yourdomain.com/health || exit 1
```

#### Kubernetes Deployment (Alternative)
```yaml
# k8s/deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kagebunshin-frontend
  labels:
    app: kagebunshin-frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kagebunshin-frontend
  template:
    metadata:
      labels:
        app: kagebunshin-frontend
    spec:
      containers:
      - name: frontend
        image: ghcr.io/siwoobae/kagebunshin-frontend:latest
        ports:
        - containerPort: 80
        env:
        - name: REACT_APP_API_URL
          value: "https://api.yourdomain.com"
        - name: REACT_APP_WS_URL
          value: "wss://api.yourdomain.com"
        livenessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
---
apiVersion: v1
kind: Service
metadata:
  name: kagebunshin-frontend-service
spec:
  selector:
    app: kagebunshin-frontend
  ports:
  - protocol: TCP
    port: 80
    targetPort: 80
  type: ClusterIP
```

### Infrastructure as Code

#### Terraform Configuration
```hcl
# terraform/main.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# VPC and Networking
resource "aws_vpc" "kagebunshin_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {
    Name = "kagebunshin-vpc"
  }
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.kagebunshin_vpc.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]
  
  map_public_ip_on_launch = true
  
  tags = {
    Name = "kagebunshin-public-${count.index + 1}"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "kagebunshin" {
  name = "kagebunshin"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Application Load Balancer
resource "aws_lb" "kagebunshin_alb" {
  name               = "kagebunshin-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
  
  enable_deletion_protection = false
}

# ECS Task Definitions
resource "aws_ecs_task_definition" "frontend" {
  family                   = "kagebunshin-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  
  container_definitions = jsonencode([{
    name  = "frontend"
    image = "${var.ecr_repository_frontend}:latest"
    
    portMappings = [{
      containerPort = 80
      protocol      = "tcp"
    }]
    
    environment = [
      {
        name  = "REACT_APP_API_URL"
        value = "https://${aws_lb.kagebunshin_alb.dns_name}"
      },
      {
        name  = "REACT_APP_WS_URL"
        value = "wss://${aws_lb.kagebunshin_alb.dns_name}"
      }
    ]
    
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.frontend.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

# ECS Services
resource "aws_ecs_service" "frontend" {
  name            = "kagebunshin-frontend"
  cluster         = aws_ecs_cluster.kagebunshin.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 2
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 80
  }
}
```

### Monitoring and Observability

#### Application Monitoring
```typescript
// frontend/src/services/monitoring.ts
import * as Sentry from '@sentry/react'
import { BrowserTracing } from '@sentry/tracing'

// Initialize error tracking
Sentry.init({
  dsn: process.env.REACT_APP_SENTRY_DSN,
  environment: process.env.REACT_APP_ENVIRONMENT,
  integrations: [
    new BrowserTracing({
      routingInstrumentation: Sentry.reactRouterV6Instrumentation(
        React.useEffect,
        useLocation,
        useNavigationType,
        createRoutesFromChildren,
        matchRoutes
      ),
    }),
  ],
  tracesSampleRate: 0.1,
  beforeSend: (event) => {
    // Filter out development errors
    if (process.env.NODE_ENV === 'development') {
      return null
    }
    return event
  }
})

// Custom performance monitoring
export class PerformanceMonitor {
  private static instance: PerformanceMonitor
  private metrics: Map<string, number> = new Map()
  
  static getInstance(): PerformanceMonitor {
    if (!PerformanceMonitor.instance) {
      PerformanceMonitor.instance = new PerformanceMonitor()
    }
    return PerformanceMonitor.instance
  }
  
  measureWebSocketLatency(startTime: number): void {
    const latency = performance.now() - startTime
    this.metrics.set('websocket_latency', latency)
    
    // Track slow WebSocket responses
    if (latency > 1000) {
      Sentry.addBreadcrumb({
        message: 'Slow WebSocket response',
        level: 'warning',
        data: { latency }
      })
    }
  }
  
  measureComponentRender(componentName: string, renderTime: number): void {
    const metricName = `component_render_${componentName}`
    this.metrics.set(metricName, renderTime)
    
    // Track slow renders
    if (renderTime > 100) {
      Sentry.addBreadcrumb({
        message: `Slow component render: ${componentName}`,
        level: 'warning',
        data: { renderTime }
      })
    }
  }
  
  getMetrics(): Record<string, number> {
    return Object.fromEntries(this.metrics)
  }
}
```

#### Backend Monitoring
```python
# server/monitoring.py
import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, Any
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from prometheus_client import Counter, Histogram, generate_latest

# Initialize Sentry
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[
        FastApiIntegration(auto_enabling_integrations=False),
        RedisIntegration(),
    ],
    traces_sample_rate=0.1,
    environment=os.getenv("ENVIRONMENT", "production")
)

# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

WEBSOCKET_CONNECTIONS = Counter(
    'websocket_connections_total',
    'Total WebSocket connections',
    ['status']
)

AGENT_OPERATIONS = Counter(
    'agent_operations_total',
    'Total agent operations',
    ['operation_type', 'status']
)

class MonitoringService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
    
    @asynccontextmanager
    async def monitor_request(self, method: str, endpoint: str):
        start_time = time.time()
        try:
            yield
            status_code = "200"
        except Exception as e:
            status_code = "500"
            sentry_sdk.capture_exception(e)
            raise
        finally:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()
            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
    
    def track_websocket_connection(self, session_id: str, status: str):
        WEBSOCKET_CONNECTIONS.labels(status=status).inc()
        
        if status == "connected":
            self.active_sessions[session_id] = {
                "connected_at": time.time(),
                "message_count": 0,
                "last_activity": time.time()
            }
        elif status == "disconnected" and session_id in self.active_sessions:
            session_duration = time.time() - self.active_sessions[session_id]["connected_at"]
            self.logger.info(
                f"Session {session_id} ended",
                extra={
                    "session_id": session_id,
                    "duration": session_duration,
                    "message_count": self.active_sessions[session_id]["message_count"]
                }
            )
            del self.active_sessions[session_id]
    
    def track_agent_operation(self, operation_type: str, status: str, session_id: str = None):
        AGENT_OPERATIONS.labels(
            operation_type=operation_type,
            status=status
        ).inc()
        
        if session_id and session_id in self.active_sessions:
            self.active_sessions[session_id]["last_activity"] = time.time()
            if status == "completed":
                self.active_sessions[session_id]["message_count"] += 1
```

#### Health Checks and Status Endpoints
```python
# server/health.py
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import asyncio
import aioredis
from playwright.async_api import async_playwright

router = APIRouter()

class HealthChecker:
    def __init__(self):
        self.checks = {
            "database": self._check_redis,
            "browser": self._check_playwright,
            "llm": self._check_llm_connection,
        }
    
    async def _check_redis(self) -> Dict[str, Any]:
        try:
            redis = aioredis.from_url("redis://localhost:6379")
            await redis.ping()
            await redis.close()
            return {"status": "healthy", "latency_ms": 0}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_playwright(self) -> Dict[str, Any]:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto("about:blank")
                await browser.close()
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_llm_connection(self) -> Dict[str, Any]:
        try:
            # Test LLM connection with a simple query
            from kagebunshin.config.settings import get_settings
            settings = get_settings()
            # Add actual LLM health check here
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def run_all_checks(self) -> Dict[str, Any]:
        results = {}
        overall_healthy = True
        
        for check_name, check_func in self.checks.items():
            try:
                result = await asyncio.wait_for(check_func(), timeout=5.0)
                results[check_name] = result
                if result["status"] != "healthy":
                    overall_healthy = False
            except asyncio.TimeoutError:
                results[check_name] = {"status": "timeout", "error": "Check timed out"}
                overall_healthy = False
            except Exception as e:
                results[check_name] = {"status": "error", "error": str(e)}
                overall_healthy = False
        
        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "checks": results
        }

health_checker = HealthChecker()

@router.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "kagebunshin-api"}

@router.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with dependency verification."""
    results = await health_checker.run_all_checks()
    
    if results["status"] != "healthy":
        raise HTTPException(status_code=503, detail=results)
    
    return results

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from monitoring import generate_latest
    return Response(generate_latest(), media_type="text/plain")
```

## Success Criteria

### Functional Requirements
- [ ] Can initiate and maintain persistent chat sessions
- [ ] Displays streaming responses in real-time
- [ ] Shows tool calls and their arguments
- [ ] Maintains message history across page reloads
- [ ] Displays current browser status information
- [ ] Handles errors gracefully with user feedback

### Performance Requirements
- [ ] WebSocket connection establishes within 1 second
- [ ] Messages appear with < 100ms latency
- [ ] Smooth scrolling with large message histories
- [ ] Responsive design works on mobile and desktop

### User Experience Requirements
- [ ] Clean, minimal black and white design
- [ ] Intuitive input and interaction patterns
- [ ] Clear visual hierarchy and message types
- [ ] Accessible keyboard navigation
- [ ] Professional appearance suitable for development use

## Future Enhancements (Out of Scope for MVP)
- Multiple concurrent sessions
- Message export functionality
- Advanced filtering and search
- Dark mode toggle
- Custom themes
- Voice input integration
- Screen sharing for debugging
- Integration with external tools

## Risk Mitigation
- **WebSocket Connection Issues**: Implement automatic reconnection with exponential backoff
- **Session State Loss**: Use local storage and periodic state synchronization
- **Performance with Large Histories**: Implement message virtualization
- **Cross-browser Compatibility**: Test on Chrome, Firefox, Safari, Edge
- **Mobile Responsiveness**: Progressive Web App considerations

## Session Management Architecture

### Session Lifecycle Management

#### Session Creation
```typescript
interface SessionConfig {
  id: string;                    // UUID for frontend identification
  thread_id: string;            // Backend KageBunshinAgent thread_id
  user_agent?: string;          // Browser fingerprint data
  viewport?: ViewportSize;      // Initial browser dimensions
  permissions?: string[];       // Browser permissions granted
  created_at: timestamp;
  expires_at?: timestamp;       // Optional session expiry
}

interface SessionState {
  config: SessionConfig;
  status: 'initializing' | 'active' | 'paused' | 'suspended' | 'ended' | 'error';
  browser_context: BrowserContextData;
  agent_metadata: AgentMetadata;
  performance_metrics: SessionMetrics;
}
```

#### Session Persistence Strategy
**Local Storage Architecture:**
- **Primary Storage**: `sessionStorage` for active session data (auto-cleared on tab close)
- **Backup Storage**: `localStorage` for session recovery across browser restarts
- **Data Partitioning**: Separate storage keys by data type for efficient access
- **Compression**: Use LZ-string for large message histories to reduce storage footprint

**Storage Keys:**
```typescript
const STORAGE_KEYS = {
  // Session metadata (small, frequently accessed)
  SESSION_META: `kage_session_${sessionId}_meta`,
  SESSION_CONFIG: `kage_session_${sessionId}_config`,
  
  // Message history (large, append-only)
  MESSAGES: `kage_session_${sessionId}_messages`,
  MESSAGE_INDEX: `kage_session_${sessionId}_msg_index`,
  
  // Browser state (medium, occasionally updated)
  BROWSER_STATE: `kage_session_${sessionId}_browser`,
  TAB_STATE: `kage_session_${sessionId}_tabs`,
  
  // Performance and debugging
  METRICS: `kage_session_${sessionId}_metrics`,
  ERRORS: `kage_session_${sessionId}_errors`,
};
```

#### State Synchronization Protocol
**Client-Server Synchronization:**
- **Heartbeat System**: Periodic sync every 30 seconds during active use
- **Change Detection**: Hash-based change detection to minimize sync overhead
- **Conflict Resolution**: Last-write-wins with timestamp-based conflict resolution
- **Optimistic Updates**: Apply changes immediately with rollback on server rejection

**Synchronization Events:**
```typescript
interface SyncEvent {
  type: 'session_state' | 'message_batch' | 'browser_state' | 'metrics';
  session_id: string;
  timestamp: number;
  data: any;
  checksum: string;
  version: number;
}

// WebSocket sync protocol
const SYNC_MESSAGES = {
  CLIENT_SYNC_REQUEST: 'client_sync_request',
  SERVER_SYNC_RESPONSE: 'server_sync_response',
  STATE_CHANGE_NOTIFY: 'state_change_notify',
  SYNC_CONFLICT: 'sync_conflict',
  FORCE_RESYNC: 'force_resync'
};
```

### Session Recovery & Restoration

#### Browser Tab Management
**Tab State Serialization:**
```typescript
interface TabState {
  tab_id: string;
  url: string;
  title: string;
  is_active: boolean;
  last_interaction: timestamp;
  viewport_position: ScrollPosition;
  form_data?: FormSnapshot;    // Auto-saved form inputs
  navigation_history: string[]; // Recent URLs visited
}

interface BrowserContextData {
  tabs: TabState[];
  active_tab_id: string;
  total_tabs: number;
  browser_metadata: {
    user_agent: string;
    viewport: ViewportSize;
    permissions: string[];
    cookies_enabled: boolean;
  };
}
```

**Session Recovery Flow:**
1. **Detection**: Check for existing session data on application load
2. **Validation**: Verify session data integrity and expiry
3. **Backend Reconnection**: Attempt to reconnect to existing backend session
4. **State Reconstruction**: Rebuild UI state from stored data
5. **Progressive Sync**: Gradually sync large datasets (messages, browser state)
6. **Fallback**: Create new session if recovery fails

#### Data Migration & Versioning

**Schema Versioning:**
```typescript
interface StorageSchema {
  version: string;           // Semantic version (e.g., "1.2.0")
  schema_hash: string;      // Schema definition hash
  migration_path?: string[]; // Required migration steps
}

const SCHEMA_VERSIONS = {
  '1.0.0': 'Initial release schema',
  '1.1.0': 'Added browser tab state',
  '1.2.0': 'Enhanced message metadata',
  '2.0.0': 'Breaking: New state structure'
};
```

**Migration Strategy:**
- **Backward Compatibility**: Support 2 previous major versions
- **Progressive Migration**: Migrate data lazily during use
- **Rollback Safety**: Keep backup of pre-migration data
- **Migration Validation**: Verify data integrity after migration

### Performance Optimization

#### Large Session Data Handling
**Message History Optimization:**
- **Virtual Scrolling**: Render only visible messages in UI
- **Lazy Loading**: Load message history in chunks (50 messages per batch)
- **Message Compression**: Compress message content using LZ-string
- **Index-based Access**: Maintain message index for fast lookup
- **Cleanup Strategy**: Archive old messages after 1000 messages per session

```typescript
interface MessageBatch {
  session_id: string;
  batch_id: string;
  start_index: number;
  end_index: number;
  messages: CompressedMessage[];
  checksum: string;
  created_at: timestamp;
}

interface MessageIndex {
  session_id: string;
  total_messages: number;
  batches: BatchReference[];
  last_updated: timestamp;
}
```

#### Storage Quota Management
**Storage Strategy:**
- **Quota Monitoring**: Monitor localStorage usage and warn at 80% capacity
- **Intelligent Cleanup**: Remove oldest inactive sessions first
- **Data Prioritization**: Keep essential data (current session) over historical data
- **Compression Levels**: Multiple compression levels based on data age

```typescript
interface StorageQuotaManager {
  getTotalUsage(): Promise<StorageQuota>;
  cleanupOldSessions(threshold: number): Promise<CleanupResult>;
  compressOldData(age_threshold: number): Promise<CompressionResult>;
  estimateDataSize(data: any): number;
}
```

## Message History Architecture

### Message Persistence & Retrieval

#### Message Data Model
```typescript
interface Message {
  id: string;                   // Unique message identifier
  session_id: string;           // Parent session reference
  type: MessageType;            // Message classification
  timestamp: number;            // Unix timestamp
  content: MessageContent;      // Message payload
  metadata: MessageMetadata;    // Additional context
  parent_id?: string;          // For threaded conversations
  status: MessageStatus;        // Processing state
}

enum MessageType {
  USER_INPUT = 'user_input',
  AGENT_RESPONSE = 'agent_response',
  TOOL_CALL = 'tool_call',
  TOOL_RESULT = 'tool_result',
  SYSTEM_MESSAGE = 'system_message',
  ERROR_MESSAGE = 'error_message',
  SUMMARY = 'summary'
}

interface MessageMetadata {
  token_count?: number;         // For cost tracking
  processing_time?: number;     // Response latency
  model_used?: string;          // LLM model identifier
  tool_calls?: ToolCallInfo[];  // Associated tool calls
  browser_state_snapshot?: string; // Browser state hash
  user_agent?: string;          // Client information
}
```

#### Storage & Indexing Strategy
**Hierarchical Storage:**
- **Hot Data**: Last 100 messages in memory for instant access
- **Warm Data**: Recent session messages (last 500) in sessionStorage
- **Cold Data**: Historical messages in localStorage with compression
- **Archive Data**: Very old messages moved to optional cloud backup

**Message Indexing:**
```typescript
interface MessageIndex {
  by_timestamp: Map<number, string>;    // Chronological access
  by_type: Map<MessageType, string[]>; // Type-based filtering
  by_tool: Map<string, string[]>;      // Tool call history
  by_error: Map<string, string[]>;     // Error debugging
}

class MessageHistoryManager {
  async addMessage(message: Message): Promise<void>;
  async getMessages(session_id: string, options?: QueryOptions): Promise<Message[]>;
  async searchMessages(query: MessageQuery): Promise<SearchResult>;
  async exportHistory(format: 'json' | 'markdown' | 'html'): Promise<string>;
}
```

### Advanced Message Features

#### Message Threading & Context
**Conversation Threading:**
- **Parent-Child Relationships**: Link related messages (user query → agent response → tool calls)
- **Context Windows**: Maintain conversation context for LLM with token limits
- **Message Grouping**: Group related messages (e.g., all messages in a single automation flow)

```typescript
interface ConversationThread {
  thread_id: string;
  session_id: string;
  root_message_id: string;
  message_ids: string[];
  context_summary?: string;    // Auto-generated summary for long threads
  total_tokens: number;        // Token count tracking
  status: 'active' | 'completed' | 'error';
}
```

#### Message Search & Filtering
**Advanced Search Capabilities:**
- **Full-Text Search**: Search within message content
- **Metadata Filtering**: Filter by type, timestamp, tool used, etc.
- **Semantic Search**: Find related messages by meaning (future enhancement)
- **Export Functionality**: Export filtered messages in multiple formats

```typescript
interface MessageQuery {
  session_id?: string;
  text_search?: string;
  type_filter?: MessageType[];
  date_range?: DateRange;
  tool_filter?: string[];
  has_errors?: boolean;
  limit?: number;
  offset?: number;
}

interface SearchResult {
  messages: Message[];
  total_count: number;
  query_time: number;
  highlights?: SearchHighlight[];
}
```

### Message History Performance

#### Streaming Message Updates
**Real-time Message Processing:**
- **Incremental Updates**: Stream message content as it arrives
- **Partial Message Rendering**: Display partial content while streaming
- **Optimistic Updates**: Show messages immediately with confirmation states
- **Rollback Capability**: Handle message send failures gracefully

```typescript
interface StreamingMessage {
  id: string;
  session_id: string;
  type: MessageType;
  content_stream: ReadableStream<string>;
  status: 'streaming' | 'complete' | 'error';
  estimated_tokens?: number;
}

class StreamingMessageHandler {
  async processStreamChunk(chunk: MessageChunk): Promise<void>;
  async finalizeMessage(message_id: string): Promise<Message>;
  async handleStreamError(error: StreamError): Promise<void>;
}
```

#### Memory Management
**Efficient Message Handling:**
- **Message Virtualization**: Only render visible messages in UI
- **Progressive Loading**: Load message batches on demand
- **Memory Cleanup**: Remove old messages from memory while keeping in storage
- **Compression Strategy**: Compress old message content for space efficiency

```typescript
interface MessageBuffer {
  hot_messages: Message[];      // In-memory for instant access
  warm_cache: LRUCache<string, Message>; // Recently accessed messages
  cold_storage: StorageAdapter; // Persistent storage interface
}

class MessageMemoryManager {
  private buffer: MessageBuffer;
  private quota_manager: StorageQuotaManager;
  
  async loadMessageBatch(start: number, count: number): Promise<Message[]>;
  async evictOldMessages(threshold: number): Promise<number>;
  async optimizeStorage(): Promise<OptimizationResult>;
}
```

### Data Integrity & Backup

#### Message Integrity Verification
**Data Validation:**
- **Checksum Verification**: Validate message integrity on load
- **Schema Validation**: Ensure message format compliance
- **Corruption Detection**: Identify and handle corrupted data
- **Auto-Repair**: Attempt to repair minor data corruption

```typescript
interface IntegrityCheck {
  checksum: string;
  schema_version: string;
  validation_timestamp: number;
  corruption_detected: boolean;
  repair_attempted: boolean;
}

class MessageIntegrityManager {
  async validateMessage(message: Message): Promise<ValidationResult>;
  async validateSession(session_id: string): Promise<SessionValidation>;
  async repairCorruption(corruption: CorruptionReport): Promise<RepairResult>;
}
```

#### Backup & Synchronization
**Data Backup Strategy:**
- **Local Backup**: Periodic export to local files
- **Cloud Sync**: Optional cloud backup integration
- **Cross-Device Sync**: Share sessions across devices (future enhancement)
- **Disaster Recovery**: Full session reconstruction from backups

## Conclusion
This plan provides a comprehensive roadmap for creating a frontend MVP that fully replicates the kagebunshin CLI REPL functionality while providing a superior user experience through modern web technologies and clean design principles. The enhanced session management and message history architecture ensures reliable data persistence, efficient performance, and seamless user experience across browser sessions.