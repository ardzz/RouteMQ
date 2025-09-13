# Middleware

Middleware allows you to process messages before they reach route handlers.

## Topics

- [Creating Middleware](creating-middleware.md) - Basic middleware structure
- [Built-in Middleware](built-in-middleware.md) - Available middleware components
- [Middleware Chains](middleware-chains.md) - Combining multiple middleware
- [Authentication Middleware](authentication.md) - User authentication
- [Caching Middleware](caching.md) - Response caching

## Quick Overview

Middleware processes messages in a chain before reaching the final handler:

```python
from core.middleware import Middleware
from core.redis_manager import redis_manager
import time

class LoggingMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Log incoming messages with Redis integration"""
        start_time = time.time()
        topic = context['topic']
        
        self.logger.info(f"Processing message on topic: {topic}")
        
        # Increment message counter in Redis
        if redis_manager.is_enabled():
            await redis_manager.incr(f"stats:messages:{topic}")
            await redis_manager.incr("stats:messages:total")
        
        # Call the next handler in the chain
        result = await next_handler(context)
        
        # Log processing time
        processing_time = time.time() - start_time
        self.logger.info(f"Message processed in {processing_time:.3f}s")
        
        return result
```

## Common Middleware Patterns

### Authentication Middleware
```python
class AuthMiddleware(Middleware):
    async def handle(self, context, next_handler):
        payload = context['payload']
        
        api_key = payload.get('api_key')
        if not self.is_valid_api_key(api_key):
            return {"error": "Invalid API key"}
        
        return await next_handler(context)
```

### Caching Middleware
```python
class CachingMiddleware(Middleware):
    async def handle(self, context, next_handler):
        cache_key = self._generate_cache_key(context)
        
        # Try cache first
        if redis_manager.is_enabled():
            cached_result = await redis_manager.get_json(cache_key)
            if cached_result:
                return cached_result
        
        # Execute handler and cache result
        result = await next_handler(context)
        if redis_manager.is_enabled():
            await redis_manager.set_json(cache_key, result, ex=300)
        
        return result
```

## Next Steps

- [Creating Middleware](creating-middleware.md) - Build custom middleware
- [Rate Limiting](../rate-limiting/README.md) - Advanced rate limiting middleware
