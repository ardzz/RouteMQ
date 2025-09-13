# Redis Manager API

Complete API reference for the RouteMQ Redis Manager class and Redis integration patterns.

## RedisManager Class

The `RedisManager` class provides async Redis operations with connection pooling, error handling, and graceful fallback when Redis is unavailable. It implements the singleton pattern to ensure one Redis connection per application.

### Import

```python
from core.redis_manager import redis_manager
```

### Global Instance

RouteMQ provides a pre-configured global Redis manager instance:

```python
# Use the global instance (recommended)
from core.redis_manager import redis_manager

# Or create your own instance
from core.redis_manager import RedisManager
custom_redis = RedisManager()
```

## Configuration

Configure Redis through environment variables:

```bash
# Enable/disable Redis
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

## Connection Management

### initialize()

Initialize Redis connection pool and test connectivity.

**Signature:**
```python
async def initialize() -> bool
```

**Returns:** bool - True if connection successful, False otherwise

**Example:**
```python
# Initialize Redis connection
success = await redis_manager.initialize()
if success:
    print("Redis connected successfully")
else:
    print("Redis connection failed")
```

### disconnect()

Close Redis connections and clean up resources.

**Signature:**
```python
async def disconnect() -> None
```

**Example:**
```python
# Clean shutdown
await redis_manager.disconnect()
```

### is_enabled()

Check if Redis is enabled and available.

**Signature:**
```python
def is_enabled() -> bool
```

**Returns:** bool - True if Redis is enabled and connected

**Example:**
```python
if redis_manager.is_enabled():
    # Use Redis operations
    await redis_manager.set("key", "value")
else:
    # Fallback to alternative storage
    local_cache["key"] = "value"
```

### get_client()

Get the underlying Redis client instance for advanced operations.

**Signature:**
```python
def get_client() -> Optional[Redis]
```

**Returns:** Redis client instance or None if not enabled

**Example:**
```python
# Advanced Redis operations
client = redis_manager.get_client()
if client:
    await client.pipeline().set("key1", "value1").set("key2", "value2").execute()
```

## Basic Operations

### get(key)

Get value by key.

**Signature:**
```python
async def get(key: str) -> Optional[str]
```

**Parameters:**
- `key` (str): Redis key

**Returns:** str | None - Value as string or None if not found

**Example:**
```python
# Get a value
value = await redis_manager.get("user:123:name")
if value:
    print(f"User name: {value}")
