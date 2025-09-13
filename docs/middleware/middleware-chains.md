# Middleware Chains

Learn how to combine multiple middleware components to create powerful processing pipelines for your RouteMQ applications.

## Understanding Middleware Chains

Middleware in RouteMQ executes in a chain pattern where each middleware can:
- Process the request before passing it to the next middleware
- Modify the context that flows through the chain
- Process the response after receiving it from subsequent middleware
- Stop the chain by not calling the next handler

### Chain Execution Flow

```
Request → Middleware 1 → Middleware 2 → Middleware 3 → Handler
           ↓              ↓              ↓           ↓
        Pre-process    Pre-process    Pre-process  Execute
           ↑              ↑              ↑           ↑
       Post-process   Post-process   Post-process  Return
Response ← Middleware 1 ← Middleware 2 ← Middleware 3 ← Handler
```

## Basic Chain Example

```python
from core.router import Router
from app.middleware.logging import LoggingMiddleware
from app.middleware.auth import AuthenticationMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

router = Router()

# Middleware executes in order: Logging → Auth → RateLimit → Handler
router.on("api/{endpoint}",
          ApiController.handle_request,
          middleware=[
              LoggingMiddleware(),           # 1st: Log the request
              AuthenticationMiddleware(),    # 2nd: Authenticate user
              RateLimitMiddleware(),        # 3rd: Check rate limits
          ])
```

### Execution Order:

1. **LoggingMiddleware** logs incoming request
2. **AuthenticationMiddleware** validates credentials  
3. **RateLimitMiddleware** checks request limits
4. **Handler** executes business logic
5. **RateLimitMiddleware** can log rate limit status
6. **AuthenticationMiddleware** can log auth success
7. **LoggingMiddleware** logs final response and timing

## Chain Design Patterns

### 1. Security-First Chain

Place security middleware at the beginning to fail fast:

```python
security_chain = [
    SecurityMiddleware(),              # 1st: Block threats immediately
    RateLimitMiddleware(),            # 2nd: Prevent abuse
    AuthenticationMiddleware(),        # 3rd: Verify identity
    AuthorizationMiddleware(),        # 4th: Check permissions
    ValidationMiddleware(schema),     # 5th: Validate input
    BusinessLogicHandler()            # Final: Process request
]

router.on("secure/api/{endpoint}",
          SecureController.handle,
          middleware=security_chain)
```

### 2. Performance-Optimized Chain

Order middleware by execution cost (fastest first):

```python
performance_chain = [
    CacheMiddleware(),                # 1st: Check cache (fast)
    RateLimitMiddleware(),           # 2nd: Simple counter check
    AuthenticationMiddleware(),       # 3rd: Token validation
    ValidationMiddleware(),          # 4th: Schema validation
    DatabaseMiddleware(),            # 5th: Database operations
    LoggingMiddleware()              # Last: I/O operations
]
```

### 3. IoT Device Chain

Specialized chain for IoT devices:

```python
iot_chain = [
    DeviceAuthMiddleware(),          # Device certificate auth
    TelemetryValidationMiddleware(), # Validate sensor data
    DataTransformMiddleware(),       # Convert units, formats
    MetricsMiddleware(),            # Collect telemetry metrics
    PersistenceMiddleware()         # Store to time-series DB
]

router.on("iot/devices/{device_id}/telemetry",
          IoTController.handle_telemetry,
          middleware=iot_chain)
```

## Context Flow Through Chains

### Context Modification Example

```python
class RequestIdMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Add request ID to context
        context['request_id'] = str(uuid.uuid4())
        context['start_time'] = time.time()
        
        result = await next_handler(context)
        
        # Add timing information to result
        if isinstance(result, dict):
            result['processing_time'] = time.time() - context['start_time']
            result['request_id'] = context['request_id']
        
        return result

class UserContextMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Use request_id from previous middleware
        request_id = context.get('request_id', 'unknown')
        
        # Add user context
        user_id = context.get('payload', {}).get('user_id')
        if user_id:
            user = await self.get_user(user_id)
            context['user'] = user
            context['user_permissions'] = user.permissions
        
        return await next_handler(context)

# Chain shows context flowing through middleware
context_chain = [
    RequestIdMiddleware(),    # Adds: request_id, start_time
    UserContextMiddleware(),  # Adds: user, user_permissions (uses request_id)
    BusinessMiddleware()      # Uses: all previous context data
]
```

