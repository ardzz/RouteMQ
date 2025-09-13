# Chat Application

This guide demonstrates how to build a real-time chat application using RouteMQ with features like multi-room support, private messaging, user presence, and message history.

## Overview

The chat application handles:
- Real-time messaging between users
- Multiple chat rooms and channels
- Private direct messages
- User presence and status tracking
- Message history and persistence
- File sharing and media messages
- Message reactions and threading
- Typing indicators

## Architecture

```
Chat Clients <-> MQTT <-> RouteMQ Chat Router <-> Redis/Database
                                               <-> WebSocket Service
                                               <-> Message Storage
                                               <-> User Presence
```

## Chat Router Setup

```python
# app/routers/chat.py
from core.router import Router
from app.controllers.chat_controller import ChatController
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.profanity_filter import ProfanityFilterMiddleware
from app.middleware.message_validation import MessageValidationMiddleware

router = Router()

# Middleware setup
auth = AuthMiddleware()
rate_limit = RateLimitMiddleware(max_requests=100, window_seconds=60)  # Stricter for chat
profanity_filter = ProfanityFilterMiddleware()
message_validation = MessageValidationMiddleware()

# Chat routes
with router.group(prefix="chat", middleware=[auth, rate_limit, message_validation]) as chat:
    
    # Room management
    chat.on("rooms/create", ChatController.create_room, qos=2)
    chat.on("rooms/join/{room_id}", ChatController.join_room, qos=1)
    chat.on("rooms/leave/{room_id}", ChatController.leave_room, qos=1)
    chat.on("rooms/list", ChatController.list_rooms, qos=1)
    chat.on("rooms/{room_id}/info", ChatController.get_room_info, qos=1)
    
    # Messaging
    with chat.group(middleware=[profanity_filter]) as messaging:
        messaging.on("message/{room_id}", ChatController.send_room_message, qos=1)
        messaging.on("private/{user_id}", ChatController.send_private_message, qos=1)
        messaging.on("broadcast", ChatController.send_broadcast_message, qos=1)
    
    # Message management
    chat.on("message/{message_id}/edit", ChatController.edit_message, qos=1)
    chat.on("message/{message_id}/delete", ChatController.delete_message, qos=1)
    chat.on("message/{message_id}/react", ChatController.add_reaction, qos=0)
    chat.on("message/{message_id}/reply", ChatController.reply_to_message, qos=1)
    
    # User presence and status
    chat.on("presence/online", ChatController.set_user_online, qos=0)
    chat.on("presence/offline", ChatController.set_user_offline, qos=0)
    chat.on("presence/away", ChatController.set_user_away, qos=0)
    chat.on("typing/{room_id}/start", ChatController.start_typing, qos=0)
    chat.on("typing/{room_id}/stop", ChatController.stop_typing, qos=0)
    
    # Message history
    chat.on("history/{room_id}", ChatController.get_message_history, qos=1)
    chat.on("search/{room_id}", ChatController.search_messages, qos=1)
    
    # File sharing
    chat.on("file/upload/{room_id}", ChatController.handle_file_upload, qos=2)
    chat.on("file/share/{room_id}", ChatController.share_file, qos=1)

# Admin routes
with router.group(prefix="chat/admin", middleware=[auth]) as admin:
    admin.on("rooms/{room_id}/moderate", ChatController.moderate_room, qos=2)
    admin.on("users/{user_id}/mute", ChatController.mute_user, qos=2)
    admin.on("users/{user_id}/ban", ChatController.ban_user, qos=2)
    admin.on("messages/cleanup", ChatController.cleanup_messages, qos=1)
```

## Chat Controller Implementation

