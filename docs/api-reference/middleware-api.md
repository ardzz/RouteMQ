# Middleware API

Complete API reference for the RouteMQ Middleware interface and middleware development patterns.

## Middleware Abstract Class

The `Middleware` class is an abstract base class that all middleware components must extend. It defines the interface for intercepting and processing MQTT messages before they reach controllers.

### Import

```python
from core.middleware import Middleware
```

### Abstract Methods

#### handle(context, next_handler)

Process the request context and call the next handler in the middleware chain.

**Signature:**
```python
async def handle(self, context: Dict[str, Any], next_handler: Callable[[Dict[str, Any]], Awaitable[Any]]) -> Any
```

**Parameters:**
- `context` (Dict[str, Any]): Request context containing topic, payload, params, and client
- `next_handler` (Callable): The next handler in the middleware chain

**Returns:** Any - The result of the request handling

**Context Structure:**
```python
context = {
    'topic': str,           # Original MQTT topic
    'payload': Any,         # Message payload (parsed JSON or raw)
    'params': Dict[str, str], # Extracted route parameters
    'client': Any           # MQTT client instance
}
```

### Properties

#### logger

Class-level logger instance for all middleware.

**Type:** logging.Logger  
**Name:** "RouteMQ.Middleware"

**Example:**
```python
class MyMiddleware(Middleware):
    async def handle(self, context, next_handler):
        self.logger.info(f"Processing request for topic: {context['topic']}")
        return await next_handler(context)
```

## Creating Custom Middleware

### Basic Middleware Pattern

```python
from core.middleware import Middleware
from typing import Dict, Any, Callable, Awaitable

class LoggingMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable[[Dict[str, Any]], Awaitable[Any]]) -> Any:
        """Log request details before and after processing."""
        
        # Pre-processing
        self.logger.info(f"Incoming request: {context['topic']}")
        start_time = time.time()
        
        try:
            # Call next middleware or handler
            result = await next_handler(context)
            
            # Post-processing (success)
            duration = time.time() - start_time
            self.logger.info(f"Request completed in {duration:.3f}s: {context['topic']}")
            
            return result
            
        except Exception as e:
            # Post-processing (error)
            duration = time.time() - start_time
            self.logger.error(f"Request failed after {duration:.3f}s: {context['topic']} - {str(e)}")
            raise
```

### Authentication Middleware

```python
import jwt
from typing import Dict, Any

class AuthMiddleware(Middleware):
    def __init__(self, secret_key: str = None, required_roles: list = None):
        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY", "default-secret")
        self.required_roles = required_roles or []
    
    async def handle(self, context: Dict[str, Any], next_handler) -> Any:
        """Validate JWT token and check permissions."""
        
        payload = context.get('payload', {})
        
        # Extract token from payload
        token = None
        if isinstance(payload, dict):
            token = payload.get('token') or payload.get('auth_token')
        
        if not token:
            self.logger.warning(f"No auth token provided for: {context['topic']}")
            raise ValueError("Authentication token required")
        
        try:
            # Decode and validate token
            decoded = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            
            # Check required roles
            user_roles = decoded.get('roles', [])
            if self.required_roles and not any(role in user_roles for role in self.required_roles):
                raise ValueError(f"Insufficient permissions. Required: {self.required_roles}")
            
            # Add user info to context
            context['user'] = {
                'user_id': decoded.get('user_id'),
                'username': decoded.get('username'),
                'roles': user_roles
            }
            
            self.logger.info(f"Authenticated user {decoded.get('username')} for: {context['topic']}")
            
            # Continue to next handler
            return await next_handler(context)
            
        except jwt.ExpiredSignatureError:
            self.logger.warning(f"Expired token for: {context['topic']}")
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"Invalid token for: {context['topic']} - {str(e)}")
            raise ValueError("Invalid authentication token")
```

### Rate Limiting Middleware

