# Real-time Notifications

This guide demonstrates how to build a comprehensive real-time notification system using RouteMQ for push notifications, alerts, and real-time updates.

## Overview

The notification system handles:
- Real-time push notifications to web clients
- Email and SMS alerts
- System status notifications
- User-specific notifications
- Broadcast messages
- Notification queuing and retry logic

## Architecture

```
Event Sources -> RouteMQ -> Notification Router -> Multiple Channels
                                                -> WebSocket/SSE
                                                -> Email Service
                                                -> SMS Service
                                                -> Push Notifications
                                                -> In-App Notifications
```

## Notification Router Setup

```python
# app/routers/notifications.py
from core.router import Router
from app.controllers.notification_controller import NotificationController
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.notification_filter import NotificationFilterMiddleware

router = Router()

# Middleware setup
auth = AuthMiddleware()
rate_limit = RateLimitMiddleware(max_requests=1000, window_seconds=60)
notification_filter = NotificationFilterMiddleware()

# Notification routes
with router.group(prefix="notifications", middleware=[auth, rate_limit]) as notifications:
    # Real-time notifications
    notifications.on("realtime/user/{user_id}", NotificationController.send_user_notification, qos=1)
    notifications.on("realtime/broadcast", NotificationController.broadcast_notification, qos=1)
    notifications.on("realtime/group/{group_id}", NotificationController.send_group_notification, qos=1)
    
    # Alert notifications
    notifications.on("alerts/critical/{alert_type}", NotificationController.handle_critical_alert, qos=2)
    notifications.on("alerts/warning/{alert_type}", NotificationController.handle_warning_alert, qos=1)
    notifications.on("alerts/info/{alert_type}", NotificationController.handle_info_alert, qos=0)
    
    # System notifications
    notifications.on("system/status", NotificationController.system_status_update, qos=1)
    notifications.on("system/maintenance", NotificationController.maintenance_notification, qos=2)
    
    # Email notifications (queued processing)
    notifications.on("email/send", NotificationController.queue_email, qos=2, shared=True, worker_count=3)
    notifications.on("email/batch", NotificationController.send_batch_email, qos=2, shared=True)
    
    # SMS notifications
    notifications.on("sms/send", NotificationController.send_sms, qos=2, shared=True)
    
    # Push notifications (mobile)
    notifications.on("push/mobile/{platform}", NotificationController.send_push_notification, qos=1)

# WebSocket connection management
with router.group(prefix="websocket", middleware=[auth]) as websocket:
    websocket.on("connect/{user_id}", NotificationController.websocket_connect, qos=1)
    websocket.on("disconnect/{user_id}", NotificationController.websocket_disconnect, qos=1)
    websocket.on("heartbeat/{user_id}", NotificationController.websocket_heartbeat, qos=0)
```

## Notification Controller Implementation

