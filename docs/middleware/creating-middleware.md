# Creating Middleware

Learn how to create custom middleware for RouteMQ to process messages before they reach your route handlers.

## Middleware Basics

Middleware in RouteMQ follows the "onion" pattern where each middleware wraps the next layer in the chain. All middleware must extend the base `Middleware` class and implement the `handle` method.

### Basic Middleware Structure

```python
from core.middleware import Middleware
from typing import Dict, Any, Callable, Awaitable

class YourMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable[[Dict[str, Any]], Awaitable[Any]]) -> Any:
        # Pre-processing: runs before the handler
        # Modify context, validate data, etc.
        
        # Call the next middleware or handler
        result = await next_handler(context)
        
        # Post-processing: runs after the handler
        # Modify response, log results, etc.
        
        return result
```

## Understanding the Context

The `context` dictionary contains all information about the current message:

```python
context = {
    'topic': 'sensors/device123/temperature',    # Original MQTT topic
    'payload': {'value': 25.6, 'unit': 'C'},     # Message payload (parsed)
    'params': {'device_id': 'device123'},        # Route parameters
    'client': mqtt_client_instance,              # MQTT client for publishing
    'route': route_object,                       # Matched route object
    # Additional data added by previous middleware
}
```

## Simple Middleware Examples

### Request Logging Middleware

```python
import time
from core.middleware import Middleware

class RequestLoggerMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Log incoming requests with timing information"""
        
        start_time = time.time()
        topic = context['topic']
        
        self.logger.info(f"Processing message on topic: {topic}")
        
        try:
            result = await next_handler(context)
            
            duration = time.time() - start_time
            self.logger.info(f"Message processed successfully in {duration:.3f}s")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Message processing failed after {duration:.3f}s: {e}")
            raise
```

### Request ID Middleware

```python
import uuid
from core.middleware import Middleware

class RequestIdMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Add unique request ID to context"""
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        context['request_id'] = request_id
        
        # Add to logger context for tracing
        logger = self.logger.getChild(f"req-{request_id[:8]}")
        context['logger'] = logger
        
        logger.info(f"Request started - Topic: {context['topic']}")
        
        try:
            result = await next_handler(context)
            logger.info("Request completed successfully")
            return result
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
```

### Data Validation Middleware

```python
from marshmallow import Schema, ValidationError, fields
from core.middleware import Middleware

class SensorDataSchema(Schema):
    device_id = fields.Str(required=True)
    value = fields.Float(required=True)
    timestamp = fields.DateTime(required=True)
    unit = fields.Str(missing='unknown')

class ValidationMiddleware(Middleware):
    def __init__(self, schema: Schema):
        self.schema = schema
    
    async def handle(self, context, next_handler):
        """Validate message payload against schema"""
        
        try:
            # Validate and deserialize payload
            validated_data = self.schema.load(context['payload'])
            context['validated_payload'] = validated_data
            
            self.logger.debug("Payload validation successful")
            
        except ValidationError as e:
            self.logger.warning(f"Payload validation failed: {e.messages}")
            return {
                "error": "validation_failed",
                "details": e.messages,
                "status": "invalid_payload"
            }
        
        return await next_handler(context)

# Usage
validation_middleware = ValidationMiddleware(SensorDataSchema())
```

## Advanced Middleware Patterns

### Conditional Processing Middleware

```python
class ConditionalMiddleware(Middleware):
    def __init__(self, condition_func: Callable, middleware_to_apply: Middleware):
        self.condition_func = condition_func
        self.middleware_to_apply = middleware_to_apply
    
    async def handle(self, context, next_handler):
        """Apply middleware only if condition is met"""
        
        if self.condition_func(context):
            # Apply conditional middleware
            async def conditional_next(ctx):
                return await self.middleware_to_apply.handle(ctx, next_handler)
            
            return await conditional_next(context)
        else:
            # Skip conditional middleware
            return await next_handler(context)

# Usage: Only apply auth middleware for certain topics
def needs_auth(context):
    return context['topic'].startswith('secure/')

conditional_auth = ConditionalMiddleware(needs_auth, AuthMiddleware())
```

### Error Handling Middleware

```python
class ErrorHandlingMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Centralized error handling with recovery"""
        
        try:
            return await next_handler(context)
            
        except ValidationError as e:
            self.logger.warning(f"Validation error: {e}")
            return {
                "error": "validation_failed",
                "message": str(e),
                "retry": False
            }
            
        except ConnectionError as e:
            self.logger.error(f"Connection error: {e}")
            return {
                "error": "connection_failed",
                "message": "External service unavailable",
                "retry": True
            }
            
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return {
                "error": "internal_error",
                "message": "An unexpected error occurred",
                "retry": False
            }
```

### Context Enhancement Middleware