### Context Dependencies

```python
class DatabaseSessionMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Provide database session to downstream middleware
        session = await Model.get_session()
        context['db_session'] = session
        
        try:
            result = await next_handler(context)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

class AuditMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Depends on user context and database session
        user = context.get('user')
        db_session = context.get('db_session')
        
        if user and db_session:
            # Create audit log entry
            audit_entry = AuditLog(
                user_id=user.id,
                action=context['topic'],
                timestamp=time.time()
            )
            db_session.add(audit_entry)
        
        return await next_handler(context)

# Order matters: Database session must come before audit
audit_chain = [
    AuthenticationMiddleware(),  # Provides: user
    DatabaseSessionMiddleware(), # Provides: db_session
    AuditMiddleware(),          # Requires: user, db_session
]
```

## Conditional Chain Execution

### Skip Middleware Based on Conditions

```python
class ConditionalAuthMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Skip auth for public endpoints
        if context['topic'].startswith('public/'):
            context['authenticated'] = False
            return await next_handler(context)
        
        # Apply authentication for other endpoints
        return await self.authenticate_request(context, next_handler)

class SmartCacheMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Only cache GET-like operations (queries)
        payload = context.get('payload', {})
        
        if payload.get('action') == 'query':
            return await self.handle_with_cache(context, next_handler)
        else:
            # Skip caching for mutations
            return await next_handler(context)
```

### Dynamic Chain Modification

```python
class AdaptiveMiddleware(Middleware):
    def __init__(self):
        self.performance_mode = False
        self.request_count = 0
    
    async def handle(self, context, next_handler):
        self.request_count += 1
        
        # Enable performance mode under high load
        if self.request_count % 100 == 0:
            current_load = await self.get_system_load()
            self.performance_mode = current_load > 0.8
        
        if self.performance_mode:
            # Skip expensive operations under high load
            context['skip_analytics'] = True
            context['cache_aggressively'] = True
        
        return await next_handler(context)
```

## Error Handling in Chains

### Early Termination

```python
class ValidationMiddleware(Middleware):
    async def handle(self, context, next_handler):
        if not self.is_valid_payload(context['payload']):
            # Stop chain execution here
            return {
                "error": "validation_failed",
                "message": "Invalid payload format"
            }
        
        # Continue chain only if validation passes
        return await next_handler(context)

class AuthorizationMiddleware(Middleware):
    async def handle(self, context, next_handler):
        user = context.get('user')
        
        if not user or not self.has_permission(user, context['topic']):
            # Stop chain - don't call next_handler
            return {
                "error": "access_denied",
                "message": "Insufficient permissions"
            }
        
        return await next_handler(context)
```

### Error Recovery

```python
class ErrorRecoveryMiddleware(Middleware):
    async def handle(self, context, next_handler):
        try:
            return await next_handler(context)
        
        except DatabaseConnectionError:
            # Try with read-only database
            context['read_only_mode'] = True
            return await self.handle_read_only(context)
        
        except RateLimitExceeded:
            # Queue request for later processing
            await self.queue_for_later(context)
            return {"status": "queued", "message": "Request queued due to rate limit"}
        
        except Exception as e:
            # Log error and return generic response
            self.logger.error(f"Unhandled error: {e}")
            return {"error": "internal_error", "message": "Please try again later"}

class CircuitBreakerMiddleware(Middleware):
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.circuit_open_time = None
    
    async def handle(self, context, next_handler):
        # Check if circuit is open
        if self.circuit_open_time:
            if time.time() - self.circuit_open_time < self.recovery_timeout:
                return {"error": "service_unavailable", "message": "Circuit breaker open"}
            else:
                # Try to close circuit
                self.circuit_open_time = None
                self.failure_count = 0
        
        try:
            result = await next_handler(context)
            self.failure_count = 0  # Reset on success
            return result
        
        except Exception as e:
            self.failure_count += 1
            
            if self.failure_count >= self.failure_threshold:
                self.circuit_open_time = time.time()
                self.logger.error("Circuit breaker opened due to repeated failures")
            
            raise
```

