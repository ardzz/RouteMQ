# Using Redis in Controllers

Redis provides powerful caching, session management, and data storage capabilities for your RouteMQ controllers. This guide shows how to integrate Redis operations in your controller methods.

## Redis Manager

RouteMQ includes a built-in Redis manager that provides async operations with connection pooling and error handling.

### Basic Usage

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import json

class CachedController(Controller):
    @staticmethod
    async def handle_data(device_id: str, payload, client):
        """Handle data with Redis caching"""
        cache_key = f"device:{device_id}:last_data"
        
        # Store data in Redis
        await redis_manager.set_json(cache_key, payload, ex=3600)  # 1 hour TTL
        
        # Process the data
        result = await CachedController.process_data(payload)
        
        return result
```

## Configuration

Redis is configured through environment variables:

```bash
# Enable Redis
ENABLE_REDIS=true

# Connection settings
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password
REDIS_USERNAME=your_username

# Connection pool settings
REDIS_MAX_CONNECTIONS=10
REDIS_SOCKET_TIMEOUT=5.0
REDIS_SOCKET_CONNECT_TIMEOUT=5.0
```

## Basic Operations

### String Operations

```python
from core.controller import Controller
from core.redis_manager import redis_manager

class StringController(Controller):
    @staticmethod
    async def handle_counter(device_id: str, payload, client):
        """Handle counter operations"""
        counter_key = f"device:{device_id}:counter"
        
        # Get current value
        current = await redis_manager.get(counter_key)
        print(f"Current counter: {current}")
        
        # Increment counter
        new_value = await redis_manager.incr(counter_key, 1)
        
        # Set expiration (24 hours)
        await redis_manager.expire(counter_key, 86400)
        
        return {"counter": new_value}
    
    @staticmethod
    async def handle_status(device_id: str, payload, client):
        """Handle device status"""
        status_key = f"device:{device_id}:status"
        status = payload.get('status')
        
        # Store status with 30 minute expiration
        await redis_manager.set(status_key, status, ex=1800)
        
        # Check if key exists
        exists = await redis_manager.exists(status_key)
        
        # Get TTL
        ttl = await redis_manager.ttl(status_key)
        
        return {"status": status, "expires_in": ttl}
```

### JSON Operations

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import time

class JsonController(Controller):
    @staticmethod
    async def handle_device_info(device_id: str, payload, client):
        """Handle device information with JSON storage"""
        info_key = f"device:{device_id}:info"
        
        # Get existing info
        existing_info = await redis_manager.get_json(info_key) or {}
        
        # Update with new data
        existing_info.update(payload)
        existing_info['last_updated'] = time.time()
        
        # Store updated info
        await redis_manager.set_json(info_key, existing_info, ex=3600)
        
        return existing_info
    
    @staticmethod
    async def handle_sensor_history(device_id: str, payload, client):
        """Maintain sensor reading history"""
        history_key = f"device:{device_id}:sensor_history"
        
        # Get existing history
        history = await redis_manager.get_json(history_key) or []
        
        # Add new reading
        reading = {
            "timestamp": time.time(),
            "temperature": payload.get('temperature'),
            "humidity": payload.get('humidity')
        }
        history.append(reading)
        
        # Keep only last 100 readings
        if len(history) > 100:
            history = history[-100:]
        
        # Store updated history
        await redis_manager.set_json(history_key, history, ex=86400)
        
        return {"readings_count": len(history)}
```

### Hash Operations

```python
from core.controller import Controller
from core.redis_manager import redis_manager

class HashController(Controller):
    @staticmethod
    async def handle_device_config(device_id: str, payload, client):
        """Handle device configuration using Redis hashes"""
        config_hash = f"device:{device_id}:config"
        
        # Set multiple configuration values
        config_data = {
            "sampling_rate": payload.get('sampling_rate', 60),
            "alert_threshold": payload.get('alert_threshold', 80),
            "enabled": payload.get('enabled', True)
        }
        
        # Store configuration in hash
        await redis_manager.hset(config_hash, mapping=config_data)
        
        # Get specific config value
        sampling_rate = await redis_manager.hget(config_hash, "sampling_rate")
        
        return {"config_updated": True, "sampling_rate": sampling_rate}
```