```python
import time
from collections import defaultdict
from core.redis_manager import redis_manager

class RateLimitMiddleware(Middleware):
    def __init__(self, max_requests: int = 100, window_seconds: int = 60, 
                 key_func: Callable = None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_func = key_func or self._default_key_func
        self.local_cache = defaultdict(list)  # Fallback when Redis unavailable
    
    def _default_key_func(self, context: Dict[str, Any]) -> str:
        """Default key function uses client ID or topic."""
        client = context.get('client')
        if hasattr(client, '_client_id'):
            return f"rate_limit:{client._client_id}"
        return f"rate_limit:{context['topic']}"
    
    async def handle(self, context: Dict[str, Any], next_handler) -> Any:
        """Enforce rate limiting."""
        
        key = self.key_func(context)
        current_time = time.time()
        window_start = current_time - self.window_seconds
        
        # Try Redis first
        if await redis_manager.is_enabled():
            count = await self._redis_rate_limit(key, current_time, window_start)
        else:
            count = await self._local_rate_limit(key, current_time, window_start)
        
        if count > self.max_requests:
            self.logger.warning(f"Rate limit exceeded for {key}: {count}/{self.max_requests}")
            raise ValueError(f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds} seconds")
        
        self.logger.debug(f"Rate limit check passed for {key}: {count}/{self.max_requests}")
        return await next_handler(context)
    
    async def _redis_rate_limit(self, key: str, current_time: float, window_start: float) -> int:
        """Redis-based rate limiting with sliding window."""
        pipe = redis_manager.get_client().pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Add current request
        pipe.zadd(key, {str(current_time): current_time})
        
        # Count requests in window
        pipe.zcard(key)
        
        # Set expiry
        pipe.expire(key, self.window_seconds + 1)
        
        results = await pipe.execute()
        return results[2]  # Count from zcard
    
    async def _local_rate_limit(self, key: str, current_time: float, window_start: float) -> int:
        """Local memory-based rate limiting fallback."""
        # Clean old entries
        self.local_cache[key] = [t for t in self.local_cache[key] if t > window_start]
        
        # Add current request
        self.local_cache[key].append(current_time)
        
        return len(self.local_cache[key])
```

### Validation Middleware

```python
import re
from jsonschema import validate, ValidationError

class ValidationMiddleware(Middleware):
    def __init__(self, payload_schema: dict = None, param_rules: dict = None):
        self.payload_schema = payload_schema
        self.param_rules = param_rules or {}
    
    async def handle(self, context: Dict[str, Any], next_handler) -> Any:
        """Validate request parameters and payload."""
        
        # Validate route parameters
        if self.param_rules:
            await self._validate_parameters(context['params'])
        
        # Validate payload schema
        if self.payload_schema and isinstance(context['payload'], dict):
            await self._validate_payload(context['payload'])
        
        return await next_handler(context)
    
    async def _validate_parameters(self, params: Dict[str, str]):
        """Validate route parameters against rules."""
        for param_name, rule in self.param_rules.items():
            value = params.get(param_name)
            
            if value is None:
                raise ValueError(f"Missing required parameter: {param_name}")
            
            if isinstance(rule, str):  # Regex pattern
                if not re.match(rule, value):
                    raise ValueError(f"Invalid format for parameter {param_name}")
            
            elif isinstance(rule, list):  # Allowed values
                if value not in rule:
                    raise ValueError(f"Invalid value for {param_name}. Allowed: {rule}")
            
            elif callable(rule):  # Custom validator function
                if not rule(value):
                    raise ValueError(f"Validation failed for parameter {param_name}")
    
    async def _validate_payload(self, payload: dict):
        """Validate payload against JSON schema."""
        try:
            validate(instance=payload, schema=self.payload_schema)
        except ValidationError as e:
            raise ValueError(f"Payload validation failed: {e.message}")

# Usage example
device_validator = ValidationMiddleware(
    param_rules={
        'device_id': r'^[a-zA-Z0-9_-]{1,50}$',  # Alphanumeric, underscores, hyphens, 1-50 chars
        'command': ['start', 'stop', 'restart', 'status']  # Allowed values
    },
    payload_schema={
        "type": "object",
        "properties": {
            "timestamp": {"type": "number"},
            "value": {"type": "number", "minimum": 0}
        },
        "required": ["timestamp", "value"]
    }
)
```

### Monitoring Middleware

