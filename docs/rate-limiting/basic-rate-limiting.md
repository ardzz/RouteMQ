# Basic Rate Limiting

Get started with RouteMQ's rate limiting middleware to control message processing rates and protect your application from abuse.

## Quick Setup

The simplest way to add rate limiting to your routes:

```python
from app.middleware.rate_limit import RateLimitMiddleware

# Basic rate limiting - 100 requests per minute
rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60
)

# Apply to a route
router.on("api/{endpoint}", 
          ApiController.handle,
          middleware=[rate_limiter])
```

## Configuration Options

### Basic Parameters

```python
rate_limiter = RateLimitMiddleware(
    max_requests=50,        # Maximum requests allowed
    window_seconds=60,      # Time window in seconds
    strategy="sliding_window"  # Rate limiting algorithm
)
```

### Common Configurations

#### API Endpoints
```python
# Standard API rate limiting
api_rate_limit = RateLimitMiddleware(
    max_requests=1000,      # 1000 requests
    window_seconds=3600     # per hour
)

router.on("api/{endpoint}", 
          ApiController.handle,
          middleware=[api_rate_limit])
```

#### IoT Device Data
```python
# Device telemetry rate limiting
device_rate_limit = RateLimitMiddleware(
    max_requests=100,       # 100 messages
    window_seconds=60       # per minute
)

router.on("devices/{device_id}/telemetry", 
          DeviceController.handle_telemetry,
          middleware=[device_rate_limit])
```

#### Public Endpoints
```python
# More restrictive for public access
public_rate_limit = RateLimitMiddleware(
    max_requests=50,        # 50 requests
    window_seconds=60       # per minute
)

router.on("public/{endpoint}", 
          PublicController.handle,
          middleware=[public_rate_limit])
```

## Understanding Rate Limiting

### How It Works

1. **Request Arrives**: A message is received on a topic
2. **Key Generation**: A unique key is generated (default: based on topic)
3. **Count Check**: Current request count is checked against the limit
4. **Decision**: Request is either allowed or blocked
5. **Counter Update**: Request count is incremented if allowed

### Rate Limit Response

When rate limit is exceeded, the middleware returns:

```json
{
    "error": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Try again in 45 seconds.",
    "rate_limit": {
        "max_requests": 100,
        "window_seconds": 60,
        "remaining": 0,
        "reset_time": 45
    }
}
```

### Context Information

Rate limiting information is added to the context:

```python
async def handle_request(self, context):
    rate_limit_info = context.get('rate_limit', {})
    
    if rate_limit_info.get('exceeded'):
        # Handle rate limit exceeded case
        pass
    else:
        remaining = rate_limit_info.get('remaining', 0)
        print(f"Remaining requests: {remaining}")
```

## Storage Backends

### Redis Backend (Recommended)

For distributed applications, use Redis for rate limiting:

```python
# Ensure Redis is enabled in your application
from core.redis_manager import redis_manager

# Rate limiter automatically uses Redis if available
rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    redis_key_prefix="api_rate_limit"  # Custom prefix
)
```

**Benefits of Redis backend:**
- Shared across multiple application instances
- Persistent across application restarts
- High performance with atomic operations
- Supports advanced algorithms

### Memory Backend (Fallback)

When Redis is unavailable, in-memory fallback is used:

```python
# Enable fallback to memory storage
rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    fallback_enabled=True  # Default: True
)
```

**Memory backend characteristics:**
- Per-instance rate limiting only
- Lost on application restart
- No coordination between instances
- Suitable for single-instance deployments

## Error Handling

### Custom Error Messages

```python
rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    custom_error_message="Too many requests! Please slow down and try again later."
)
```

### Graceful Degradation

```python
# Disable fallback - allow requests if Redis fails
strict_rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    fallback_enabled=False  # Allow requests if Redis unavailable
)

# Enable fallback - use memory if Redis fails
resilient_rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    fallback_enabled=True   # Use in-memory fallback
)
```

## Monitoring Rate Limits

### Logging

Rate limiting events are automatically logged:

```
INFO - Rate limit middleware initialized: 100 req/60s, strategy: sliding_window
DEBUG - Rate limit check passed for key: topic:api/users, remaining: 95
WARNING - Rate limit exceeded for key: topic:api/users
```

### Context Information

Access rate limit status in your handlers:

```python
class ApiController(Controller):
    async def handle_request(self, context):
        rate_limit = context.get('rate_limit', {})
        
        # Log rate limit status
        self.logger.info(f"Rate limit remaining: {rate_limit.get('remaining', 0)}")
        
        # Add rate limit headers to response
        response = {"data": "success"}
        
        if not rate_limit.get('exceeded'):
            response['rate_limit'] = {
                'remaining': rate_limit.get('remaining'),
                'reset_time': rate_limit.get('reset_time')
            }
        
        return response
```

## Testing Rate Limits

### Unit Testing