## Advanced Patterns

### Caching with Fallback

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import json

class CacheController(Controller):
    @staticmethod
    async def handle_expensive_operation(device_id: str, payload, client):
        """Handle expensive operations with caching"""
        cache_key = f"device:{device_id}:expensive_result"
        
        # Try to get from cache first
        cached_result = await redis_manager.get_json(cache_key)
        if cached_result:
            print("Cache hit!")
            
            # Add cache metadata
            cached_result['from_cache'] = True
            return cached_result
        
        print("Cache miss - performing expensive operation")
        
        # Perform expensive operation
        result = await CacheController.expensive_operation(device_id, payload)
        
        # Cache the result for 5 minutes
        await redis_manager.set_json(cache_key, result, ex=300)
        
        result['from_cache'] = False
        return result
    
    @staticmethod
    async def expensive_operation(device_id: str, payload):
        """Simulate expensive operation"""
        import asyncio
        await asyncio.sleep(2)  # Simulate delay
        
        return {
            "device_id": device_id,
            "processed_data": payload,
            "timestamp": time.time()
        }
```

### Rate Limiting

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import time

class RateLimitController(Controller):
    @staticmethod
    async def handle_rate_limited(device_id: str, payload, client):
        """Handle requests with rate limiting"""
        rate_key = f"rate_limit:device:{device_id}"
        window_size = 60  # 1 minute window
        max_requests = 10  # 10 requests per minute
        
        current_time = int(time.time())
        window_start = current_time - (current_time % window_size)
        
        # Create time-based key
        window_key = f"{rate_key}:{window_start}"
        
        # Increment request count
        request_count = await redis_manager.incr(window_key, 1)
        
        # Set expiration on first request in window
        if request_count == 1:
            await redis_manager.expire(window_key, window_size)
        
        # Check if rate limit exceeded
        if request_count > max_requests:
            error_response = {
                "error": "Rate limit exceeded",
                "limit": max_requests,
                "window": window_size,
                "retry_after": window_size - (current_time % window_size)
            }
            
            error_topic = f"devices/{device_id}/rate_limit_error"
            client.publish(error_topic, json.dumps(error_response))
            
            return error_response
        
        # Process the request
        result = await RateLimitController.process_request(payload)
        
        # Add rate limit info to response
        result['rate_limit'] = {
            "requests": request_count,
            "limit": max_requests,
            "remaining": max_requests - request_count,
            "window": window_size
        }
        
        return result
```

### Session Management

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import uuid
import time

class SessionController(Controller):
    @staticmethod
    async def handle_login(device_id: str, payload, client):
        """Handle device login with session management"""
        credentials = payload.get('credentials')
        
        # Validate credentials (simplified)
        if not SessionController.validate_credentials(credentials):
            return {"error": "Invalid credentials"}
        
        # Create session
        session_id = str(uuid.uuid4())
        session_key = f"session:{session_id}"
        
        session_data = {
            "device_id": device_id,
            "created_at": time.time(),
            "last_activity": time.time(),
            "permissions": ["read", "write"]
        }
        
        # Store session with 1 hour expiration
        await redis_manager.set_json(session_key, session_data, ex=3600)
        
        # Store device -> session mapping
        device_session_key = f"device:{device_id}:session"
        await redis_manager.set(device_session_key, session_id, ex=3600)
        
        response_topic = f"devices/{device_id}/login_response"
        client.publish(response_topic, json.dumps({
            "session_id": session_id,
            "expires_in": 3600
        }))
        
        return {"session_created": True}
    
    @staticmethod
    async def handle_authenticated_request(device_id: str, payload, client):
        """Handle request requiring authentication"""
        session_id = payload.get('session_id')
        
        if not session_id:
            return {"error": "Session ID required"}
        
        # Get session data
        session_key = f"session:{session_id}"
        session_data = await redis_manager.get_json(session_key)
        
        if not session_data:
            return {"error": "Invalid or expired session"}
        
        # Update last activity
        session_data['last_activity'] = time.time()
        await redis_manager.set_json(session_key, session_data, ex=3600)
        
        # Process authenticated request
        result = await SessionController.process_authenticated_request(
            device_id, payload, session_data
        )
        
        return result
