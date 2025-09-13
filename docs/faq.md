# Frequently Asked Questions (FAQ)

Common questions and answers about RouteMQ.

## General Questions

### What is RouteMQ?
RouteMQ is a flexible MQTT routing framework inspired by web frameworks like Express.js and Laravel. It provides route-based message handling, middleware support, and horizontal scaling capabilities for MQTT applications.

### Why use RouteMQ instead of a basic MQTT client?
- **Organized Code**: Routes and controllers provide structure
- **Middleware Support**: Reusable components for authentication, logging, rate limiting
- **Horizontal Scaling**: Shared subscriptions with worker processes
- **Redis Integration**: Built-in caching and session management
- **Developer Experience**: Familiar patterns from web development

### What MQTT brokers are supported?
RouteMQ works with any MQTT broker that supports MQTT 3.1.1 or 5.0, including:
- Eclipse Mosquitto
- HiveMQ
- AWS IoT Core
- Azure IoT Hub
- Google Cloud IoT Core

## Installation and Setup

### Do I need Redis or MySQL?
No, both are optional:
- **Redis**: Recommended for caching, rate limiting, and distributed features
- **MySQL**: Only needed if you want persistent data storage

### Can I use other databases besides MySQL?
Currently, RouteMQ officially supports MySQL through SQLAlchemy. However, you can extend it to support other databases by modifying the database configuration.

### How do I migrate from a basic MQTT application?
1. Install RouteMQ
2. Create route files for your existing topics
3. Move your message handling logic to controllers
4. Add middleware as needed
5. Test and deploy incrementally

## Development

### How do route parameters work?
Route parameters use Laravel-style syntax with curly braces:
```python
# Route: devices/{device_id}/sensor/{sensor_type}
# Topic: devices/123/sensor/temperature
# Parameters: device_id="123", sensor_type="temperature"
```

### Can I use multiple middleware on a route?
Yes, middleware can be chained:
```python
middleware = [AuthMiddleware(), RateLimitMiddleware(), LoggingMiddleware()]
router.on("api/{endpoint}", handler, middleware=middleware)
```

### How do shared subscriptions work?
Shared subscriptions distribute messages across multiple worker processes:
```python
# This creates 3 worker processes for load balancing
router.on("high-volume/{topic}", handler, shared=True, worker_count=3)
```

## Performance and Scaling

### How many messages can RouteMQ handle?
Performance depends on:
- Hardware resources
- Message complexity
- Middleware overhead
- External service latency

With proper configuration and Redis caching, RouteMQ can handle thousands of messages per second.

### When should I use shared subscriptions?
Use shared subscriptions for:
- High-volume message topics
- CPU-intensive message processing
- When you need load balancing
- To improve fault tolerance

### How do I optimize performance?
- Use Redis for caching frequently accessed data
- Implement appropriate rate limiting
- Use shared subscriptions for high-throughput routes
- Optimize database queries and connection pooling
- Monitor and profile your application

## Troubleshooting

### Routes are not being discovered
Check:
- Router files are in `app/routers/` directory
- Files have a `router` variable
- No syntax errors in router files
- Proper imports and dependencies

### Redis connection failed
Verify:
- Redis server is running
- Connection details in `.env` file
- Network connectivity
- Redis authentication (if required)

### Worker processes not starting
Check:
- Shared subscription configuration
- MQTT broker supports shared subscriptions
- No port conflicts
- Sufficient system resources

## Best Practices

### How should I organize my routes?
Group related routes by domain:
```
app/routers/
├── devices.py      # Device management
├── sensors.py      # Sensor data
├── users.py        # User operations
└── notifications.py # Alerts and notifications
```

### Should I use QoS 0, 1, or 2?
- **QoS 0**: Non-critical messages, high throughput
- **QoS 1**: Important messages, at-least-once delivery
- **QoS 2**: Critical messages, exactly-once delivery (slower)

### How do I handle errors in controllers?
Use try-catch blocks and return error responses:
```python
async def handle_request(param, payload, client):
    try:
        # Process request
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return {"error": "Processing failed"}
```

## Advanced Features

### Can I use custom middleware?
Yes, create middleware by extending the Middleware base class:
```python
from core.middleware import Middleware

class CustomMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Custom logic
        return await next_handler(context)
```

### How do I implement custom rate limiting?
Extend the RateLimitMiddleware or create your own:
```python
class CustomRateLimitMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Custom rate limiting logic
        if self.is_rate_limited(context):
            return {"error": "Rate limit exceeded"}
        return await next_handler(context)
```

### Can I publish messages from controllers?
Yes, use the MQTT client parameter:
```python
async def handle_request(param, payload, client):
    # Process request
    result = {"status": "processed"}
    
    # Publish response
    client.publish(f"response/{param}", json.dumps(result))
    return result
```