```python
from core.redis_manager import redis_manager
from core.model import Model

class ContextEnhancementMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Enhance context with additional data"""
        
        # Add device information if device_id is available
        device_id = context.get('params', {}).get('device_id')
        if device_id:
            # Fetch device info from database
            device = await self._get_device_info(device_id)
            if device:
                context['device'] = device
                context['device_config'] = device.config
        
        # Add user information from session
        session_id = context.get('payload', {}).get('session_id')
        if session_id and redis_manager.is_enabled():
            user_data = await redis_manager.get_json(f"session:{session_id}")
            if user_data:
                context['user'] = user_data
        
        # Add timestamp
        context['processed_at'] = time.time()
        
        return await next_handler(context)
    
    async def _get_device_info(self, device_id: str):
        """Fetch device information from database"""
        try:
            # This would use your actual Device model
            from app.models.device import Device
            return await Model.find(Device, device_id)
        except Exception as e:
            self.logger.warning(f"Could not fetch device info: {e}")
            return None
```

## Middleware with Configuration

### Configurable Rate Limiting Middleware

```python
import time
from collections import defaultdict
from core.middleware import Middleware

class RateLimitMiddleware(Middleware):
    def __init__(self, max_requests: int = 100, window_seconds: int = 60, key_func=None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_func = key_func or self._default_key_func
        self.requests = defaultdict(list)
    
    def _default_key_func(self, context):
        """Default key function uses client ID"""
        client = context.get('client')
        return client._client_id if client else 'anonymous'
    
    async def handle(self, context, next_handler):
        """Apply rate limiting based on configuration"""
        
        # Get rate limit key
        key = self.key_func(context)
        current_time = time.time()
        
        # Clean old requests
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if current_time - req_time < self.window_seconds
        ]
        
        # Check rate limit
        if len(self.requests[key]) >= self.max_requests:
            self.logger.warning(f"Rate limit exceeded for {key}")
            return {
                "error": "rate_limit_exceeded",
                "message": f"Too many requests. Limit: {self.max_requests}/{self.window_seconds}s",
                "retry_after": self.window_seconds
            }
        
        # Record this request
        self.requests[key].append(current_time)
        
        return await next_handler(context)

# Usage with custom key function
def device_key_func(context):
    return context.get('params', {}).get('device_id', 'unknown')

device_rate_limiter = RateLimitMiddleware(
    max_requests=50,
    window_seconds=60,
    key_func=device_key_func
)
```

## Middleware with External Dependencies

### Database Transaction Middleware

```python
from core.middleware import Middleware
from core.model import Model

class TransactionMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Wrap handler execution in database transaction"""
        
        session = await Model.get_session()
        context['db_session'] = session
        
        try:
            # Begin transaction
            result = await next_handler(context)
            
            # Commit transaction on success
            await session.commit()
            self.logger.debug("Transaction committed successfully")
            
            return result
            
        except Exception as e:
            # Rollback transaction on error
            await session.rollback()
            self.logger.error(f"Transaction rolled back due to error: {e}")
            raise
            
        finally:
            await session.close()
```

### Redis Cache Middleware

```python
import json
import hashlib
from core.middleware import Middleware
from core.redis_manager import redis_manager

class CacheMiddleware(Middleware):
    def __init__(self, ttl: int = 300, key_prefix: str = "cache"):
        self.ttl = ttl
        self.key_prefix = key_prefix
    
    async def handle(self, context, next_handler):
        """Cache responses using Redis"""
        
        if not redis_manager.is_enabled():
            return await next_handler(context)
        
        # Generate cache key
        cache_key = self._generate_cache_key(context)
        
        # Try to get from cache
        cached_result = await redis_manager.get_json(cache_key)
        if cached_result is not None:
            self.logger.debug(f"Cache hit for key: {cache_key}")
            return cached_result
        
        # Execute handler
        result = await next_handler(context)
        
        # Cache the result
        if result is not None:
            await redis_manager.set_json(cache_key, result, ex=self.ttl)
            self.logger.debug(f"Cached result for key: {cache_key}")
        
        return result
    
    def _generate_cache_key(self, context):
        """Generate cache key from context"""
        key_data = {
            'topic': context['topic'],
            'params': context.get('params', {}),
            'payload': context.get('payload', {})
        }
        
        key_string = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        
        return f"{self.key_prefix}:{key_hash}"
```

## Registration and Usage

### Single Middleware

```python
from core.router import Router
from app.middleware.logging import RequestLoggerMiddleware

router = Router()

# Apply middleware to specific route
router.on("sensors/{device_id}/data", 
          SensorController.handle_data,
          middleware=[RequestLoggerMiddleware()])
```

### Multiple Middleware (Chain)

```python
# Middleware executes in order: Auth -> RateLimit -> Logging -> Handler
router.on("api/{endpoint}",
          ApiController.handle_request,
          middleware=[
              AuthMiddleware(),
              RateLimitMiddleware(max_requests=100),
              RequestLoggerMiddleware()
          ])
```

### Group Middleware

```python
# Apply middleware to all routes in group
with router.group(prefix="admin", middleware=[AuthMiddleware(), AdminMiddleware()]) as admin:
    admin.on("users/{user_id}", AdminController.manage_user)
    admin.on("settings/{key}", AdminController.update_setting)
```

## Testing Middleware

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock
from app.middleware.logging import RequestLoggerMiddleware