```python
# app/controllers/chat_controller.py
from core.controller import Controller
from core.redis_manager import redis_manager
from app.models.user import User
from app.services.chat_service import ChatService
from app.services.file_service import FileService
from app.services.notification_service import NotificationService
import json
import time
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from enum import Enum

class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"

class UserStatus(Enum):
    ONLINE = "online"
    AWAY = "away"
    OFFLINE = "offline"

class ChatController(Controller):
    
    @staticmethod
    async def create_room(payload: Dict[str, Any], client, **kwargs):
        """Create a new chat room"""
        try:
            context = kwargs.get('context', {})
            creator_id = context.get('user_id')
            
            room_name = payload.get("name")
            room_description = payload.get("description", "")
            room_type = payload.get("type", "public")  # public, private, direct
            max_members = payload.get("max_members", 100)
            
            if not room_name:
                raise ValueError("Room name is required")
            
            room_id = str(uuid.uuid4())
            
            # Create room data
            room_data = {
                "id": room_id,
                "name": room_name,
                "description": room_description,
                "type": room_type,
                "creator_id": creator_id,
                "created_at": time.time(),
                "max_members": max_members,
                "member_count": 1,
                "last_activity": time.time()
            }
            
            # Store room data
            await redis_manager.set_json(f"room:{room_id}", room_data, ex=86400*30)  # 30 days
            
            # Add to rooms list
            await redis_manager.sadd("rooms:all", room_id)
            if room_type == "public":
                await redis_manager.sadd("rooms:public", room_id)
            
            # Add creator as member
            await redis_manager.sadd(f"room:{room_id}:members", creator_id)
            await redis_manager.sadd(f"user:{creator_id}:rooms", room_id)
            
            # Set creator as admin
            await redis_manager.sadd(f"room:{room_id}:admins", creator_id)
            
            # Send system message
            system_message = {
                "id": str(uuid.uuid4()),
                "room_id": room_id,
                "type": MessageType.SYSTEM.value,
                "content": f"Room '{room_name}' created",
                "timestamp": time.time(),
                "sender": "system"
            }
            
            await ChatController._store_message(system_message)
            await ChatController._broadcast_to_room(room_id, system_message, client)
            
            return {
                "status": "room_created",
                "room_id": room_id,
                "room_data": room_data
            }
            
        except Exception as e:
            print(f"Error creating room: {e}")
            raise
    
    @staticmethod
    async def join_room(room_id: str, payload: Dict[str, Any], client, **kwargs):
        """Join a chat room"""
        try:
            context = kwargs.get('context', {})
            user_id = context.get('user_id')
            
            # Check if room exists
            room_data = await redis_manager.get_json(f"room:{room_id}")
            if not room_data:
                raise ValueError("Room not found")
            
            # Check if user is already a member
            is_member = await redis_manager.sismember(f"room:{room_id}:members", user_id)
            if is_member:
                return {"status": "already_member", "room_id": room_id}
            
            # Check room capacity
            member_count = await redis_manager.scard(f"room:{room_id}:members")
            if member_count >= room_data.get("max_members", 100):
                raise ValueError("Room is full")
            
            # Check if user is banned
            is_banned = await redis_manager.sismember(f"room:{room_id}:banned", user_id)
            if is_banned:
                raise ValueError("User is banned from this room")
            
            # Add user to room
            await redis_manager.sadd(f"room:{room_id}:members", user_id)
            await redis_manager.sadd(f"user:{user_id}:rooms", room_id)
            
            # Update member count
            await redis_manager.incr(f"room:{room_id}:member_count")
            
            # Get user info
            user = await User.find_by_id(user_id)
            username = user.username if user else f"User_{user_id}"
            
            # Send join message
            join_message = {
                "id": str(uuid.uuid4()),
                "room_id": room_id,
                "type": MessageType.SYSTEM.value,
                "content": f"{username} joined the room",
                "timestamp": time.time(),
                "sender": "system",
                "user_id": user_id
            }
            
            await ChatController._store_message(join_message)
            await ChatController._broadcast_to_room(room_id, join_message, client)
            
            # Send recent message history to new member
            await ChatController._send_recent_history(room_id, user_id, client)
            
            return {
                "status": "joined",
                "room_id": room_id,
                "member_count": member_count + 1
            }
            
        except Exception as e:
            print(f"Error joining room {room_id}: {e}")
            raise
    
    @staticmethod
    async def send_room_message(room_id: str, payload: Dict[str, Any], client, **kwargs):
        """Send message to a room"""
        try:
            context = kwargs.get('context', {})
            sender_id = context.get('user_id')
            
            content = payload.get("content")
            message_type = payload.get("type", MessageType.TEXT.value)
            reply_to = payload.get("reply_to")  # Message ID this is replying to
            
            if not content:
                raise ValueError("Message content is required")
            
            # Check if user is member of room
            is_member = await redis_manager.sismember(f"room:{room_id}:members", sender_id)
            if not is_member:
                raise ValueError("User is not a member of this room")
            
            # Check if user is muted
            is_muted = await redis_manager.sismember(f"room:{room_id}:muted", sender_id)
            if is_muted:
                raise ValueError("User is muted in this room")
            
            # Create message
            message_id = str(uuid.uuid4())
            message = {
                "id": message_id,
                "room_id": room_id,
                "sender_id": sender_id,
                "content": content,
                "type": message_type,
                "timestamp": time.time(),
                "reply_to": reply_to,
                "reactions": {},
                "edited": False
            }
            
            # Get sender info
            user = await User.find_by_id(sender_id)
            message["sender_name"] = user.username if user else f"User_{sender_id}"
            
            # Store message
            await ChatController._store_message(message)
            
            # Update room last activity
            await redis_manager.set(f"room:{room_id}:last_activity", time.time())
            
            # Broadcast to room members
            await ChatController._broadcast_to_room(room_id, message, client)
            
            # Update user's message count
            await redis_manager.incr(f"user:{sender_id}:message_count")
            
            return {
                "status": "message_sent",
                "message_id": message_id,
                "timestamp": message["timestamp"]
            }
            
        except Exception as e:
            print(f"Error sending message to room {room_id}: {e}")
            raise
    
    @staticmethod
    async def send_private_message(target_user_id: str, payload: Dict[str, Any], client, **kwargs):
        """Send private message to another user"""
        try:
            context = kwargs.get('context', {})
            sender_id = context.get('user_id')
            
            if sender_id == target_user_id:
                raise ValueError("Cannot send message to yourself")
            
            content = payload.get("content")
            message_type = payload.get("type", MessageType.TEXT.value)
            
            if not content:
                raise ValueError("Message content is required")
            
            # Create or get private room ID
            room_id = await ChatController._get_or_create_private_room(sender_id, target_user_id)
            
            # Create message
            message_id = str(uuid.uuid4())
            message = {
                "id": message_id,
                "room_id": room_id,
                "sender_id": sender_id,
                "target_id": target_user_id,
                "content": content,
                "type": message_type,
                "timestamp": time.time(),
                "is_private": True,
                "read": False
            }
            
            # Get sender info
            user = await User.find_by_id(sender_id)
            message["sender_name"] = user.username if user else f"User_{sender_id}"
            
            # Store message
            await ChatController._store_message(message)
            
            # Send to both users
            await ChatController._send_to_user(sender_id, message, client)
            await ChatController._send_to_user(target_user_id, message, client)
            
            # Update unread count for target user
            await redis_manager.incr(f"user:{target_user_id}:unread_messages")
            
            # Send push notification to target user if offline
            target_status = await redis_manager.get(f"user:{target_user_id}:status")
            if target_status != UserStatus.ONLINE.value:
                await NotificationService.send_message_notification(target_user_id, message)
            
            return {
                "status": "private_message_sent",
                "message_id": message_id,
                "room_id": room_id
            }
            
        except Exception as e:
            print(f"Error sending private message: {e}")
            raise
    
    @staticmethod
    async def start_typing(room_id: str, payload: Dict[str, Any], client, **kwargs):
        """Indicate user is typing"""
        try:
            context = kwargs.get('context', {})
            user_id = context.get('user_id')
            
            # Check if user is member
            is_member = await redis_manager.sismember(f"room:{room_id}:members", user_id)
            if not is_member:
                return {"status": "not_member"}
            
            # Set typing indicator
            await redis_manager.setex(f"typing:{room_id}:{user_id}", 10, "1")  # 10 seconds
            
            # Get user info
            user = await User.find_by_id(user_id)
            username = user.username if user else f"User_{user_id}"
            
            # Broadcast typing indicator
            typing_message = {
                "type": "typing_start",
                "room_id": room_id,
                "user_id": user_id,
                "username": username,
                "timestamp": time.time()
            }
            
            await ChatController._broadcast_to_room(room_id, typing_message, client, exclude_user=user_id)
            
            return {"status": "typing_started"}
            
        except Exception as e:
            print(f"Error setting typing indicator: {e}")
            raise
    
    @staticmethod
    async def stop_typing(room_id: str, payload: Dict[str, Any], client, **kwargs):
        """Stop typing indicator"""
        try:
            context = kwargs.get('context', {})
            user_id = context.get('user_id')
            
            # Remove typing indicator
            await redis_manager.delete(f"typing:{room_id}:{user_id}")
            
            # Broadcast stop typing
            typing_message = {
                "type": "typing_stop",
                "room_id": room_id,
                "user_id": user_id,
                "timestamp": time.time()
            }
            
            await ChatController._broadcast_to_room(room_id, typing_message, client, exclude_user=user_id)
            
            return {"status": "typing_stopped"}
            
        except Exception as e:
            print(f"Error stopping typing indicator: {e}")
            raise
    
    @staticmethod
    async def add_reaction(message_id: str, payload: Dict[str, Any], client, **kwargs):
        """Add reaction to a message"""
        try:
            context = kwargs.get('context', {})
            user_id = context.get('user_id')
            
            emoji = payload.get("emoji")
            if not emoji:
                raise ValueError("Emoji is required")
            
            # Get message
            message = await redis_manager.get_json(f"message:{message_id}")
            if not message:
                raise ValueError("Message not found")
            
            # Check if user is member of the room
            room_id = message["room_id"]
            is_member = await redis_manager.sismember(f"room:{room_id}:members", user_id)
            if not is_member:
                raise ValueError("User is not a member of this room")
            
            # Add reaction
            reactions = message.get("reactions", {})
            if emoji not in reactions:
                reactions[emoji] = []
            
            if user_id not in reactions[emoji]:
                reactions[emoji].append(user_id)
                message["reactions"] = reactions
                
                # Update message
                await redis_manager.set_json(f"message:{message_id}", message, ex=86400*30)
                
                # Broadcast reaction update
                reaction_message = {
                    "type": "reaction_added",
                    "message_id": message_id,
                    "emoji": emoji,
                    "user_id": user_id,
                    "reactions": reactions,
                    "timestamp": time.time()
                }
                
                await ChatController._broadcast_to_room(room_id, reaction_message, client)
            
            return {"status": "reaction_added", "reactions": reactions}
            
        except Exception as e:
            print(f"Error adding reaction: {e}")
            raise
    
    @staticmethod
    async def get_message_history(room_id: str, payload: Dict[str, Any], client, **kwargs):
        """Get message history for a room"""
        try:
            context = kwargs.get('context', {})
            user_id = context.get('user_id')
            
            # Check if user is member
            is_member = await redis_manager.sismember(f"room:{room_id}:members", user_id)
            if not is_member:
                raise ValueError("User is not a member of this room")
            
            limit = payload.get("limit", 50)
            before_timestamp = payload.get("before")  # For pagination
            
            # Get messages from Redis sorted set
            if before_timestamp:
                max_score = before_timestamp
            else:
                max_score = "+inf"
            
            message_ids = await redis_manager.zrevrangebyscore(
                f"room:{room_id}:messages",
                max_score,
                "-inf",
                start=0,
                num=limit
            )
            
            messages = []
            for message_id in message_ids:
                message = await redis_manager.get_json(f"message:{message_id}")
                if message:
                    messages.append(message)
            
            return {
                "status": "success",
                "room_id": room_id,
                "messages": messages,
                "count": len(messages)
            }
            
        except Exception as e:
            print(f"Error getting message history: {e}")
            raise
    
    @staticmethod
    async def set_user_online(payload: Dict[str, Any], client, **kwargs):
        """Set user status to online"""
        try:
            context = kwargs.get('context', {})
            user_id = context.get('user_id')
            
            # Set user status
            await redis_manager.setex(f"user:{user_id}:status", 300, UserStatus.ONLINE.value)  # 5 minutes
            await redis_manager.set(f"user:{user_id}:last_seen", time.time())
            
            # Add to online users set
            await redis_manager.sadd("users:online", user_id)
            
            # Broadcast status to user's rooms
            await ChatController._broadcast_user_status(user_id, UserStatus.ONLINE.value, client)
            
            return {"status": "online"}
            
        except Exception as e:
            print(f"Error setting user online: {e}")
            raise
    
    # Helper methods
    @staticmethod
    async def _store_message(message: Dict[str, Any]):
        """Store message in Redis and database"""
        message_id = message["id"]
        room_id = message["room_id"]
        timestamp = message["timestamp"]
        
        # Store message data
        await redis_manager.set_json(f"message:{message_id}", message, ex=86400*30)  # 30 days
        
        # Add to room's message timeline
        await redis_manager.zadd(f"room:{room_id}:messages", {message_id: timestamp})
        
        # Keep only recent messages in memory (last 1000)
        await redis_manager.zremrangebyrank(f"room:{room_id}:messages", 0, -1001)
        
        # Add to global message index for search
        if message.get("type") == MessageType.TEXT.value:
            await redis_manager.zadd("messages:all", {message_id: timestamp})
    
    @staticmethod
    async def _broadcast_to_room(room_id: str, message: Dict[str, Any], client, exclude_user: str = None):
        """Broadcast message to all room members"""
        members = await redis_manager.smembers(f"room:{room_id}:members")
        
        for member_id in members:
            if exclude_user and member_id == exclude_user:
                continue
            
            await ChatController._send_to_user(member_id, message, client)
    
    @staticmethod
    async def _send_to_user(user_id: str, message: Dict[str, Any], client):
        """Send message to specific user"""
        # In a real implementation, this would send via WebSocket
        # For now, we'll publish to a user-specific topic
        user_topic = f"chat/user/{user_id}/messages"
        client.publish(user_topic, json.dumps(message))
    
    @staticmethod
    async def _get_or_create_private_room(user1_id: str, user2_id: str) -> str:
        """Get or create private room between two users"""
        # Create consistent room ID regardless of user order
        sorted_users = sorted([user1_id, user2_id])
        room_id = f"private_{sorted_users[0]}_{sorted_users[1]}"
        
        # Check if room already exists
        room_exists = await redis_manager.exists(f"room:{room_id}")
        
        if not room_exists:
            # Create private room
            room_data = {
                "id": room_id,
                "type": "private",
                "participants": sorted_users,
                "created_at": time.time(),
                "last_activity": time.time()
            }
            
            await redis_manager.set_json(f"room:{room_id}", room_data, ex=86400*30)
            
            # Add users as members
            for user_id in sorted_users:
                await redis_manager.sadd(f"room:{room_id}:members", user_id)
                await redis_manager.sadd(f"user:{user_id}:rooms", room_id)
        
        return room_id
    
    @staticmethod
    async def _send_recent_history(room_id: str, user_id: str, client):
        """Send recent message history to user"""
        # Get last 20 messages
        message_ids = await redis_manager.zrevrange(f"room:{room_id}:messages", 0, 19)
        
        messages = []
        for message_id in message_ids:
            message = await redis_manager.get_json(f"message:{message_id}")
            if message:
                messages.append(message)
        
        # Send in chronological order
        messages.reverse()
        
        history_message = {
            "type": "message_history",
            "room_id": room_id,
            "messages": messages
        }
        
        await ChatController._send_to_user(user_id, history_message, client)
    
    @staticmethod
    async def _broadcast_user_status(user_id: str, status: str, client):
        """Broadcast user status to all their rooms"""
        user_rooms = await redis_manager.smembers(f"user:{user_id}:rooms")
        
        # Get user info
        user = await User.find_by_id(user_id)
        username = user.username if user else f"User_{user_id}"
        
        status_message = {
            "type": "user_status",
            "user_id": user_id,
            "username": username,
            "status": status,
            "timestamp": time.time()
        }
        
        for room_id in user_rooms:
            await ChatController._broadcast_to_room(room_id, status_message, client, exclude_user=user_id)
```

