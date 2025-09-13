# API Reference

Complete API documentation for RouteMQ framework components.

## Topics

- [Router API](router-api.md) - Router class methods and options
- [Controller API](controller-api.md) - Controller base class and utilities
- [Middleware API](middleware-api.md) - Middleware interface and methods
- [Redis Manager API](redis-manager-api.md) - Redis operations and methods
- [Worker Manager API](worker-manager-api.md) - Worker process management

## Quick Reference

### Router Class

```python
from core.router import Router

router = Router()

# Basic route definition
router.on(topic_pattern, handler, qos=0, shared=False, worker_count=1, middleware=[])

# Route groups
with router.group(prefix="api", middleware=[auth]) as group:
    group.on("endpoint", handler)
```

### Controller Class

```python
from core.controller import Controller

class MyController(Controller):
    @staticmethod
    async def handler(param1, param2, payload, client):
        # Handler implementation
        return {"status": "success"}
```

### Middleware Class

```python
from core.middleware import Middleware

class MyMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Pre-processing
        result = await next_handler(context)
        # Post-processing
        return result
```

### Redis Manager

```python
from core.redis_manager import redis_manager

# Basic operations
await redis_manager.set("key", "value", ex=60)
value = await redis_manager.get("key")

# JSON operations
await redis_manager.set_json("key", {"data": "value"}, ex=60)
data = await redis_manager.get_json("key")
```

## Method Signatures

### Router.on()
```python
def on(self, topic_pattern: str, handler: callable, 
       qos: int = 0, shared: bool = False, 
       worker_count: int = 1, middleware: list = []) -> None
```

### Router.group()
```python
def group(self, prefix: str = "", middleware: list = []) -> RouterGroup
```

### RedisManager Methods
```python
async def set(self, key: str, value: str, ex: int = None) -> bool
async def get(self, key: str) -> str
async def delete(self, key: str) -> bool
async def set_json(self, key: str, value: dict, ex: int = None) -> bool
async def get_json(self, key: str) -> dict
async def incr(self, key: str, amount: int = 1) -> int
async def hset(self, name: str, key: str, value: str) -> bool
async def hget(self, name: str, key: str) -> str
```

## Next Steps

- [Router API](router-api.md) - Detailed router documentation
- [Controller API](controller-api.md) - Controller class reference
- [Middleware API](middleware-api.md) - Middleware development guide
