# Framework Architecture

RouteMQ is built with a modular, scalable architecture that follows familiar web framework patterns adapted for MQTT messaging.

## System Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MQTT Broker   │◄──►│   RouteMQ App   │◄──►│   External      │
│                 │    │                 │    │   Services      │
│ - Message Queue │    │ - Route Handler │    │ - Database      │
│ - Pub/Sub       │    │ - Middleware    │    │ - Redis         │
│ - Load Balance  │    │ - Workers       │    │ - APIs          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Core Components

### 1. Router System

The routing system is the heart of RouteMQ, providing Laravel-style route definitions with parameter extraction:

- **Router**: Main routing class that manages route definitions
- **Route**: Individual route definitions with topic patterns, handlers, and configuration
- **RouterGroup**: Groups routes with shared prefixes and middleware

```python
# Example route definition
router.on("sensors/{device_id}/data", DeviceController.handle_data, qos=1)

# Route groups with shared configuration
with router.group(prefix="sensors", middleware=[AuthMiddleware()]) as devices:
    devices.on("message/{device_id}", DeviceController.handle_message)
```

### 2. Router Registry

Automatically discovers and loads route files from the application:

- **Dynamic Discovery**: Scans the `app/routers` directory for route definitions
- **Module Loading**: Imports and merges routes from multiple files
- **Hot Reloading**: Can reload routes during development

### 3. Middleware Pipeline

Processes messages before they reach route handlers:

- **Chain Processing**: Middleware executes in order with `next()` pattern
- **Context Passing**: Shared context dictionary passes through the chain
- **Early Termination**: Middleware can stop processing by not calling `next()`

### 4. Controller Architecture

Handles business logic with clean separation of concerns:

- **Async Support**: Built for non-blocking operations
- **Dependency Injection**: Access to Redis, database, and MQTT client
- **Parameter Extraction**: Route parameters automatically injected

### 5. Worker Management

Enables horizontal scaling through shared subscriptions:

- **Process Isolation**: Each worker runs in a separate process
- **Load Balancing**: MQTT broker distributes messages across workers
- **Dynamic Scaling**: Configure worker count per route

## Design Patterns

### Convention over Configuration

RouteMQ follows sensible defaults while allowing customization:

- Router files automatically discovered in `app/routers/`
- Controllers in `app/controllers/`
- Middleware in `app/middleware/`
- Environment-based configuration

### Async-First Architecture

Built around Python's asyncio for high-performance I/O:

```python
async def handle(self, context, next_handler):
    # Non-blocking database query
    result = await self.db.query("SELECT * FROM devices")
    context['devices'] = result
    return await next_handler(context)
```

### Modular Design

Loosely coupled components that can be tested and replaced independently:

- **Router**: Topic matching and parameter extraction
- **Middleware**: Cross-cutting concerns (auth, logging, rate limiting)
- **Controllers**: Business logic
- **Models**: Data layer abstraction

## Message Flow Architecture

1. **MQTT Subscription**: Framework subscribes to topic patterns
2. **Message Reception**: Broker delivers message to framework
3. **Route Matching**: Router finds matching route using regex patterns
4. **Parameter Extraction**: Route parameters extracted from topic
5. **Middleware Chain**: Message processed through middleware pipeline
6. **Handler Execution**: Controller method processes the message
7. **Response Handling**: Optional response published back to MQTT

## Scaling Architecture

### Vertical Scaling

- **Async Processing**: Handle multiple messages concurrently
- **Connection Pooling**: Efficient database and Redis connections
- **Memory Management**: Optimized message processing

### Horizontal Scaling

- **Shared Subscriptions**: Multiple workers for the same route
- **Process Isolation**: Worker processes for CPU-intensive tasks
- **Load Distribution**: MQTT broker balances across workers

```python
# Enable shared subscription with 3 workers
router.on("sensors/data", handler, shared=True, worker_count=3)
```

## Configuration Architecture

### Environment-Based Setup

```python
# Broker configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

# Worker configuration
WORKER_COUNT = int(os.getenv("WORKER_COUNT", 1))
GROUP_NAME = os.getenv("MQTT_GROUP_NAME", "mqtt_framework_group")
```

### Dependency Injection

Controllers have access to shared resources:

```python
class DeviceController(Controller):
    async def handle_data(self, context):
        # Access to Redis
        await self.redis.set(f"device:{context['device_id']}", data)
        
        # Access to MQTT client
        await self.publish("alerts/device", alert_data)
```

## Error Handling Architecture

- **Graceful Degradation**: Framework continues operating when routes fail
- **Logging Integration**: Comprehensive logging at all levels
- **Exception Isolation**: Route errors don't affect other routes
- **Recovery Mechanisms**: Automatic reconnection and retry logic

## Next Steps

- [Router Discovery](router-discovery.md) - Learn how routes are automatically loaded
- [Message Flow](message-flow.md) - Understand the complete message processing pipeline
- [Middleware Pipeline](middleware-pipeline.md) - Implement cross-cutting concerns