```python
import time
import psutil
from core.redis_manager import redis_manager

class MonitoringMiddleware(Middleware):
    def __init__(self, track_performance: bool = True, track_errors: bool = True):
        self.track_performance = track_performance
        self.track_errors = track_errors
    
    async def handle(self, context: Dict[str, Any], next_handler) -> Any:
        """Monitor request performance and errors."""
        
        topic = context['topic']
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss if self.track_performance else 0
        
        try:
            result = await next_handler(context)
            
            # Track successful request
            if self.track_performance:
                await self._track_performance(topic, start_time, start_memory, success=True)
            
            return result
            
        except Exception as e:
            # Track failed request
            if self.track_errors:
                await self._track_error(topic, str(e), type(e).__name__)
            
            if self.track_performance:
                await self._track_performance(topic, start_time, start_memory, success=False)
            
            raise
    
    async def _track_performance(self, topic: str, start_time: float, start_memory: int, success: bool):
        """Track performance metrics."""
        duration = time.time() - start_time
        end_memory = psutil.Process().memory_info().rss
        memory_used = end_memory - start_memory
        
        metrics = {
            'topic': topic,
            'duration_ms': round(duration * 1000, 2),
            'memory_used_bytes': memory_used,
            'success': success,
            'timestamp': time.time()
        }
        
        # Store in Redis if available
        if await redis_manager.is_enabled():
            key = f"metrics:performance:{topic}:{int(time.time())}"
            await redis_manager.set_json(key, metrics, ex=3600)  # Keep for 1 hour
        
        self.logger.info(f"Performance: {topic} - {duration*1000:.2f}ms, {memory_used}B memory")
    
    async def _track_error(self, topic: str, error_message: str, error_type: str):
        """Track error occurrences."""
        error_data = {
            'topic': topic,
            'error_message': error_message,
            'error_type': error_type,
            'timestamp': time.time()
        }
        
        # Store in Redis if available
        if await redis_manager.is_enabled():
            key = f"metrics:errors:{topic}:{int(time.time())}"
            await redis_manager.set_json(key, error_data, ex=86400)  # Keep for 24 hours
            
            # Increment error counter
            counter_key = f"metrics:error_count:{topic}"
            await redis_manager.incr(counter_key)
            await redis_manager.expire(counter_key, 3600)  # Reset every hour
        
        self.logger.error(f"Error tracked: {topic} - {error_type}: {error_message}")
```

## Middleware Execution Order

Middleware executes in the order specified in the middleware list:

```python
# Middleware executes in this order:
# 1. LoggingMiddleware (pre-processing)
# 2. AuthMiddleware (pre-processing)  
# 3. RateLimitMiddleware (pre-processing)
# 4. Handler execution
# 5. RateLimitMiddleware (post-processing)
# 6. AuthMiddleware (post-processing)
# 7. LoggingMiddleware (post-processing)

router.on("secure/endpoint", handler, middleware=[
    LoggingMiddleware(),      # Outermost - logs everything
    AuthMiddleware(),         # Authentication check
    RateLimitMiddleware()     # Innermost - rate limiting
])
```

## Context Modification

Middleware can modify the context for downstream handlers:

```python
class ContextEnrichmentMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler) -> Any:
        """Add additional context data."""
        
        # Add timestamp
        context['request_timestamp'] = time.time()
        
        # Add request ID for tracking
        context['request_id'] = str(uuid.uuid4())
        
        # Parse and enrich payload
        if isinstance(context['payload'], str):
            try:
                context['payload'] = json.loads(context['payload'])
            except json.JSONDecodeError:
                pass  # Keep as string
        
        # Add client information
        client = context['client']
        context['client_info'] = {
            'client_id': getattr(client, '_client_id', 'unknown'),
            'connected_at': getattr(client, '_connected_at', None)
        }
        
        return await next_handler(context)
```

## Error Handling in Middleware

### Graceful Error Handling

