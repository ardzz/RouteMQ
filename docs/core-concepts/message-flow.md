# Message Flow

Understanding how messages flow through RouteMQ from MQTT broker to your application handlers is crucial for building efficient and reliable applications.

## Complete Message Flow

```
┌─────────────────┐---->┌─────────────────┐---->┌─────────────────┐---->┌─────────────────┐
│   MQTT Broker   │     │  Route Matcher  │     │  Middleware     │     │   Controller    │
│ - Receives Msg  │     │ - Topic Match   │     │ - Auth Check    │     │ - Business      │
│ - Delivers      │     │ - Extract Params│     │ - Rate Limit    │     │   Logic         │
│ - Load Balance  │     │ - Find Route    │     │ - Logging       │     │ - Data Process  │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
         |                         |                         |                         |
         |                         |                         |                         v
         |                         |                         |                ┌─────────────────┐
         |                         |                         |                │    Response     │
         |                         |                         |                │ - Publish Reply │
         |                         |                         |                │ - Update State  │
         |                         |                         |                │ - Log Result    │
         |                         |                         |                └─────────────────┘
         |                         |                         |
         v                         v                         v
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Error Case   │     │     No Route    │     │ Middleware Block│
│ - Log Error     │     │ - Log Warning   │     │ - Auth Failed   │
│ - Continue Op   │     │ - Continue Op   │     │ - Rate Limited  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Step-by-Step Flow

### 1. Message Reception

The MQTT client receives a message from the broker:

```python
def _on_message(self, client, userdata, msg):
    """Callback when message received from broker"""
    topic = msg.topic
    payload = msg.payload
    
    # Handle shared subscription topic format
    if topic.startswith("$share/"):
        actual_topic = extract_actual_topic(topic)
    
    # Decode payload
    try:
        decoded_payload = json.loads(payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        decoded_payload = payload
```

### 2. Route Matching

The router finds a matching route using regex patterns:

```python
async def dispatch(self, topic: str, payload: Any, client) -> None:
    """Find matching route and dispatch message"""
    
    for route in self.routes:
        params = route.matches(topic)
        if params:
            # Route found - extract parameters
            context = {
                'topic': topic,
                'payload': payload,
                'params': params,
                'client': client,
                'route': route
            }
            
            # Process through middleware pipeline
            await self._process_middleware_chain(context, route)
            return
    
    # No route found
    self.logger.warning(f"No route found for topic: {topic}")
```

#### Route Matching Example

```python
# Route definition
router.on("sensors/{device_id}/data/{sensor_type}", SensorController.handle_data)

# Incoming topic: "sensors/device123/data/temperature"
# Extracted params: {'device_id': 'device123', 'sensor_type': 'temperature'}
```

### 3. Parameter Extraction

Route parameters are extracted using regex groups:

```python
class Route:
    def _compile_topic_pattern(self) -> re.Pattern:
        """Convert Laravel-style params to regex"""
        pattern = self.topic
        # {device_id} becomes (?P<device_id>[^/]+)
        pattern = re.sub(r'{([^/]+)}', r'(?P<\1>[^/]+)', pattern)
        return re.compile(f'^{pattern}$')
    
    def matches(self, topic: str) -> dict[str, str] | None:
        """Extract parameters from topic"""
        match = self.pattern.match(topic)
        if match:
            return match.groupdict()  # Returns {'device_id': 'value', ...}
        return None
```

### 4. Middleware Pipeline Processing

Messages pass through middleware in order:

```python
async def _process_middleware_chain(self, context: dict, route: Route):
    """Process message through middleware pipeline"""
    
    middleware_chain = route.middleware
    
    async def create_next_handler(index: int):
        """Create next handler for middleware chain"""
        if index >= len(middleware_chain):
            # End of chain - call actual handler
            return await self._call_route_handler(context, route)
        
        middleware = middleware_chain[index]
        
        async def next_handler(ctx: dict):
            return await create_next_handler(index + 1)
        
        return await middleware.handle(context, next_handler)
    
    await create_next_handler(0)
```

#### Middleware Chain Example

```python
# Route with middleware
router.on("api/{endpoint}", 
          ApiController.handle,
          middleware=[AuthMiddleware(), RateLimitMiddleware(), LoggingMiddleware()])

# Execution order:
# 1. AuthMiddleware.handle()
# 2. RateLimitMiddleware.handle()  
# 3. LoggingMiddleware.handle()
# 4. ApiController.handle()
```

### 5. Controller Handler Execution

The final handler processes the business logic:

```python
async def _call_route_handler(self, context: dict, route: Route):
    """Call the route handler with context"""
    handler = route.handler
    
    if inspect.iscoroutinefunction(handler):
        return await handler(context)
    else:
        # Handle sync functions
        return handler(context)
```

## Context Object

The context dictionary carries information through the pipeline:

```python
context = {
    'topic': 'sensors/device123/data',      # Original MQTT topic
    'payload': {'temperature': 25.6},       # Decoded message payload
    'params': {'device_id': 'device123'},   # Extracted route parameters
    'client': mqtt_client,                  # MQTT client for publishing
    'route': route_object,                  # Route that matched
    'user': user_object,                    # Added by auth middleware
    'request_id': 'req_abc123',            # Added by logging middleware
}
```

## Error Handling Flow

### Route Not Found

```python
# No matching route
if not route_found:
    logger.warning(f"No route found for topic: {topic}")
    # Continue processing other messages
    return
```

### Middleware Errors

```python
try:
    await middleware.handle(context, next_handler)
except Exception as e:
    logger.error(f"Middleware error: {e}")
    # Error logged, processing stops for this message
    return
```

### Handler Errors

```python
try:
    await route.handler(context)
except Exception as e:
    logger.error(f"Handler error in {route.topic}: {e}")
    # Continue processing other messages
    return
```

## Async Processing

### Non-Blocking Operations

All processing is async to handle multiple messages concurrently:

```python
# Multiple messages processed simultaneously
async def handle_data(self, context):
    # Non-blocking database operation
    device = await self.db.get_device(context['params']['device_id'])
    
    # Non-blocking Redis operation  
    await self.redis.set(f"latest:{device.id}", context['payload'])
    
    # Non-blocking MQTT publish
    await self.publish(f"processed/{device.id}", {"status": "success"})
```

### Concurrent Message Handling

```python
# Framework handles multiple messages concurrently
await asyncio.gather(
    self.process_message(topic1, payload1),
    self.process_message(topic2, payload2),
    self.process_message(topic3, payload3)
)
```

## Shared Subscription Flow

For high-throughput routes with shared subscriptions:

```python
# Multiple workers process messages from same topic
┌─────────────────┐    ┌─────────────────┐
│   MQTT Broker   │───▶│    Worker 1     │
│                 │    │                 │
│ $share/group/   │───▶│    Worker 2     │  
│ sensors/+/data  │    │                 │
│                 │───▶│    Worker 3     │
└─────────────────┘    └─────────────────┘
```

### Worker Message Flow

Each worker follows the same message flow:

1. **Receive Message**: Worker gets message from shared subscription
2. **Strip Shared Prefix**: Remove `$share/group/` from topic
3. **Process Normally**: Follow standard route matching and middleware
4. **Independent Processing**: Each worker processes messages independently

## Performance Characteristics

### Throughput Optimization

* **Async Processing**: Handle multiple messages simultaneously
* **Shared Subscriptions**: Distribute load across workers
* **Middleware Caching**: Cache expensive operations in middleware
* **Connection Pooling**: Reuse database and Redis connections

### Latency Optimization

* **Direct Route Matching**: O(n) route lookup where n = number of routes
* **Minimal Middleware**: Only necessary middleware in chain
* **Async I/O**: Non-blocking external operations
* **Memory Efficiency**: Reuse context objects

## Message Flow Examples

### Simple Temperature Reading

```python
# Topic: sensors/device123/temperature
# Route: sensors/{device_id}/{sensor_type}

1. Message received: {"value": 25.6, "timestamp": "2024-01-01T12:00:00Z"}
2. Route matched: sensors/{device_id}/{sensor_type}
3. Parameters extracted: {"device_id": "device123", "sensor_type": "temperature"}
4. Middleware chain: [LoggingMiddleware]
5. Handler called: SensorController.handle_reading
6. Data stored in database
7. Alert published if threshold exceeded
```

### API Gateway Flow

```python
# Topic: api/devices/list
# Route: api/{endpoint}

1. Message received: {"user_id": "user456", "filters": {"status": "active"}}
2. Route matched: api/{endpoint}
3. Parameters extracted: {"endpoint": "devices/list"}
4. Middleware chain: [AuthMiddleware, RateLimitMiddleware, LoggingMiddleware]
5. AuthMiddleware: Validates user token
6. RateLimitMiddleware: Checks request rate
7. LoggingMiddleware: Logs request
8. Handler called: ApiController.handle_request
9. Response published to api/response/{request_id}
```

## Flow Monitoring

### Built-in Logging

```python
# Router logs
INFO: Message received on topic: sensors/device123/data
DEBUG: Route matched: sensors/{device_id}/data -> SensorController.handle_data
DEBUG: Processing through 2 middleware
INFO: Message processed successfully in 45ms

# Middleware logs  
INFO: [Auth] User authenticated: user123
INFO: [RateLimit] Request allowed: 15/100 requests
INFO: [Logging] Request ID: req_abc123
```

### Custom Monitoring

Add monitoring middleware:

```python
class MetricsMiddleware(Middleware):
    async def handle(self, context, next_handler):
        start_time = time.time()
        
        try:
            result = await next_handler(context)
            # Record success metric
            metrics.increment('messages.processed.success')
            return result
        except Exception as e:
            # Record error metric
            metrics.increment('messages.processed.error')
            raise
        finally:
            # Record processing time
            duration = time.time() - start_time
            metrics.histogram('messages.processing_time', duration)
```

## Next Steps

* [Middleware Pipeline](middleware-pipeline.md) - Implement message processing logic
* [Worker Processes](worker-processes.md) - Scale with shared subscriptions
* [Controllers](../controllers/) - Write message handlers
