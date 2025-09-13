# Middleware Pipeline

Middleware in RouteMQ provides a powerful way to process messages before they reach your route handlers. The middleware pipeline follows the familiar "onion" pattern where each middleware wraps the next layer.

## Middleware Concept

```
┌─────────────────────────────────────────────────────────────┐
│                    Middleware Pipeline                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │    Auth     │  │ Rate Limit  │  │   Logging   │         │
│  │ Middleware  │  │ Middleware  │  │ Middleware  │         │
│  │     ┌───────┼──┼─────────────┼──┼─────────────┼───────┐ │
│  │     │       │  │             │  │             │       │ │
│  │     │       │  │             │  │             │       │ │
│  │     │   ┌───┼──┼─────────────┼──┼─────────────┼────┐  │ │
│  │     │   │   │  │             │  │             │    │  │ │
│  │     │   │   │  │             │  │             │    │  │ │
│  │     │   │   │  │             │  │             │    │  │ │
│  │     │   │   │  │             │  │ ┌───────────┼────┼──┼─┤
│  │     │   │   │  │             │  │ │           │    │  │ │
│  │     │   │   │  │             │  │ │  Handler  │    │  │ │
│  │     │   │   │  │             │  │ │           │    │  │ │
│  │     │   │   │  │             │  │ └───────────┼────┼──┼─┤
│  │     │   │   │  │             │  │             │    │  │ │
│  │     │   │   │  │             │  │             │    │  │ │
│  │     │   │   └──┼─────────────┼──┼─────────────┼────┘  │ │
│  │     │   │      │             │  │             │       │ │
│  │     │   └──────┼─────────────┼──┼─────────────┼───────┘ │
│  │     │          │             │  │             │         │
│  └─────┼──────────┼─────────────┼──┼─────────────┼─────────┘
│        │          │             │  │             │
│     Request    Request       Request          Request
│     ────────▶  ────────▶     ────────▶        ────────▶
│        │          │             │  │             │
│     Response   Response      Response         Response
│     ◀────────  ◀────────     ◀────────        ◀────────
└─────────────────────────────────────────────────────────────┘
```

## Creating Middleware

### Basic Middleware Structure

All middleware must extend the `Middleware` base class:

```python
from core.middleware import Middleware
from typing import Dict, Any, Callable, Awaitable

class LoggingMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable[[Dict[str, Any]], Awaitable[Any]]) -> Any:
        # Pre-processing: runs before the handler
        self.logger.info(f"Processing message on topic: {context['topic']}")
        
        try:
            # Call the next middleware or handler
            result = await next_handler(context)
            
            # Post-processing: runs after the handler
            self.logger.info(f"Successfully processed message")
            return result
            
        except Exception as e:
            # Error handling
            self.logger.error(f"Error processing message: {e}")
            raise
```

### Middleware with Configuration

```python
class RateLimitMiddleware(Middleware):
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # In production, use Redis
    
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        # Extract client identifier
        client_id = context.get('client_id', 'anonymous')
        current_time = time.time()
        
        # Check rate limit
        if self._is_rate_limited(client_id, current_time):
            self.logger.warning(f"Rate limit exceeded for client: {client_id}")
            return  # Stop processing - don't call next_handler
        
        # Record request
        self._record_request(client_id, current_time)
        
        # Continue to next middleware
        return await next_handler(context)
```

## Middleware Registration

### Route-Level Middleware

Apply middleware to specific routes:

```python
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

router = Router()

# Single middleware
router.on("api/secure/{endpoint}", 
          ApiController.handle, 
          middleware=[AuthMiddleware()])

# Multiple middleware (executed in order)
router.on("api/limited/{endpoint}", 
          ApiController.handle,
          middleware=[AuthMiddleware(), RateLimitMiddleware(max_requests=50)])
```

### Group-Level Middleware

Apply middleware to route groups:

```python
# All routes in group get the middleware
with router.group(prefix="admin", middleware=[AuthMiddleware(), AdminMiddleware()]) as admin:
    admin.on("users/{user_id}", AdminController.manage_user)
    admin.on("settings/{key}", AdminController.update_setting)
```

### Combined Middleware

Group middleware combines with route-specific middleware:

```python
with router.group(prefix="api", middleware=[AuthMiddleware()]) as api:
    # This route gets: AuthMiddleware + RateLimitMiddleware
    api.on("data/{id}", 
           DataController.get_data, 
           middleware=[RateLimitMiddleware()])
```

## Built-in Middleware Examples

### Authentication Middleware

```python
class AuthMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        # Extract token from payload or headers
        token = self._extract_token(context)
        
        if not token:
            self.logger.warning("No authentication token provided")
            return {"error": "Authentication required"}
        
        # Validate token
        user = await self._validate_token(token)
        if not user:
            self.logger.warning(f"Invalid token: {token}")
            return {"error": "Invalid authentication"}
        
        # Add user to context for downstream handlers
        context['user'] = user
        context['authenticated'] = True
        
        return await next_handler(context)
    
    def _extract_token(self, context: Dict[str, Any]) -> str:
        payload = context.get('payload', {})
        return payload.get('token') or payload.get('auth_token')
    
    async def _validate_token(self, token: str) -> dict:
        # Validate against database or JWT
        # Return user object if valid, None if invalid
        pass
```

### Request ID Middleware

```python
import uuid

class RequestIdMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        context['request_id'] = request_id
        
        # Add to logger context
        logger = logging.getLogger("RouteMQ").getChild(f"req-{request_id[:8]}")
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

### Validation Middleware

```python
from marshmallow import Schema, ValidationError

class ValidationMiddleware(Middleware):
    def __init__(self, schema: Schema):
        self.schema = schema
    
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        try:
            # Validate payload against schema
            validated_data = self.schema.load(context['payload'])
            context['validated_payload'] = validated_data
            
        except ValidationError as e:
            self.logger.warning(f"Validation failed: {e.messages}")
            return {"error": "Invalid payload", "details": e.messages}
        
        return await next_handler(context)

# Usage
from marshmallow import Schema, fields

class SensorDataSchema(Schema):
    device_id = fields.Str(required=True)
    temperature = fields.Float(required=True)
    timestamp = fields.DateTime(required=True)

router.on("sensors/data", 
          SensorController.handle_data,
          middleware=[ValidationMiddleware(SensorDataSchema())])
```

## Middleware Execution Order

### Chain Processing

Middleware executes in the order specified:

```python
middleware=[Auth(), RateLimit(), Logging(), Validation()]

# Execution order:
# 1. Auth.handle() - pre-processing
# 2. RateLimit.handle() - pre-processing  
# 3. Logging.handle() - pre-processing
# 4. Validation.handle() - pre-processing
# 5. Route handler executes
# 6. Validation.handle() - post-processing
# 7. Logging.handle() - post-processing
# 8. RateLimit.handle() - post-processing
# 9. Auth.handle() - post-processing
```

### Early Termination

Middleware can stop processing by not calling `next_handler`:

```python
class SecurityMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        if self._is_blocked_ip(context.get('client_ip')):
            self.logger.warning("Blocked IP attempted access")
            return {"error": "Access denied"}  # Stops here
        
        # Only continues if IP is allowed
        return await next_handler(context)
```

## Context Manipulation

### Adding Data to Context

Middleware can add data for downstream processing:

```python
class DeviceInfoMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        device_id = context['params'].get('device_id')
        
        if device_id:
            # Fetch device info from database
            device = await self.db.get_device(device_id)
            context['device'] = device
            context['device_config'] = device.config
        
        return await next_handler(context)
```

### Modifying Payload

```python
class PayloadTransformMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        payload = context['payload']
        
        # Transform payload format
        if isinstance(payload, str):
            try:
                context['payload'] = json.loads(payload)
            except json.JSONDecodeError:
                context['payload'] = {"raw_data": payload}
        
        # Add metadata
        context['payload']['processed_at'] = datetime.utcnow().isoformat()
        context['payload']['middleware_version'] = "1.0"
        
        return await next_handler(context)