## Message Validation Middleware

```python
# app/middleware/message_validation.py
from core.middleware import Middleware
import re

class MessageValidationMiddleware(Middleware):
    async def handle(self, context, next_handler):
        payload = context.get('payload', {})
        
        if 'content' in payload:
            content = payload['content']
            
            # Length validation
            if len(content) > 4000:  # 4000 character limit
                raise ValueError("Message too long (max 4000 characters)")
            
            if len(content.strip()) == 0:
                raise ValueError("Message cannot be empty")
            
            # Basic content validation
            if self._contains_excessive_caps(content):
                payload['content'] = content.lower()
            
            # URL validation (simplified)
            if self._contains_suspicious_urls(content):
                payload['flagged'] = True
        
        return await next_handler(context)
    
    def _contains_excessive_caps(self, text: str) -> bool:
        """Check if message has too many capital letters"""
        if len(text) < 10:
            return False
        caps_ratio = sum(1 for c in text if c.isupper()) / len(text)
        return caps_ratio > 0.7
    
    def _contains_suspicious_urls(self, text: str) -> bool:
        """Basic check for suspicious URLs"""
        suspicious_domains = ['bit.ly', 'tinyurl.com']  # Add more as needed
        return any(domain in text for domain in suspicious_domains)
```

## Usage Examples

### Join Room and Send Message
```python
# Join room: chat/rooms/join/room_123
{
    "user_preferences": {
        "notifications": true
    }
}

# Send message: chat/message/room_123
{
    "content": "Hello everyone!",
    "type": "text"
}
```

### Private Message
```python
# Send private message: chat/private/user_456
{
    "content": "Hey, how are you?",
    "type": "text"
}
```

### Add Reaction
```python
# Add reaction: chat/message/msg_789/react
{
    "emoji": "👍"
}
```

### Typing Indicator
```python
# Start typing: chat/typing/room_123/start
{}

# Stop typing: chat/typing/room_123/stop  
{}
```

This chat application provides comprehensive real-time messaging capabilities with room management, private messaging, presence tracking, and moderation features.

## Integration with Frontend

The chat system can be integrated with web clients using WebSocket connections or Server-Sent Events (SSE) for real-time updates. Mobile clients can use MQTT directly or HTTP APIs with push notifications for offline message delivery.