## Chain Composition Patterns

### Reusable Chain Components

```python
# Define reusable middleware stacks
class MiddlewareStacks:
    
    @staticmethod
    def security_stack():
        """Standard security middleware stack"""
        return [
            SecurityMiddleware(),
            RateLimitMiddleware(max_requests=1000),
            AuthenticationMiddleware(),
            AuthorizationMiddleware()
        ]
    
    @staticmethod
    def performance_stack():
        """Performance optimization stack"""
        return [
            CacheMiddleware(ttl=300),
            CompressionMiddleware(),
            MetricsMiddleware()
        ]
    
    @staticmethod
    def data_stack():
        """Data processing stack"""
        return [
            ValidationMiddleware(),
            TransformationMiddleware(),
            PersistenceMiddleware()
        ]

# Compose stacks for different route types
api_middleware = (
    MiddlewareStacks.security_stack() +
    MiddlewareStacks.performance_stack() +
    [LoggingMiddleware()]
)

data_middleware = (
    [AuthenticationMiddleware()] +
    MiddlewareStacks.data_stack() +
    [MetricsMiddleware()]
)
```

### Conditional Stack Assembly

```python
def build_middleware_stack(route_type: str, environment: str) -> List[Middleware]:
    """Build middleware stack based on route type and environment"""
    
    stack = []
    
    # Always include security for non-public routes
    if route_type != 'public':
        stack.extend([
            SecurityMiddleware(),
            AuthenticationMiddleware()
        ])
    
    # Add rate limiting (different limits for different environments)
    if environment == 'production':
        stack.append(RateLimitMiddleware(max_requests=1000, window_seconds=3600))
    else:
        stack.append(RateLimitMiddleware(max_requests=100, window_seconds=60))
    
    # Add caching for read operations
    if route_type in ['api', 'public']:
        stack.append(CacheMiddleware(ttl=300))
    
    # Add validation for data routes
    if route_type == 'data':
        stack.append(ValidationMiddleware(DataSchema()))
    
    # Always include logging and metrics
    stack.extend([
        MetricsMiddleware(),
        LoggingMiddleware()
    ])
    
    return stack

# Use dynamic stack building
environment = os.getenv('ENVIRONMENT', 'development')

router.on("api/{endpoint}",
          ApiController.handle,
          middleware=build_middleware_stack('api', environment))

router.on("data/{type}/{id}",
          DataController.handle,
          middleware=build_middleware_stack('data', environment))
```

## Advanced Chain Patterns

### Parallel Middleware Execution

```python
import asyncio

class ParallelMiddleware(Middleware):
    def __init__(self, middleware_list: List[Middleware]):
        self.middleware_list = middleware_list
    
    async def handle(self, context, next_handler):
        """Execute multiple middleware in parallel (where safe)"""
        
        # Create tasks for independent middleware
        tasks = []
        for middleware in self.middleware_list:
            if self.is_safe_for_parallel(middleware):
                task = asyncio.create_task(
                    middleware.handle(context.copy(), self.noop_handler)
                )
                tasks.append(task)
        
        # Wait for all parallel middleware to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Continue with main chain
        return await next_handler(context)
    
    async def noop_handler(self, context):
        """No-op handler for parallel middleware"""
        return None
    
    def is_safe_for_parallel(self, middleware):
        """Check if middleware can run in parallel"""
        # Only metrics and logging middleware are safe for parallel execution
        return isinstance(middleware, (MetricsMiddleware, LoggingMiddleware))

# Usage
parallel_stack = [
    AuthenticationMiddleware(),
    ParallelMiddleware([
        MetricsMiddleware(),
        LoggingMiddleware(),
        AnalyticsMiddleware()
    ]),
    ValidationMiddleware()
]
```

### Middleware with State Sharing