@pytest.mark.asyncio
async def test_logging_middleware():
    middleware = RequestLoggerMiddleware()
    
    # Mock next handler
    next_handler = AsyncMock(return_value="success")
    
    # Test context
    context = {
        'topic': 'test/topic',
        'payload': {'test': 'data'},
        'params': {}
    }
    
    # Execute middleware
    result = await middleware.handle(context, next_handler)
    
    # Assertions
    assert result == "success"
    next_handler.assert_called_once_with(context)

@pytest.mark.asyncio
async def test_middleware_error_handling():
    middleware = RequestLoggerMiddleware()
    
    # Mock next handler that raises exception
    next_handler = AsyncMock(side_effect=ValueError("Test error"))
    
    context = {'topic': 'test/topic', 'payload': {}, 'params': {}}
    
    # Should re-raise the exception
    with pytest.raises(ValueError):
        await middleware.handle(context, next_handler)
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_middleware_chain():
    """Test multiple middleware working together"""
    
    # Create middleware chain
    middleware_chain = [
        RequestIdMiddleware(),
        ValidationMiddleware(SensorDataSchema()),
        RequestLoggerMiddleware()
    ]
    
    # Mock final handler
    final_handler = AsyncMock(return_value={"status": "processed"})
    
    # Create context
    context = {
        'topic': 'sensors/device123/data',
        'payload': {
            'device_id': 'device123',
            'value': 25.6,
            'timestamp': '2023-01-01T00:00:00Z'
        },
        'params': {'device_id': 'device123'}
    }
    
    # Execute chain
    current_handler = final_handler
    for middleware in reversed(middleware_chain):
        async def create_handler(mw, next_h):
            async def handler(ctx):
                return await mw.handle(ctx, next_h)
            return handler
        
        current_handler = await create_handler(middleware, current_handler)
    
    result = await current_handler(context)
    
    # Verify result and context modifications
    assert result["status"] == "processed"
    assert "request_id" in context
    assert "validated_payload" in context
```

## Best Practices

### 1. Keep Middleware Focused

Each middleware should have a single responsibility:

```python
# Good: Single responsibility
class AuthMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Only handle authentication
        pass

# Bad: Multiple responsibilities
class AuthAndLoggingMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Authentication AND logging
        pass
```

### 2. Handle Errors Gracefully

```python
class RobustMiddleware(Middleware):
    async def handle(self, context, next_handler):
        try:
            # Middleware logic
            return await next_handler(context)
        except Exception as e:
            self.logger.error(f"Middleware error: {e}")
            # Decide whether to continue or stop processing
            raise  # Re-raise to stop processing
```

### 3. Make Middleware Configurable

```python
class ConfigurableMiddleware(Middleware):
    def __init__(self, option1: str, option2: int = 10):
        self.option1 = option1
        self.option2 = option2
    
    async def handle(self, context, next_handler):
        # Use configuration options
        pass
```

### 4. Document Context Modifications

```python
class ContextModifyingMiddleware(Middleware):
    """
    Middleware that adds the following to context:
    - user: User object from authentication
    - permissions: List of user permissions
    - device_info: Device information if device_id present
    """
    
    async def handle(self, context, next_handler):
        # Clearly document what's added to context
        pass
```

### 5. Use Type Hints

```python
from typing import Dict, Any, Optional, List

class TypedMiddleware(Middleware):
    def __init__(self, config: Dict[str, Any]):
        self.config: Dict[str, Any] = config
    
    async def handle(self, context: Dict[str, Any], next_handler) -> Optional[Dict[str, Any]]:
        # Clear type annotations help with development
        pass
```

## Common Pitfalls

### 1. Forgetting to Call next_handler

```python
# Wrong: Handler never called
class BrokenMiddleware(Middleware):
    async def handle(self, context, next_handler):
        if some_condition:
            return {"error": "blocked"}
        # Missing: return await next_handler(context)

# Correct: Always call next_handler when processing should continue
class CorrectMiddleware(Middleware):
    async def handle(self, context, next_handler):
        if some_condition:
            return {"error": "blocked"}
        return await next_handler(context)
```

### 2. Modifying Context Incorrectly

```python
# Wrong: Creating new context object
async def handle(self, context, next_handler):
    new_context = {"new": "context"}
    return await next_handler(new_context)

# Correct: Modifying existing context
async def handle(self, context, next_handler):
    context["new_field"] = "value"
    return await next_handler(context)
```

### 3. Not Handling Async Properly

```python
# Wrong: Not awaiting async operations
async def handle(self, context, next_handler):
    redis_manager.set("key", "value")  # Missing await
    return next_handler(context)       # Missing await

# Correct: Properly awaiting async operations
async def handle(self, context, next_handler):
    await redis_manager.set("key", "value")
    return await next_handler(context)
```

## Next Steps

- [Built-in Middleware](built-in-middleware.md) - Explore available middleware components
- [Middleware Chains](middleware-chains.md) - Learn about combining middleware effectively
- [Authentication Middleware](authentication.md) - Implement user authentication
- [Caching Middleware](caching.md) - Add response caching to your routes