```

### Distributed Locking

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import asyncio
import time

class LockController(Controller):
    @staticmethod
    async def handle_exclusive_operation(device_id: str, payload, client):
        """Handle operation requiring exclusive access"""
        lock_key = f"lock:device:{device_id}"
        lock_timeout = 30  # 30 seconds
        
        # Acquire lock
        lock_acquired = await redis_manager.set(
            lock_key, 
            "locked", 
            ex=lock_timeout, 
            nx=True  # Only set if not exists
        )
        
        if not lock_acquired:
            return {"error": "Device is busy, try again later"}
        
        try:
            # Perform exclusive operation
            result = await LockController.exclusive_operation(device_id, payload)
            
            return result
            
        finally:
            # Always release the lock
            await redis_manager.delete(lock_key)
    
    @staticmethod
    async def exclusive_operation(device_id: str, payload):
        """Perform operation that requires exclusive access"""
        # Simulate work
        await asyncio.sleep(5)
        
        return {
            "device_id": device_id,
            "operation": "completed",
            "timestamp": time.time()
        }
```

## Error Handling

Always handle Redis errors gracefully:

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import logging

class RobustController(Controller):
    @staticmethod
    async def handle_with_fallback(device_id: str, payload, client):
        """Handle operations with Redis fallback"""
        try:
            # Try Redis operation
            if redis_manager.is_enabled():
                cached_data = await redis_manager.get_json(f"device:{device_id}:data")
                if cached_data:
                    return cached_data
            
            # Fallback to processing without cache
            result = await RobustController.process_data(payload)
            
            # Try to cache result
            if redis_manager.is_enabled():
                await redis_manager.set_json(f"device:{device_id}:data", result, ex=300)
            
            return result
            
        except Exception as e:
            logging.error(f"Redis operation failed: {e}")
            
            # Continue without Redis
            return await RobustController.process_data(payload)
```

## Performance Tips

### 1. Use Appropriate Expiration Times

```python
# Short-lived data (sensor readings)
await redis_manager.set_json("sensor:temp", data, ex=300)  # 5 minutes

# Medium-lived data (device status)
await redis_manager.set_json("device:status", data, ex=1800)  # 30 minutes

# Long-lived data (configuration)
await redis_manager.set_json("device:config", data, ex=86400)  # 24 hours
```

### 2. Batch Operations

```python
# Avoid multiple round trips
for i in range(100):
    await redis_manager.set(f"key:{i}", f"value:{i}")  # Inefficient

# Instead, prepare data and use hashes or JSON
data = {f"key:{i}": f"value:{i}" for i in range(100)}
await redis_manager.set_json("batch_data", data)
```

### 3. Connection Management

The Redis manager handles connection pooling automatically, but you can check connection status:

```python
@staticmethod
async def handle_data(device_id: str, payload, client):
    """Handle data with connection check"""
    if not redis_manager.is_enabled():
        # Redis not available, use alternative storage
        return await AlternativeController.store_data(device_id, payload)
    
    # Redis available, use normal flow
    await redis_manager.set_json(f"device:{device_id}:data", payload)
    return {"stored": True}
```

## Next Steps

- [Database Operations](database-operations.md) - Work with database models
- [Best Practices](best-practices.md) - Follow controller organization guidelines