```

### set(key, value, ex=None, px=None, nx=False, xx=False)

Set key-value pair with optional expiration and conditions.

**Signature:**
```python
async def set(key: str, value: Union[str, int, float], ex: Optional[int] = None,
              px: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool
```

**Parameters:**
- `key` (str): Redis key
- `value` (str | int | float): Value to set
- `ex` (int, optional): Expire time in seconds
- `px` (int, optional): Expire time in milliseconds  
- `nx` (bool): Only set if key doesn't exist
- `xx` (bool): Only set if key exists

**Returns:** bool - True if successful

**Example:**
```python
# Simple set
await redis_manager.set("session:abc123", "user_data")

# Set with expiration (1 hour)
await redis_manager.set("temp:token", "xyz789", ex=3600)

# Set only if key doesn't exist
success = await redis_manager.set("unique:id", "123", nx=True)

# Set only if key exists
success = await redis_manager.set("existing:key", "new_value", xx=True)
```

### delete(*keys)

Delete one or more keys.

**Signature:**
```python
async def delete(*keys: str) -> int
```

**Parameters:**
- `keys` (str): One or more keys to delete

**Returns:** int - Number of keys deleted

**Example:**
```python
# Delete single key
deleted = await redis_manager.delete("temp:data")

# Delete multiple keys
deleted = await redis_manager.delete("key1", "key2", "key3")
print(f"Deleted {deleted} keys")
```

### exists(key)

Check if key exists.

**Signature:**
```python
async def exists(key: str) -> bool
```

**Parameters:**
- `key` (str): Redis key to check

**Returns:** bool - True if key exists

**Example:**
```python
if await redis_manager.exists("user:123"):
    user_data = await redis_manager.get("user:123")
```

### expire(key, time)

Set expiration time for a key.

**Signature:**
```python
async def expire(key: str, time: int) -> bool
```

**Parameters:**
- `key` (str): Redis key
- `time` (int): Expiration time in seconds

**Returns:** bool - True if successful

**Example:**
```python
# Set key to expire in 5 minutes
await redis_manager.expire("session:abc123", 300)
```

### ttl(key)

Get time to live for a key.

**Signature:**
```python
async def ttl(key: str) -> int
```

**Parameters:**
- `key` (str): Redis key

**Returns:** int - TTL in seconds, -1 if no expiry, -2 if key doesn't exist

**Example:**
```python
ttl = await redis_manager.ttl("session:abc123")
if ttl > 0:
    print(f"Session expires in {ttl} seconds")
elif ttl == -1:
    print("Session never expires")
else:
    print("Session doesn't exist")
```

## Numeric Operations

### incr(key, amount=1)

Increment key value by amount.

**Signature:**
```python
async def incr(key: str, amount: int = 1) -> Optional[int]
```

**Parameters:**
- `key` (str): Redis key
- `amount` (int): Amount to increment (default: 1)

**Returns:** int | None - New value or None if error

**Example:**
```python
# Increment counter
new_value = await redis_manager.incr("page:views")
print(f"Page views: {new_value}")

# Increment by custom amount
views = await redis_manager.incr("api:calls", 5)

# Rate limiting example
current_requests = await redis_manager.incr("rate_limit:user:123")
if current_requests > 100:
    raise ValueError("Rate limit exceeded")
```

## Hash Operations

### hset(name, key=None, value=None, mapping=None)

Set hash field(s).

**Signature:**
```python
async def hset(name: str, key: str = None, value: str = None,
               mapping: Dict[str, Any] = None) -> int
```

**Parameters:**
- `name` (str): Hash name
- `key` (str): Field key (for single field)
- `value` (str): Field value (for single field)
- `mapping` (dict): Dictionary of field-value pairs

**Returns:** int - Number of fields added

**Example:**
```python
# Set single hash field
await redis_manager.hset("user:123", "name", "John Doe")

# Set multiple hash fields
await redis_manager.hset("user:123", mapping={
    "email": "john@example.com",
    "age": "30",
    "status": "active"
})
```

### hget(name, key)

Get hash field value.

**Signature:**
```python
async def hget(name: str, key: str) -> Optional[str]
```

**Parameters:**
- `name` (str): Hash name
- `key` (str): Field key

**Returns:** str | None - Field value or None

**Example:**
```python
# Get user name from hash
name = await redis_manager.hget("user:123", "name")
if name:
    print(f"User name: {name}")

# Get user profile data
email = await redis_manager.hget("user:123", "email")
age = await redis_manager.hget("user:123", "age")
```

## JSON Operations

### set_json(key, value, ex=None, px=None, nx=False, xx=False)

Serialize and store JSON data.

**Signature:**
```python
async def set_json(key: str, value: Any, ex: Optional[int] = None,
                   px: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool
```

**Parameters:**
- `key` (str): Redis key
- `value` (Any): Value to serialize as JSON
- Other parameters same as `set()`

**Returns:** bool - True if successful

**Example:**
```python
# Store complex data structure
user_data = {
    "id": 123,
    "name": "John Doe",
    "preferences": {
        "theme": "dark",
        "notifications": True
    },
    "tags": ["admin", "developer"]
}

await redis_manager.set_json("user:123:profile", user_data, ex=3600)
```

### get_json(key)

Retrieve and deserialize JSON data.

**Signature:**
```python
async def get_json(key: str) -> Optional[Any]
```

**Parameters:**
- `key` (str): Redis key

**Returns:** Any | None - Deserialized value or None

**Example:**
```python
# Retrieve complex data structure
user_data = await redis_manager.get_json("user:123:profile")
if user_data:
    print(f"User: {user_data['name']}")
    print(f"Theme: {user_data['preferences']['theme']}")
```

## Common Usage Patterns

### Caching

```python
async def get_user_with_cache(user_id: str):
    """Get user data with Redis caching."""
    cache_key = f"user:{user_id}"
    
    # Try cache first
    cached_user = await redis_manager.get_json(cache_key)
    if cached_user:
        return cached_user
    
    # Fetch from database
    user = await database.get_user(user_id)
    if user:
        # Cache for 1 hour
        await redis_manager.set_json(cache_key, user, ex=3600)
    
    return user
```

### Session Management

```python
import uuid
import json

class SessionManager:
    @staticmethod
    async def create_session(user_id: str, data: dict) -> str:
        """Create a new user session."""
        session_id = str(uuid.uuid4())
        session_key = f"session:{session_id}"
        
        session_data = {
            "user_id": user_id,
            "created_at": time.time(),
            **data
        }
        
        # Session expires in 24 hours
        await redis_manager.set_json(session_key, session_data, ex=86400)
        return session_id
    
    @staticmethod
    async def get_session(session_id: str) -> Optional[dict]:
        """Get session data."""
        session_key = f"session:{session_id}"
        return await redis_manager.get_json(session_key)
    
    @staticmethod
    async def delete_session(session_id: str) -> bool:
        """Delete session."""
        session_key = f"session:{session_id}"
        deleted = await redis_manager.delete(session_key)
        return deleted > 0
```

### Rate Limiting

```python
import time

class RateLimiter:
    @staticmethod
    async def check_rate_limit(identifier: str, max_requests: int = 100, 
                              window_seconds: int = 3600) -> bool:
        """Check if request is within rate limit."""
        current_time = int(time.time())
        window_start = current_time - window_seconds
        
        # Use sorted set for sliding window
        key = f"rate_limit:{identifier}"
        
        # Remove old entries
        client = redis_manager.get_client()
        if client:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)
            results = await pipe.execute()
            
            current_requests = results[2]  # Count from zcard
            return current_requests <= max_requests
        
        return True  # Allow if Redis unavailable
```

### Distributed Locking

```python
import asyncio
import time

class DistributedLock:
    def __init__(self, key: str, timeout: int = 10):
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.identifier = str(uuid.uuid4())
    
    async def acquire(self) -> bool:
        """Acquire distributed lock."""
        end_time = time.time() + self.timeout
        
        while time.time() < end_time:
            # Try to acquire lock
            if await redis_manager.set(self.key, self.identifier, ex=self.timeout, nx=True):
                return True
            
            # Wait before retrying
            await asyncio.sleep(0.001)
        
        return False
    
    async def release(self) -> bool:
        """Release distributed lock."""
        # Lua script to atomically check and delete
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        client = redis_manager.get_client()
        if client:
            result = await client.eval(lua_script, 1, self.key, self.identifier)
            return bool(result)
        
        return False
    
    async def __aenter__(self):
        if not await self.acquire():
            raise TimeoutError(f"Could not acquire lock: {self.key}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()

# Usage
async def critical_section():
    async with DistributedLock("resource:123", timeout=30):
        # Only one process can execute this at a time
        await process_critical_resource()
```

### Pub/Sub Messaging

```python
class PubSubManager:
    @staticmethod
    async def publish(channel: str, message: dict):
        """Publish message to channel."""
        client = redis_manager.get_client()
        if client:
            await client.publish(channel, json.dumps(message))
    
    @staticmethod
    async def subscribe(channels: list, handler: callable):
        """Subscribe to channels and handle messages."""
        client = redis_manager.get_client()
        if not client:
            return
        
        pubsub = client.pubsub()
        await pubsub.subscribe(*channels)
        
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        await handler(message['channel'], data)
                    except Exception as e:
                        logger.error(f"Error handling pubsub message: {e}")
        finally:
            await pubsub.close()

# Usage
async def handle_notification(channel: str, data: dict):
    print(f"Received notification on {channel}: {data}")

# Publish
await PubSubManager.publish("notifications", {
    "type": "user_login",
    "user_id": 123,
    "timestamp": time.time()
})

# Subscribe
await PubSubManager.subscribe(["notifications"], handle_notification)
```

## Error Handling

The Redis Manager handles errors gracefully:

```python
# All operations return sensible defaults on error
value = await redis_manager.get("nonexistent_key")  # Returns None
success = await redis_manager.set("key", "value")   # Returns False if failed
count = await redis_manager.delete("key")           # Returns 0 if failed

# Check if Redis is available before critical operations
if redis_manager.is_enabled():
    await redis_manager.set("important_data", data)
else:
    # Fallback to alternative storage
    await database.save_data(data)
```

## Best Practices

### 1. Use JSON Methods for Complex Data
```python
# Good - structured data
await redis_manager.set_json("user:123", {"name": "John", "age": 30})

# Avoid - manual serialization
await redis_manager.set("user:123", json.dumps({"name": "John", "age": 30}))
```

### 2. Set Appropriate Expiration Times
```python
# Cache data with reasonable TTL
await redis_manager.set_json("cache:expensive_query", result, ex=3600)  # 1 hour

# Session data with longer TTL
await redis_manager.set_json("session:abc123", session_data, ex=86400)  # 24 hours
```

### 3. Use Descriptive Key Patterns
```python
# Good - clear, hierarchical keys
"user:123:profile"
"session:abc123:data"
"cache:product:456"
"rate_limit:user:123"

# Avoid - unclear keys
"u123"
"data"
"temp"
```

### 4. Handle Redis Unavailability
```python
async def robust_cache_get(key: str):
    """Get from cache with fallback."""
    if redis_manager.is_enabled():
        return await redis_manager.get_json(key)
    return None  # Graceful fallback

async def robust_cache_set(key: str, value: Any, ex: int = None):
    """Set cache with error handling."""
    if redis_manager.is_enabled():
        return await redis_manager.set_json(key, value, ex=ex)
    return False  # Fail silently if Redis unavailable
```