```python
# app/controllers/notification_controller.py
from core.controller import Controller
from core.redis_manager import redis_manager
from app.models.mail_log import MailLog
from app.models.user import User
from app.services.email_service import EmailService
from app.services.sms_service import SMSService
from app.services.push_service import PushService
from app.services.websocket_service import WebSocketService
import json
import time
import uuid
from typing import Dict, List, Any
from enum import Enum
from datetime import datetime, timedelta

class NotificationPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

class NotificationController(Controller):
    
    @staticmethod
    async def send_user_notification(user_id: str, payload: Dict[str, Any], client):
        """Send real-time notification to specific user"""
        try:
            notification_id = str(uuid.uuid4())
            message = payload.get("message")
            title = payload.get("title", "Notification")
            priority = payload.get("priority", NotificationPriority.NORMAL.value)
            notification_type = payload.get("type", "info")
            data = payload.get("data", {})
            
            if not message:
                raise ValueError("Message is required")
            
            # Create notification object
            notification = {
                "id": notification_id,
                "user_id": user_id,
                "title": title,
                "message": message,
                "type": notification_type,
                "priority": priority,
                "data": data,
                "timestamp": time.time(),
                "read": False,
                "channels": []
            }
            
            # Store notification
            await redis_manager.set_json(f"notification:{notification_id}", notification, ex=86400)
            
            # Add to user's notification list
            await redis_manager.lpush(f"user:{user_id}:notifications", notification_id)
            await redis_manager.ltrim(f"user:{user_id}:notifications", 0, 99)  # Keep last 100
            
            # Check user's notification preferences
            preferences = await NotificationController._get_user_preferences(user_id)
            
            # Send via appropriate channels
            channels_used = []
            
            # WebSocket/SSE for real-time updates
            if preferences.get("realtime", True):
                await WebSocketService.send_to_user(user_id, notification)
                channels_used.append("realtime")
            
            # Email for high priority notifications
            if priority in [NotificationPriority.HIGH.value, NotificationPriority.CRITICAL.value]:
                if preferences.get("email", True):
                    await NotificationController._queue_email_notification(user_id, notification)
                    channels_used.append("email")
            
            # SMS for critical notifications
            if priority == NotificationPriority.CRITICAL.value:
                if preferences.get("sms", False):
                    await NotificationController._queue_sms_notification(user_id, notification)
                    channels_used.append("sms")
            
            # Push notification for mobile
            if preferences.get("push", True):
                await NotificationController._send_push_notification(user_id, notification)
                channels_used.append("push")
            
            # Update notification with channels used
            notification["channels"] = channels_used
            await redis_manager.set_json(f"notification:{notification_id}", notification, ex=86400)
            
            # Update user's unread count
            await redis_manager.incr(f"user:{user_id}:unread_notifications")
            
            return {
                "status": "sent",
                "notification_id": notification_id,
                "channels": channels_used
            }
            
        except Exception as e:
            print(f"Error sending user notification to {user_id}: {e}")
            raise
    
    @staticmethod
    async def broadcast_notification(payload: Dict[str, Any], client):
        """Send broadcast notification to all users"""
        try:
            message = payload.get("message")
            title = payload.get("title", "System Notification")
            notification_type = payload.get("type", "system")
            target_groups = payload.get("target_groups", [])  # Optional user groups
            
            if not message:
                raise ValueError("Message is required")
            
            broadcast_id = str(uuid.uuid4())
            
            # Create broadcast notification
            broadcast = {
                "id": broadcast_id,
                "title": title,
                "message": message,
                "type": notification_type,
                "target_groups": target_groups,
                "timestamp": time.time(),
                "sent_count": 0
            }
            
            # Store broadcast info
            await redis_manager.set_json(f"broadcast:{broadcast_id}", broadcast, ex=86400)
            
            # Get target users
            if target_groups:
                users = await NotificationController._get_users_in_groups(target_groups)
            else:
                users = await NotificationController._get_all_active_users()
            
            sent_count = 0
            
            # Send to each user
            for user_id in users:
                try:
                    # Create individual notification
                    user_notification = {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "title": title,
                        "message": message,
                        "type": notification_type,
                        "broadcast_id": broadcast_id,
                        "timestamp": time.time(),
                        "read": False
                    }
                    
                    # Send via WebSocket
                    await WebSocketService.send_to_user(user_id, user_notification)
                    
                    # Store user notification
                    await redis_manager.lpush(f"user:{user_id}:notifications", user_notification["id"])
                    await redis_manager.set_json(f"notification:{user_notification['id']}", user_notification, ex=86400)
                    
                    sent_count += 1
                    
                except Exception as user_error:
                    print(f"Error sending broadcast to user {user_id}: {user_error}")
            
            # Update broadcast stats
            broadcast["sent_count"] = sent_count
            await redis_manager.set_json(f"broadcast:{broadcast_id}", broadcast, ex=86400)
            
            return {
                "status": "broadcast_sent",
                "broadcast_id": broadcast_id,
                "sent_count": sent_count
            }
            
        except Exception as e:
            print(f"Error sending broadcast notification: {e}")
            raise
    
    @staticmethod
    async def handle_critical_alert(alert_type: str, payload: Dict[str, Any], client):
        """Handle critical system alerts"""
        try:
            alert_id = str(uuid.uuid4())
            message = payload.get("message")
            source = payload.get("source")
            severity = payload.get("severity", "critical")
            affected_systems = payload.get("affected_systems", [])
            
            # Create alert notification
            alert = {
                "id": alert_id,
                "type": alert_type,
                "message": message,
                "source": source,
                "severity": severity,
                "affected_systems": affected_systems,
                "timestamp": time.time(),
                "acknowledged": False
            }
            
            # Store alert
            await redis_manager.set_json(f"alert:{alert_id}", alert, ex=86400)
            await redis_manager.lpush("alerts:critical", alert_id)
            
            # Get administrators and on-call personnel
            admin_users = await NotificationController._get_admin_users()
            oncall_users = await NotificationController._get_oncall_users(alert_type)
            
            # Combine and deduplicate users
            target_users = list(set(admin_users + oncall_users))
            
            # Send immediate notifications via all channels
            for user_id in target_users:
                # Real-time notification
                await WebSocketService.send_to_user(user_id, {
                    "type": "critical_alert",
                    "alert": alert,
                    "requires_acknowledgment": True
                })
                
                # Email notification
                await NotificationController._queue_email_notification(user_id, {
                    "title": f"CRITICAL ALERT: {alert_type}",
                    "message": message,
                    "priority": "critical",
                    "data": alert
                })
                
                # SMS notification
                await NotificationController._queue_sms_notification(user_id, {
                    "message": f"CRITICAL: {alert_type} - {message}",
                    "priority": "critical"
                })
            
            # Set up escalation if not acknowledged
            await NotificationController._schedule_alert_escalation(alert_id, target_users)
            
            return {
                "status": "critical_alert_sent",
                "alert_id": alert_id,
                "notified_users": len(target_users)
            }
            
        except Exception as e:
            print(f"Error handling critical alert {alert_type}: {e}")
            raise
    
    @staticmethod
    async def queue_email(payload: Dict[str, Any], client):
        """Queue email for delivery"""
        try:
            email_id = str(uuid.uuid4())
            to_email = payload.get("to")
            subject = payload.get("subject")
            body = payload.get("body")
            html_body = payload.get("html_body")
            priority = payload.get("priority", "normal")
            send_at = payload.get("send_at")  # Scheduled delivery
            
            if not all([to_email, subject, body]):
                raise ValueError("To email, subject, and body are required")
            
            # Create email job
            email_job = {
                "id": email_id,
                "to": to_email,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "priority": priority,
                "send_at": send_at or time.time(),
                "created_at": time.time(),
                "status": "queued",
                "attempts": 0,
                "max_attempts": 3
            }
            
            # Store email job
            await redis_manager.set_json(f"email_job:{email_id}", email_job, ex=86400)
            
            # Add to appropriate queue based on priority
            queue_name = f"email_queue:{priority}"
            if send_at and send_at > time.time():
                # Scheduled email
                await redis_manager.zadd("email_queue:scheduled", {email_id: send_at})
            else:
                # Immediate email
                await redis_manager.lpush(queue_name, email_id)
            
            # Log email creation
            mail_log = MailLog(
                email_id=email_id,
                to_email=to_email,
                subject=subject,
                status="queued",
                created_at=datetime.now()
            )
            await mail_log.save()
            
            return {"status": "email_queued", "email_id": email_id}
            
        except Exception as e:
            print(f"Error queuing email: {e}")
            raise
    
    @staticmethod
    async def send_sms(payload: Dict[str, Any], client):
        """Send SMS notification"""
        try:
            phone_number = payload.get("phone")
            message = payload.get("message")
            priority = payload.get("priority", "normal")
            
            if not all([phone_number, message]):
                raise ValueError("Phone number and message are required")
            
            # Send SMS via service
            result = await SMSService.send_sms(phone_number, message)
            
            # Log SMS
            sms_log = {
                "phone": phone_number,
                "message": message,
                "priority": priority,
                "status": result.get("status"),
                "timestamp": time.time()
            }
            
            await redis_manager.lpush("sms_logs", json.dumps(sms_log))
            
            return {"status": "sms_sent", "result": result}
            
        except Exception as e:
            print(f"Error sending SMS: {e}")
            raise
    
    @staticmethod
    async def websocket_connect(user_id: str, payload: Dict[str, Any], client):
        """Handle WebSocket connection"""
        try:
            session_id = payload.get("session_id")
            device_info = payload.get("device_info", {})
            
            if not session_id:
                session_id = str(uuid.uuid4())
            
            # Store connection info
            connection_info = {
                "user_id": user_id,
                "session_id": session_id,
                "device_info": device_info,
                "connected_at": time.time(),
                "last_heartbeat": time.time()
            }
            
            await redis_manager.set_json(f"websocket:{user_id}:{session_id}", connection_info, ex=3600)
            await redis_manager.sadd(f"websocket:users", user_id)
            await redis_manager.sadd(f"websocket:user:{user_id}:sessions", session_id)
            
            # Send pending notifications
            await NotificationController._send_pending_notifications(user_id)
            
            return {"status": "connected", "session_id": session_id}
            
        except Exception as e:
            print(f"Error handling WebSocket connection for user {user_id}: {e}")
            raise
    
    @staticmethod
    async def websocket_disconnect(user_id: str, payload: Dict[str, Any], client):
        """Handle WebSocket disconnection"""
        try:
            session_id = payload.get("session_id")
            
            if session_id:
                await redis_manager.delete(f"websocket:{user_id}:{session_id}")
                await redis_manager.srem(f"websocket:user:{user_id}:sessions", session_id)
                
                # Check if user has any other active sessions
                active_sessions = await redis_manager.smembers(f"websocket:user:{user_id}:sessions")
                if not active_sessions:
                    await redis_manager.srem(f"websocket:users", user_id)
            
            return {"status": "disconnected"}
            
        except Exception as e:
            print(f"Error handling WebSocket disconnection for user {user_id}: {e}")
            raise
    
    # Helper methods
    @staticmethod
    async def _get_user_preferences(user_id: str) -> Dict[str, Any]:
        """Get user notification preferences"""
        preferences = await redis_manager.get_json(f"user:{user_id}:notification_preferences")
        if not preferences:
            # Default preferences
            preferences = {
                "realtime": True,
                "email": True,
                "sms": False,
                "push": True
            }
        return preferences
    
    @staticmethod
    async def _queue_email_notification(user_id: str, notification: Dict[str, Any]):
        """Queue email notification for user"""
        user = await User.find_by_id(user_id)
        if user and user.email:
            email_payload = {
                "to": user.email,
                "subject": notification.get("title", "Notification"),
                "body": notification.get("message"),
                "priority": notification.get("priority", "normal")
            }
            
            # Send to email queue
            await NotificationController.queue_email(email_payload, None)
    
    @staticmethod
    async def _queue_sms_notification(user_id: str, notification: Dict[str, Any]):
        """Queue SMS notification for user"""
        user = await User.find_by_id(user_id)
        if user and user.phone:
            sms_payload = {
                "phone": user.phone,
                "message": notification.get("message"),
                "priority": notification.get("priority", "normal")
            }
            
            # Send to SMS queue
            await NotificationController.send_sms(sms_payload, None)
    
    @staticmethod
    async def _send_push_notification(user_id: str, notification: Dict[str, Any]):
        """Send push notification to user's devices"""
        # Get user's registered devices
        device_tokens = await redis_manager.smembers(f"user:{user_id}:push_tokens")
        
        for token in device_tokens:
            try:
                await PushService.send_notification(token, notification)
            except Exception as e:
                print(f"Error sending push notification to token {token}: {e}")
    
    @staticmethod
    async def _get_admin_users() -> List[str]:
        """Get list of admin user IDs"""
        # Implementation depends on your user management system
        return await redis_manager.smembers("users:admin")
    
    @staticmethod
    async def _get_oncall_users(alert_type: str) -> List[str]:
        """Get on-call users for specific alert type"""
        return await redis_manager.smembers(f"oncall:{alert_type}")
    
    @staticmethod
    async def _send_pending_notifications(user_id: str):
        """Send pending notifications to newly connected user"""
        notification_ids = await redis_manager.lrange(f"user:{user_id}:notifications", 0, 9)  # Last 10
        
        for notification_id in notification_ids:
            notification = await redis_manager.get_json(f"notification:{notification_id}")
            if notification and not notification.get("read"):
                await WebSocketService.send_to_user(user_id, notification)
```