```python
class SharedStateMiddleware(Middleware):
    """Middleware that shares state across the chain"""
    
    def __init__(self):
        self.shared_state = {}
    
    async def handle(self, context, next_handler):
        # Add shared state to context
        context['shared_state'] = self.shared_state
        
        result = await next_handler(context)
        
        # Extract any updates to shared state
        if 'shared_state_updates' in context:
            self.shared_state.update(context['shared_state_updates'])
        
        return result

class StatefulMiddleware(Middleware):
    """Middleware that uses shared state"""
    
    async def handle(self, context, next_handler):
        shared_state = context.get('shared_state', {})
        
        # Use shared state
        request_count = shared_state.get('request_count', 0) + 1
        
        # Update shared state
        context['shared_state_updates'] = {
            'request_count': request_count,
            'last_request_time': time.time()
        }
        
        return await next_handler(context)

# Chain with shared state
stateful_chain = [
    SharedStateMiddleware(),  # Provides shared state
    StatefulMiddleware(),     # Uses and updates shared state
    BusinessMiddleware()      # Can also use shared state
]
```

## Testing Middleware Chains

### Unit Testing Chains

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_middleware_chain_execution():
    """Test that middleware executes in correct order"""
    
    execution_order = []
    
    class OrderTrackingMiddleware(Middleware):
        def __init__(self, name):
            self.name = name
        
        async def handle(self, context, next_handler):
            execution_order.append(f"{self.name}_start")
            result = await next_handler(context)
            execution_order.append(f"{self.name}_end")
            return result
    
    # Create middleware chain
    middleware_chain = [
        OrderTrackingMiddleware("first"),
        OrderTrackingMiddleware("second"),
        OrderTrackingMiddleware("third")
    ]
    
    # Mock final handler
    final_handler = AsyncMock(return_value="success")
    
    # Build chain
    current_handler = final_handler
    for middleware in reversed(middleware_chain):
        async def create_handler(mw, next_h):
            async def handler(ctx):
                return await mw.handle(ctx, next_h)
            return handler
        
        current_handler = await create_handler(middleware, current_handler)
    
    # Execute chain
    context = {'topic': 'test', 'payload': {}}
    result = await current_handler(context)
    
    # Verify execution order
    expected_order = [
        "first_start", "second_start", "third_start",
        "third_end", "second_end", "first_end"
    ]
    
    assert execution_order == expected_order
    assert result == "success"

@pytest.mark.asyncio
async def test_middleware_early_termination():
    """Test middleware chain stops when middleware doesn't call next"""
    
    class BlockingMiddleware(Middleware):
        async def handle(self, context, next_handler):
            if context.get('block', False):
                return {"blocked": True}
            return await next_handler(context)
    
    class TrackingMiddleware(Middleware):
        def __init__(self):
            self.called = False
        
        async def handle(self, context, next_handler):
            self.called = True
            return await next_handler(context)
    
    tracking = TrackingMiddleware()
    final_handler = AsyncMock()
    
    # Build chain: blocking -> tracking -> final
    chain = [BlockingMiddleware(), tracking]
    
    # Test blocked execution
    context = {'block': True}
    # ... (build and execute chain)
    
    # Verify tracking middleware and final handler weren't called
    assert not tracking.called
    assert not final_handler.called
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_complete_middleware_stack():
    """Test complete middleware stack integration"""
    
    # Setup test middleware stack
    test_stack = [
        AuthenticationMiddleware(),
        ValidationMiddleware(TestSchema()),
        LoggingMiddleware()
    ]
    
    # Mock dependencies
    redis_manager.enable()  # Enable Redis for testing
    
    # Create test route with middleware
    router = Router()
    router.on("test/{id}", test_handler, middleware=test_stack)
    
    # Test valid request
    valid_context = {
        'topic': 'test/123',
        'payload': {'token': 'valid_token', 'data': 'test'},
        'params': {'id': '123'}
    }
    
    result = await router.dispatch(**valid_context)
    
    # Verify successful processing
    assert result['status'] == 'success'
    assert 'request_id' in result
    
    # Test invalid request (should be blocked by middleware)
    invalid_context = {
        'topic': 'test/123',
        'payload': {'invalid': 'data'},  # Missing token
        'params': {'id': '123'}
    }
    
    result = await router.dispatch(**invalid_context)
    
    # Verify request was blocked
    assert 'error' in result