```

## Error Handling in Middleware

### Graceful Error Handling

```python
class ErrorHandlingMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        try:
            return await next_handler(context)
        
        except ValidationError as e:
            # Handle validation errors
            self.logger.warning(f"Validation error: {e}")
            return {"error": "validation_failed", "details": str(e)}
        
        except DatabaseError as e:
            # Handle database errors
            self.logger.error(f"Database error: {e}")
            return {"error": "database_error", "retry": True}
        
        except Exception as e:
            # Handle unexpected errors
            self.logger.error(f"Unexpected error: {e}")
            return {"error": "internal_error"}
```

### Error Recovery

```python
class RetryMiddleware(Middleware):
    def __init__(self, max_retries: int = 3, delay: float = 1.0):
        self.max_retries = max_retries
        self.delay = delay
    
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                return await next_handler(context)
            
            except RetryableError as e:
                if attempt == self.max_retries:
                    self.logger.error(f"Max retries exceeded: {e}")
                    raise
                
                self.logger.warning(f"Attempt {attempt + 1} failed, retrying: {e}")
                await asyncio.sleep(self.delay * (2 ** attempt))  # Exponential backoff
```

## Dependency Injection in Middleware

### Access to Shared Resources

```python
class DatabaseMiddleware(Middleware):
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        # Make database available to handlers
        context['db'] = self.db
        
        # Start database transaction
        async with self.db.transaction() as tx:
            context['transaction'] = tx
            
            try:
                result = await next_handler(context)
                await tx.commit()
                return result
            except Exception as e:
                await tx.rollback()
                raise

# Registration with dependency injection
db_connection = get_database_connection()
router.on("data/save", 
          DataController.save,
          middleware=[DatabaseMiddleware(db_connection)])
```

## Performance Considerations

### Async Operations

Always use async for I/O operations:

```python
class CachingMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        cache_key = self._generate_cache_key(context)
        
        # Non-blocking cache lookup
        cached_result = await self.redis.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
        
        # Continue to handler
        result = await next_handler(context)
        
        # Non-blocking cache store
        await self.redis.setex(cache_key, 300, json.dumps(result))
        
        return result
```

### Memory Efficiency

Avoid storing large objects in context:

```python
class EfficientMiddleware(Middleware):
    async def handle(self, context: Dict[str, Any], next_handler: Callable) -> Any:
        # Store references, not full objects
        context['user_id'] = user.id  # Not the full user object
        context['device_ref'] = f"device:{device_id}"  # Not the full device
        
        return await next_handler(context)
```

## Testing Middleware

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_auth_middleware():
    middleware = AuthMiddleware()
    
    # Mock next handler
    next_handler = AsyncMock(return_value="success")
    
    # Test valid auth
    context = {
        'payload': {'token': 'valid_token'},
        'topic': 'test/topic'
    }
    
    result = await middleware.handle(context, next_handler)
    
    assert result == "success"
    assert 'user' in context
    next_handler.assert_called_once_with(context)
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_middleware_chain():
    router = Router()
    router.on("test/{id}", test_handler, middleware=[
        AuthMiddleware(),
        ValidationMiddleware(TestSchema()),
        LoggingMiddleware()
    ])
    
    # Test complete chain
    await router.dispatch("test/123", {"token": "valid", "data": "test"}, mock_client)
```

## Best Practices

### Middleware Design

1. **Single Responsibility**: Each middleware should handle one concern
2. **Fail Fast**: Validate early and return clear error messages
3. **Context Hygiene**: Only add necessary data to context
4. **Async First**: Use async/await for all I/O operations
5. **Error Handling**: Handle errors gracefully and provide useful messages

### Performance Guidelines

1. **Minimize Processing**: Keep middleware logic lightweight
2. **Cache Results**: Cache expensive operations when possible
3. **Connection Pooling**: Reuse database and Redis connections
4. **Lazy Loading**: Only load data when needed

### Security Considerations

1. **Input Validation**: Validate all input data
2. **Authentication**: Verify user identity before processing
3. **Authorization**: Check permissions for specific operations
4. **Rate Limiting**: Prevent abuse and DoS attacks
5. **Logging**: Log security-relevant events

## Next Steps

- [Worker Processes](worker-processes.md) - Scale your application with shared subscriptions
- [Controllers](../controllers/README.md) - Implement business logic in handlers
- [Middleware Examples](../middleware/README.md) - See more middleware implementations