## WebSocket Service

```python
# app/services/websocket_service.py
from core.redis_manager import redis_manager
import json
import asyncio

class WebSocketService:
    @staticmethod
    async def send_to_user(user_id: str, data: dict):
        """Send data to all of user's active WebSocket connections"""
        sessions = await redis_manager.smembers(f"websocket:user:{user_id}:sessions")
        
        for session_id in sessions:
            connection_info = await redis_manager.get_json(f"websocket:{user_id}:{session_id}")
            if connection_info:
                # In a real implementation, you would send to the actual WebSocket connection
                # For now, we'll store it in a queue for the WebSocket handler to pick up
                message = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "data": data,
                    "timestamp": time.time()
                }
                await redis_manager.lpush(f"websocket:queue:{user_id}:{session_id}", json.dumps(message))
    
    @staticmethod
    async def broadcast_to_all(data: dict):
        """Broadcast data to all connected users"""
        connected_users = await redis_manager.smembers("websocket:users")
        
        for user_id in connected_users:
            await WebSocketService.send_to_user(user_id, data)
```

## Usage Examples

### User Notification
```python
# Send to: notifications/realtime/user/user123
{
    "title": "New Message",
    "message": "You have received a new message from John",
    "type": "message",
    "priority": "normal",
    "data": {
        "message_id": "msg_456",
        "sender": "john_doe"
    }
}
```

### Critical Alert
```python
# Send to: notifications/alerts/critical/system_failure
{
    "message": "Database connection failed",
    "source": "database_monitor",
    "severity": "critical",
    "affected_systems": ["user_service", "order_service"]
}
```

### Email Notification
```python
# Send to: notifications/email/send
{
    "to": "user@example.com",
    "subject": "Account Security Alert",
    "body": "Your account was accessed from a new device",
    "priority": "high"
}
```

This notification system provides comprehensive real-time communication capabilities with multiple delivery channels and priority handling.