```

## Performance Optimization

### Middleware Ordering for Performance

```python
# Optimal ordering (fastest to slowest):
optimized_chain = [
    CacheMiddleware(),           # Fast: Memory/Redis lookup
    RateLimitMiddleware(),       # Fast: Simple counter check
    SecurityMiddleware(),        # Medium: Pattern matching
    AuthenticationMiddleware(),   # Slow: Database/token validation
    ValidationMiddleware(),      # Slow: Schema validation
    LoggingMiddleware()          # Slowest: File I/O
]
```

### Lazy Loading in Middleware

```python
class LazyLoadingMiddleware(Middleware):
    def __init__(self):
        self._expensive_resource = None
    
    async def get_expensive_resource(self):
        """Lazy load expensive resource only when needed"""
        if self._expensive_resource is None:
            self._expensive_resource = await self.initialize_resource()
        return self._expensive_resource
    
    async def handle(self, context, next_handler):
        # Only load resource if actually needed
        if self.needs_resource(context):
            resource = await self.get_expensive_resource()
            context['resource'] = resource
        
        return await next_handler(context)
```

### Middleware Caching

```python
class CachingWrapperMiddleware(Middleware):
    """Wrapper that adds caching to any middleware"""
    
    def __init__(self, wrapped_middleware: Middleware, cache_ttl: int = 60):
        self.wrapped_middleware = wrapped_middleware
        self.cache_ttl = cache_ttl
        self.cache = {}
    
    async def handle(self, context, next_handler):
        # Generate cache key for middleware result
        cache_key = self._generate_cache_key(context)
        
        # Check cache first
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                # Apply cached modifications to context
                context.update(cached_data)
                return await next_handler(context)
        
        # Execute wrapped middleware
        original_context = context.copy()
        result = await self.wrapped_middleware.handle(context, next_handler)
        
        # Cache the context modifications
        context_changes = {
            k: v for k, v in context.items() 
            if k not in original_context or original_context[k] != v
        }
        
        self.cache[cache_key] = (context_changes, time.time())
        
        return result
```

## Best Practices

### 1. Design for Composability

```python
# Good: Focused, reusable middleware
class AuthMiddleware(Middleware): pass
class LoggingMiddleware(Middleware): pass
class MetricsMiddleware(Middleware): pass

# Bad: Monolithic middleware
class AuthLoggingMetricsMiddleware(Middleware): pass
```

### 2. Handle Dependencies Explicitly

```python
# Good: Clear dependency chain
security_chain = [
    AuthenticationMiddleware(),  # Provides: user
    AuthorizationMiddleware(),   # Requires: user
]

# Bad: Hidden dependencies
mixed_chain = [
    AuthorizationMiddleware(),   # Fails: no user context
    AuthenticationMiddleware(),  # Provides: user (too late)
]
```

### 3. Document Chain Requirements

```python
class ApiMiddlewareStack:
    """
    Standard API middleware stack.
    
    Chain order:
    1. SecurityMiddleware - Blocks threats
    2. RateLimitMiddleware - Prevents abuse  
    3. AuthenticationMiddleware - Validates identity
    4. ValidationMiddleware - Validates payload
    5. LoggingMiddleware - Logs request/response
    
    Context additions:
    - request_id: Unique request identifier
    - user: Authenticated user object
    - validated_payload: Schema-validated payload
    """
    
    @staticmethod
    def create(schema: Schema = None):
        return [
            SecurityMiddleware(),
            RateLimitMiddleware(),
            AuthenticationMiddleware(),
            ValidationMiddleware(schema) if schema else None,
            LoggingMiddleware()
        ]
```

### 4. Implement Graceful Degradation

```python
class ResilientMiddleware(Middleware):
    async def handle(self, context, next_handler):
        try:
            # Try normal operation
            return await self.normal_operation(context, next_handler)
        except ServiceUnavailableError:
            # Degrade gracefully
            return await self.degraded_operation(context, next_handler)
        except Exception:
            # Log error but continue chain
            self.logger.error("Middleware failed, continuing...")
            return await next_handler(context)
```

## Next Steps

- [Authentication Middleware](authentication.md) - Deep dive into authentication patterns
- [Caching Middleware](caching.md) - Advanced caching strategies
- [Creating Middleware](creating-middleware.md) - Build custom middleware components
- [Built-in Middleware](built-in-middleware.md) - Explore available middleware
