"""
Redis-backed group chat for Kagebunshin agents.

Provides a lightweight, concurrency-safe queue (Redis list) for posting and
reading recent group messages. Falls back to in-memory storage when Redis is
unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Any

from ..config.settings import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    REDIS_USERNAME,
    GROUPCHAT_PREFIX,
    GROUPCHAT_MAX_MESSAGES,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatRecord:
    room: str
    sender: str
    message: str
    timestamp: float  # epoch seconds

    def as_json(self) -> str:
        return json.dumps({
            "room": self.room,
            "sender": self.sender,
            "message": self.message,
            "timestamp": self.timestamp,
        }, ensure_ascii=False)


class GroupChatClient:
    """Async Redis client wrapper with in-memory fallback for group chat."""

    # Process-wide fallback store so multiple agents in same process can share
    _GLOBAL_MEM_STORE: Dict[str, Deque[ChatRecord]] = {}
    _GLOBAL_LOCK: Optional[asyncio.Lock] = None

    def __init__(
        self,
        host: str = REDIS_HOST,
        port: int = REDIS_PORT,
        db: int = REDIS_DB,
        password: Optional[str] = REDIS_PASSWORD,
        username: Optional[str] = REDIS_USERNAME,
        key_prefix: str = GROUPCHAT_PREFIX,
        max_messages: int = GROUPCHAT_MAX_MESSAGES,
    ) -> None:
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.username = username
        self.key_prefix = key_prefix.rstrip(":")
        self.max_messages = max_messages

        self._redis: Optional[Any] = None
        self._connected = False

        # Initialize global lock lazily
        if GroupChatClient._GLOBAL_LOCK is None:
            GroupChatClient._GLOBAL_LOCK = asyncio.Lock()

    async def connect(self) -> None:
        if self._connected:
            return
        try:
            # Lazy import to avoid hard dependency if unused
            from redis import asyncio as aioredis  # type: ignore

            # Build Redis connection parameters
            redis_params = {
                "host": self.host,
                "port": self.port,
                "db": self.db,
                "decode_responses": True
            }
            
            # Add authentication if provided
            if self.password:
                redis_params["password"] = self.password
            if self.username:
                redis_params["username"] = self.username

            self._redis = aioredis.Redis(**redis_params)
            # Simple ping to verify connection
            await self._redis.ping()
            self._connected = True
            auth_info = f" (auth: {self.username})" if self.username else ""
            logger.info(f"GroupChatClient connected to Redis at {self.host}:{self.port}/{self.db}{auth_info}")
        except Exception as e:
            self._redis = None
            self._connected = False
            logger.warning(f"GroupChatClient: Redis unavailable ({e}). Falling back to in-memory queue.")

    def _key(self, room: str) -> str:
        return f"{self.key_prefix}:{room}"

    async def post(self, room: str, sender: str, message: str) -> None:
        record = ChatRecord(room=room, sender=sender, message=message, timestamp=datetime.now(timezone.utc).timestamp())
        if self._connected and self._redis is not None:
            try:
                key = self._key(room)
                # Use RPUSH to append to queue; trim to last N messages
                await self._redis.rpush(key, record.as_json())
                # Keep only the newest max_messages entries
                await self._redis.ltrim(key, -self.max_messages, -1)
                return
            except Exception as e:
                logger.warning(f"GroupChatClient.post: Redis error, switching to memory. Error: {e}")
                self._connected = False
                self._redis = None

        # Fallback to in-memory store
        async with GroupChatClient._GLOBAL_LOCK:  # type: ignore[arg-type]
            q = GroupChatClient._GLOBAL_MEM_STORE.setdefault(room, deque(maxlen=self.max_messages))
            q.append(record)

    async def history(self, room: str, limit: int = 100) -> List[ChatRecord]:
        limit = max(1, min(limit, self.max_messages))
        if self._connected and self._redis is not None:
            try:
                key = self._key(room)
                # Read last `limit` messages
                values = await self._redis.lrange(key, -limit, -1)
                records: List[ChatRecord] = []
                for val in values:
                    try:
                        obj = json.loads(val)
                        records.append(
                            ChatRecord(
                                room=obj.get("room", room),
                                sender=obj.get("sender", "unknown"),
                                message=obj.get("message", ""),
                                timestamp=float(obj.get("timestamp", datetime.now(timezone.utc).timestamp())),
                            )
                        )
                    except Exception:
                        continue
                return records
            except Exception as e:
                logger.warning(f"GroupChatClient.history: Redis error, switching to memory. Error: {e}")
                self._connected = False
                self._redis = None

        # Fallback to in-memory store
        async with GroupChatClient._GLOBAL_LOCK:  # type: ignore[arg-type]
            q = GroupChatClient._GLOBAL_MEM_STORE.get(room, deque())
            return list(q)[-limit:]

    @staticmethod
    def format_history(records: List[ChatRecord]) -> str:
        if not records:
            return "Group Chat (no messages yet)."
        lines: List[str] = ["Group Chat (recent messages):"]
        for rec in records:
            ts = datetime.utcfromtimestamp(rec.timestamp).strftime("%H:%M:%S")
            lines.append(f"[{ts}] {rec.sender}: {rec.message}")
        return "\n".join(lines)