```python
class ErrorHandlingMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler) -> Any:
        """Handle errors gracefully and provide consistent responses."""
        
        try:
            return await next_handler(context)
            
        except ValueError as e:
            # Client errors (4xx equivalent)
            self.logger.warning(f"Client error for {context['topic']}: {str(e)}")
            return {
                "error": True,
                "type": "client_error",
                "message": str(e),
                "timestamp": time.time()
            }
            
        except Exception as e:
            # Server errors (5xx equivalent)
            self.logger.error(f"Server error for {context['topic']}: {str(e)}")
            return {
                "error": True,
                "type": "server_error", 
                "message": "Internal server error",
                "timestamp": time.time()
            }
```

### Circuit Breaker Pattern

```python
class CircuitBreakerMiddleware(Middleware):
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def handle(self, context: Dict[str, Any], next_handler) -> Any:
        """Implement circuit breaker pattern."""
        
        current_time = time.time()
        
        # Check if circuit should move from OPEN to HALF_OPEN
        if self.state == "OPEN" and current_time - self.last_failure_time > self.recovery_timeout:
            self.state = "HALF_OPEN"
            self.logger.info("Circuit breaker moving to HALF_OPEN state")
        
        # Reject requests if circuit is OPEN
        if self.state == "OPEN":
            self.logger.warning(f"Circuit breaker is OPEN, rejecting request: {context['topic']}")
            raise ValueError("Service temporarily unavailable")
        
        try:
            result = await next_handler(context)
            
            # Success - reset failure count if in HALF_OPEN
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                self.logger.info("Circuit breaker reset to CLOSED state")
            
            return result
            
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = current_time
            
            # Open circuit if threshold reached
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.logger.error(f"Circuit breaker opened after {self.failure_count} failures")
            
            raise
```

## Testing Middleware

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock
from app.middleware.auth_middleware import AuthMiddleware

@pytest.mark.asyncio
async def test_auth_middleware_success():
    middleware = AuthMiddleware(secret_key="test-secret")
    
    # Mock context with valid token
    context = {
        'topic': 'test/topic',
        'payload': {'token': 'valid.jwt.token'},
        'params': {},
        'client': None
    }
    
    # Mock next handler
    next_handler = AsyncMock(return_value={"success": True})
    
    # Test middleware
    result = await middleware.handle(context, next_handler)
    
    # Assertions
    assert result == {"success": True}
    next_handler.assert_called_once_with(context)
    assert 'user' in context  # User info should be added

@pytest.mark.asyncio
async def test_auth_middleware_failure():
    middleware = AuthMiddleware()
    
    # Mock context without token
    context = {
        'topic': 'test/topic',
        'payload': {},
        'params': {},
        'client': None
    }
    
    next_handler = AsyncMock()
    
    # Test middleware raises exception
    with pytest.raises(ValueError, match="Authentication token required"):
        await middleware.handle(context, next_handler)
    
    # Next handler should not be called
    next_handler.assert_not_called()
```

## Best Practices

### 1. Single Responsibility
Each middleware should have one clear purpose:

```python
# Good - focused on one concern
class CorsMiddleware(Middleware): pass
class AuthMiddleware(Middleware): pass  
class RateLimitMiddleware(Middleware): pass

# Avoid - doing too much
class MegaMiddleware(Middleware):  # Auth + CORS + Rate limiting + Logging
    pass
```

### 2. Configurable Behavior
Make middleware configurable:

```python
class CacheMiddleware(Middleware):
    def __init__(self, ttl: int = 300, cache_key_func: Callable = None):
        self.ttl = ttl
        self.cache_key_func = cache_key_func or self._default_cache_key
```

### 3. Graceful Degradation
Handle dependencies gracefully:

```python
class RedisMiddleware(Middleware):
    async def handle(self, context, next_handler):
        if not await redis_manager.is_enabled():
            # Fall back to next handler without Redis functionality
            self.logger.warning("Redis unavailable, skipping cache middleware")
            return await next_handler(context)
        
        # Redis-based logic here
```

### 4. Performance Considerations
Keep middleware lightweight:

```python
class EfficientMiddleware(Middleware):
    def __init__(self):
        # Do expensive initialization once
        self.compiled_regex = re.compile(r'pattern')
        self.static_data = load_static_configuration()
    
    async def handle(self, context, next_handler):
        # Fast operations only
        if self.compiled_regex.match(context['topic']):
            # Quick validation
            pass
        return await next_handler(context)
```
