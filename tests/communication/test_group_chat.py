"""
Unit tests for group chat communication system.
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from collections import deque

from kagebunshin.communication.group_chat import ChatRecord, GroupChatClient


class TestChatRecord:
    """Test suite for ChatRecord data class."""
    
    def test_should_create_chat_record_with_all_fields(self):
        """Test creating ChatRecord with all required fields."""
        record = ChatRecord(
            room="test_room",
            sender="agent_1",
            message="Hello world",
            timestamp=1234567890.5
        )
        
        assert record.room == "test_room"
        assert record.sender == "agent_1"
        assert record.message == "Hello world"
        assert record.timestamp == 1234567890.5

    def test_should_serialize_to_json_correctly(self):
        """Test ChatRecord JSON serialization."""
        record = ChatRecord(
            room="lobby",
            sender="test_agent",
            message="Test message with unicode: 你好",
            timestamp=1640995200.0
        )
        
        json_str = record.as_json()
        parsed = json.loads(json_str)
        
        assert parsed["room"] == "lobby"
        assert parsed["sender"] == "test_agent"
        assert parsed["message"] == "Test message with unicode: 你好"
        assert parsed["timestamp"] == 1640995200.0

    def test_should_handle_special_characters_in_json(self):
        """Test that special characters are properly handled in JSON."""
        record = ChatRecord(
            room="test",
            sender="agent",
            message='Message with "quotes" and \n newlines',
            timestamp=1234567890.0
        )
        
        json_str = record.as_json()
        parsed = json.loads(json_str)
        
        assert parsed["message"] == 'Message with "quotes" and \n newlines'


class TestGroupChatClient:
    """Test suite for GroupChatClient Redis and fallback functionality."""
    
    def test_should_initialize_with_default_parameters(self):
        """Test GroupChatClient initialization with defaults."""
        client = GroupChatClient()
        
        assert client.host == "127.0.0.1"  # From settings
        assert client.port == 6379  # From settings
        assert client.db == 0  # From settings
        assert client.max_messages == 200  # From settings
        assert client._connected is False
        assert client._redis is None

    def test_should_initialize_with_custom_parameters(self):
        """Test GroupChatClient initialization with custom parameters."""
        client = GroupChatClient(
            host="redis.example.com",
            port=6380,
            db=1,
            key_prefix="custom_chat",
            max_messages=100
        )
        
        assert client.host == "redis.example.com"
        assert client.port == 6380
        assert client.db == 1
        assert client.key_prefix == "custom_chat"
        assert client.max_messages == 100

    def test_should_strip_trailing_colon_from_key_prefix(self):
        """Test that trailing colon is stripped from key prefix."""
        client = GroupChatClient(key_prefix="chat_prefix:")
        
        assert client.key_prefix == "chat_prefix"

    @pytest.mark.asyncio
    async def test_should_connect_to_redis_successfully(self):
        """Test successful Redis connection."""
        client = GroupChatClient()
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis_class.return_value = mock_redis
            mock_redis.ping.return_value = True
            
            await client.connect()
            
            assert client._connected is True
            assert client._redis == mock_redis
            mock_redis_class.assert_called_once_with(
                host=client.host, port=client.port, db=client.db, decode_responses=True
            )
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_handle_redis_connection_failure_gracefully(self):
        """Test graceful handling of Redis connection failure."""
        client = GroupChatClient()
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis_class.side_effect = Exception("Redis unavailable")
            
            await client.connect()
            
            assert client._connected is False
            assert client._redis is None

    @pytest.mark.asyncio
    async def test_should_skip_connect_if_already_connected(self):
        """Test that connect is skipped if already connected."""
        client = GroupChatClient()
        client._connected = True
        mock_redis = Mock()
        client._redis = mock_redis
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            await client.connect()
            
            mock_redis_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_post_message_to_redis_when_connected(self):
        """Test posting message to Redis when connection is available."""
        client = GroupChatClient()
        client._connected = True
        mock_redis = AsyncMock()
        client._redis = mock_redis
        
        await client.post("test_room", "agent_1", "Hello Redis!")
        
        # Verify Redis operations were called
        mock_redis.rpush.assert_called_once()  # Implementation uses rpush, not lpush
        mock_redis.ltrim.assert_called_once()
        
        # Check that the message was formatted correctly
        call_args = mock_redis.rpush.call_args[0]
        assert call_args[0] == "kagebunshin:groupchat:test_room"  # Key
        
        # Parse the JSON message
        message_json = call_args[1]
        message_data = json.loads(message_json)
        assert message_data["room"] == "test_room"
        assert message_data["sender"] == "agent_1"
        assert message_data["message"] == "Hello Redis!"

    @pytest.mark.asyncio
    async def test_should_fallback_to_memory_when_redis_unavailable(self):
        """Test fallback to in-memory storage when Redis is unavailable."""
        client = GroupChatClient()
        client._connected = False
        
        await client.post("test_room", "agent_1", "Hello Memory!")
        
        # Verify message was stored in memory - key is just the room name
        room_key = "test_room"
        assert room_key in GroupChatClient._GLOBAL_MEM_STORE
        assert len(GroupChatClient._GLOBAL_MEM_STORE[room_key]) == 1
        
        record = GroupChatClient._GLOBAL_MEM_STORE[room_key][0]
        assert record.room == "test_room"
        assert record.sender == "agent_1"
        assert record.message == "Hello Memory!"

    @pytest.mark.asyncio
    async def test_should_get_recent_messages_from_redis(self):
        """Test retrieving recent messages from Redis."""
        client = GroupChatClient()
        client._connected = True
        mock_redis = AsyncMock()
        client._redis = mock_redis
        
        # Mock Redis response - no encoding needed due to decode_responses=True
        test_record = ChatRecord("test_room", "agent_1", "Test message", 1234567890.0)
        mock_redis.lrange.return_value = [test_record.as_json()]
        
        messages = await client.history("test_room", limit=10)
        
        assert len(messages) == 1
        assert messages[0].room == "test_room"
        assert messages[0].sender == "agent_1"
        assert messages[0].message == "Test message"
        
        mock_redis.lrange.assert_called_once_with("kagebunshin:groupchat:test_room", -10, -1)

    @pytest.mark.asyncio
    async def test_should_get_recent_messages_from_memory_fallback(self):
        """Test retrieving messages from memory when Redis unavailable."""
        client = GroupChatClient()
        client._connected = False
        
        # Add test data to memory store - key is just the room name
        room_key = "test_room"
        test_record = ChatRecord("test_room", "agent_1", "Memory message", 1234567890.0)
        GroupChatClient._GLOBAL_MEM_STORE[room_key] = deque([test_record])
        
        messages = await client.history("test_room", limit=10)
        
        assert len(messages) == 1
        assert messages[0].room == "test_room"
        assert messages[0].sender == "agent_1"
        assert messages[0].message == "Memory message"

    @pytest.mark.asyncio
    async def test_should_limit_messages_in_memory_store(self):
        """Test that memory store respects max_messages limit."""
        client = GroupChatClient(max_messages=3)
        client._connected = False
        
        # Clear any existing data from previous tests
        room_key = "test_limit_room"
        GroupChatClient._GLOBAL_MEM_STORE.pop(room_key, None)
        
        # Add more messages than the limit
        for i in range(5):
            await client.post(room_key, "agent", f"Message {i}")
        
        messages = GroupChatClient._GLOBAL_MEM_STORE[room_key]
        
        # Should only keep the most recent 3 messages
        assert len(messages) == 3
        assert messages[-1].message == "Message 4"  # Most recent last in deque
        assert messages[0].message == "Message 2"  # Oldest kept

    @pytest.mark.asyncio
    async def test_should_handle_malformed_json_in_redis_gracefully(self):
        """Test graceful handling of malformed JSON from Redis."""
        client = GroupChatClient()
        client._connected = True
        mock_redis = AsyncMock()
        client._redis = mock_redis
        
        # Mock Redis returning invalid JSON - no encoding needed
        valid_record = ChatRecord("test_room", "agent", "Valid message", 1234567890.0)
        mock_redis.lrange.return_value = ['invalid json', valid_record.as_json()]
        
        messages = await client.history("test_room")
        
        # Should skip malformed entries and continue processing
        assert len(messages) == 1  # One valid entry
        assert messages[0].message == "Valid message"

    @pytest.mark.asyncio
    async def test_should_handle_redis_errors_during_operations(self):
        """Test handling of Redis errors during message operations."""
        client = GroupChatClient()
        client._connected = True
        mock_redis = AsyncMock()
        client._redis = mock_redis
        mock_redis.rpush.side_effect = Exception("Redis error")
        
        # Should not crash, should fallback gracefully
        await client.post("test_room", "agent", "Test message")
        
        # Message should be stored in memory as fallback
        room_key = "test_room"
        assert room_key in GroupChatClient._GLOBAL_MEM_STORE

    @pytest.mark.asyncio
    async def test_should_return_empty_list_for_nonexistent_room(self):
        """Test that non-existent rooms return empty message list."""
        client = GroupChatClient()
        client._connected = False
        
        messages = await client.history("nonexistent_room")
        
        assert messages == []