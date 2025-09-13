# Redis Integration

RouteMQ includes optional Redis integration for distributed caching, session management, and advanced rate limiting.

## Quick Setup

Enable Redis in your `.env` file:

```env
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password  # Optional
REDIS_USERNAME=your_username  # Optional
REDIS_MAX_CONNECTIONS=10
```

## Using Redis in Controllers

```python
from core.redis_manager import redis_manager
from core.controller import Controller

class SensorController(Controller):
    @staticmethod
    async def handle_temperature(sensor_id, payload, client):
        # Cache sensor data in Redis
        cache_key = f"sensor:{sensor_id}:latest"
        await redis_manager.set_json(cache_key, payload, ex=3600)  # Cache for 1 hour
        
        # Get cached historical data
        history_key = f"sensor:{sensor_id}:history"
        history = await redis_manager.get_json(history_key) or []
        
        return {"status": "processed", "cached": True}
```

## Redis Operations

The Redis manager provides comprehensive async operations:

```python
from core.redis_manager import redis_manager

# Basic operations
await redis_manager.set("key", "value", ex=60)  # Set with expiration
value = await redis_manager.get("key")
await redis_manager.delete("key")

# JSON operations
await redis_manager.set_json("config", {"setting": "value"}, ex=3600)
config = await redis_manager.get_json("config")

# Hash operations
await redis_manager.hset("user:123", "name", "John")
name = await redis_manager.hget("user:123", "name")

# Counters
count = await redis_manager.incr("page_views")
await redis_manager.expire("page_views", 86400)
```

## Benefits

- **Distributed Caching**: Share data across multiple instances
- **High Performance**: In-memory data storage
- **Rate Limiting**: Advanced rate limiting strategies
- **Session Management**: Store user sessions and state
- **Metrics Collection**: Real-time metrics and statistics

## Next Steps

- [Configuration](configuration.md) - Detailed Redis setup
- [Rate Limiting](../rate-limiting/README.md) - Redis-powered rate limiting