```python
import pytest
from app.middleware.rate_limit import RateLimitMiddleware
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_rate_limit_allows_requests_within_limit():
    """Test that requests within limit are allowed"""
    
    rate_limiter = RateLimitMiddleware(
        max_requests=5,
        window_seconds=60,
        fallback_enabled=True  # Use memory for testing
    )
    
    context = {'topic': 'test/endpoint'}
    handler = AsyncMock(return_value="success")
    
    # First 5 requests should be allowed
    for i in range(5):
        result = await rate_limiter.handle(context.copy(), handler)
        assert result == "success"
        assert handler.call_count == i + 1

@pytest.mark.asyncio
async def test_rate_limit_blocks_excess_requests():
    """Test that requests exceeding limit are blocked"""
    
    rate_limiter = RateLimitMiddleware(
        max_requests=2,
        window_seconds=60,
        fallback_enabled=True
    )
    
    context = {'topic': 'test/endpoint'}
    handler = AsyncMock(return_value="success")
    
    # First 2 requests allowed
    for i in range(2):
        result = await rate_limiter.handle(context.copy(), handler)
        assert result == "success"
    
    # 3rd request should be blocked
    result = await rate_limiter.handle(context.copy(), handler)
    assert isinstance(result, dict)
    assert result['error'] == 'rate_limit_exceeded'
    assert handler.call_count == 2  # Handler not called for blocked request
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_rate_limit_with_router():
    """Test rate limiting integrated with router"""
    
    from core.router import Router
    
    # Create rate limited route
    rate_limiter = RateLimitMiddleware(max_requests=3, window_seconds=60)
    
    router = Router()
    router.on("test/{id}", 
              lambda ctx: {"result": "success"},
              middleware=[rate_limiter])
    
    # Test within limit
    for i in range(3):
        result = await router.dispatch("test/123", {}, None)
        assert result["result"] == "success"
    
    # Test rate limit exceeded
    result = await router.dispatch("test/123", {}, None)
    assert result["error"] == "rate_limit_exceeded"
```

## Performance Considerations

### Key Generation Efficiency

The default key generator uses the topic, which means rate limiting is applied per topic:

```python
# Default behavior - rate limit per topic
context = {'topic': 'api/users'}
# Key: "topic:api/users"

context = {'topic': 'api/orders'} 
# Key: "topic:api/orders"  # Different limit counter
```

### Redis Connection Pooling

Rate limiting middleware uses the shared Redis connection pool from `redis_manager`, ensuring efficient connection reuse.

### Memory Usage

In-memory fallback automatically cleans up expired entries to prevent memory leaks:

```python
# Automatic cleanup runs every 60 seconds
# Old entries are removed based on window_seconds
```

## Common Use Cases

### API Rate Limiting

```python
# Standard REST API rate limiting
api_rate_limit = RateLimitMiddleware(
    max_requests=1000,    # 1000 requests per hour
    window_seconds=3600,
    strategy="sliding_window"
)

# Apply to all API routes
with router.group(prefix="api", middleware=[api_rate_limit]) as api:
    api.on("users/{id}", UserController.get_user)
    api.on("orders/{id}", OrderController.get_order)
```

### Device Telemetry

```python
# IoT device data ingestion
telemetry_rate_limit = RateLimitMiddleware(
    max_requests=500,     # 500 messages per minute
    window_seconds=60,
    strategy="token_bucket",
    burst_allowance=100   # Allow bursts up to 600
)

router.on("devices/{device_id}/data", 
          DeviceController.ingest_data,
          middleware=[telemetry_rate_limit])
```

### Public Endpoints

```python
# Public API with stricter limits
public_rate_limit = RateLimitMiddleware(
    max_requests=100,     # 100 requests per hour
    window_seconds=3600,
    custom_error_message="Public API rate limit reached. Please try again later."
)

router.on("public/weather/{city}", 
          WeatherController.get_weather,
          middleware=[public_rate_limit])
```

## Troubleshooting

### Common Issues

**Rate limiting not working:**
- Check if Redis is enabled and accessible
- Verify fallback_enabled setting
- Check logs for Redis connection errors

**Different behavior between instances:**
- Ensure all instances use the same Redis backend
- Check Redis key prefix consistency
- Verify Redis configuration

**Memory usage growing:**
- Memory fallback automatically cleans up expired entries
- Check cleanup interval settings
- Monitor memory usage in single-instance deployments

### Debug Logging

Enable debug logging to troubleshoot rate limiting:

```python
import logging
logging.getLogger('app.middleware.rate_limit').setLevel(logging.DEBUG)
```

## Next Steps

- [Rate Limiting Strategies](strategies.md) - Learn about different algorithms
- [Topic-Specific Limits](topic-specific.md) - Set custom limits per topic
- [Client-Based Limiting](client-based.md) - Rate limit by client instead of topic
- [Advanced Features](advanced-features.md) - Whitelisting, custom messages, and more
