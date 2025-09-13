# Controllers

Controllers handle the business logic for your MQTT routes.

## Topics

- [Creating Controllers](creating-controllers.md) - Basic controller structure
- [Controller Methods](controller-methods.md) - Handler method patterns
- [Using Redis in Controllers](redis-integration.md) - Caching and data storage
- [Database Operations](database-operations.md) - Working with models
- [Best Practices](best-practices.md) - Controller organization tips

## Quick Overview

Controllers contain the business logic that processes MQTT messages:

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import json
import time

class DeviceController(Controller):
    @staticmethod
    async def handle_control(device_id, payload, client):
        """Handle device control commands with Redis caching"""
        command = payload.get('command')
        
        # Check rate limiting info from middleware
        rate_limit_info = payload.get('rate_limit', {})
        remaining_requests = rate_limit_info.get('remaining', 0)
        
        # Log the command with rate limit info
        print(f"Controlling device {device_id}: {command} (Rate limit remaining: {remaining_requests})")
        
        # Cache command history in Redis
        history_key = f"device:{device_id}:commands"
        command_entry = {
            "command": command,
            "timestamp": time.time(),
            "remaining_rate_limit": remaining_requests
        }
        
        # Add to command history (keep last 100 commands)
        if redis_manager.is_enabled():
            history = await redis_manager.get_json(history_key) or []
            history.append(command_entry)
            if len(history) > 100:
                history = history[-100:]
            await redis_manager.set_json(history_key, history, ex=86400)  # 24 hours
        
        # Process the command
        if command == 'restart':
            result = await DeviceController.restart_device(device_id)
        elif command == 'shutdown':
            result = await DeviceController.shutdown_device(device_id)
        else:
            result = {"error": "Unknown command"}
        
        # Publish response
        response_topic = f"devices/{device_id}/control/response"
        client.publish(response_topic, json.dumps(result))
        
        return result
```

## Controller Features

- **Async Support**: All controller methods are async for non-blocking operations
- **Parameter Extraction**: Route parameters are automatically injected
- **Redis Integration**: Built-in Redis manager for caching and data storage
- **Database Access**: Direct access to database models
- **MQTT Client**: Publish responses or additional messages

## Next Steps

- [Creating Controllers](creating-controllers.md) - Learn controller basics
- [Redis Integration](redis-integration.md) - Use Redis in controllers
- [Database Operations](database-operations.md) - Work with database models
