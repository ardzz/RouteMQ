# Route Definition

Learn how to define routes in RouteMQ using an intuitive, Laravel-inspired syntax for mapping MQTT topics to handler functions.

## Basic Route Syntax

Routes are defined using the `Router.on()` method, which maps MQTT topic patterns to handler functions:

```python
from core.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()

# Basic route definition
router.on("sensors/temperature", SensorController.handle_temperature)
```

## Route Components

### Topic Pattern

The topic pattern defines which MQTT topics will trigger your handler:

```python
# Static topic - matches exactly
router.on("devices/status", handler)

# Parameterized topic - matches dynamic values
router.on("devices/{device_id}/status", handler)

# Multi-level topic - matches nested structures
router.on("sensors/{type}/{location}/data", handler)
```

### Handler Function

The handler function receives the parsed parameters and message data:

```python
class SensorController:
    async def handle_temperature(self, payload, client, **params):
        # Handle temperature sensor data
        temperature = json.loads(payload)
        print(f"Temperature: {temperature['value']}°C")
```

## Route Options

### Quality of Service (QoS)

Control message delivery guarantees:

```python
# QoS 0 - At most once (fire and forget)
router.on("logs/{level}", LogController.handle, qos=0)

# QoS 1 - At least once (acknowledged delivery)
router.on("commands/{device_id}", CommandController.handle, qos=1)

# QoS 2 - Exactly once (guaranteed delivery)
router.on("critical/alerts", AlertController.handle, qos=2)
```

### Shared Subscriptions

Enable horizontal scaling with multiple workers:

```python
# Shared subscription with load balancing
router.on("high-volume/data", 
          DataController.handle_bulk, 
          shared=True, 
          worker_count=5)
```

### Middleware

Add processing logic to routes:

```python
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.logging_middleware import LoggingMiddleware

# Single middleware
router.on("api/users", UserController.handle, 
          middleware=[LoggingMiddleware()])

# Multiple middleware (executed in order)
router.on("api/devices", DeviceController.handle,
          middleware=[
              LoggingMiddleware(),
              RateLimitMiddleware(max_requests=100)
          ])
```

## Topic Pattern Matching

### Wildcards

RouteMQ automatically converts route parameters to MQTT wildcards:

```python
# Route definition
router.on("devices/{device_id}/status", handler)

# MQTT subscription topic becomes: "devices/+/status"
# Matches: "devices/sensor001/status", "devices/pump02/status"
```

### Pattern Examples

```python
# Simple parameter
router.on("users/{user_id}", handler)
# Matches: users/123, users/john_doe

# Multiple parameters
router.on("buildings/{building_id}/floors/{floor_id}", handler)
# Matches: buildings/A/floors/1, buildings/tower/floors/ground

# Mixed static and dynamic
router.on("api/v1/devices/{device_id}/config", handler)
# Matches: api/v1/devices/sensor01/config
```

## Complete Route Example

```python
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

router = Router()

# Comprehensive route definition
router.on(
    topic="secure/devices/{device_id}/commands/{command_type}",
    handler=DeviceController.handle_secure_command,
    qos=2,                    # Guaranteed delivery
    shared=True,              # Load balancing
    worker_count=3,           # 3 worker processes
    middleware=[
        AuthMiddleware(),     # Authentication check
        RateLimitMiddleware(max_requests=50, window_seconds=60)
    ]
)
```

## Handler Function Signature

Your handler functions should follow this signature:

```python
async def handler_function(self, payload, client, **params):
    """
    Args:
        payload: Raw message payload (bytes or str)
        client: MQTT client instance
        **params: Extracted route parameters as keyword arguments
    
    Returns:
        Any: Optional return value (logged for debugging)
    """
    # Process the message
    pass
```

## Best Practices

### Topic Naming

- Use lowercase with underscores: `device_status`
- Organize hierarchically: `buildings/sensors/temperature`
- Keep parameters descriptive: `{device_id}` not `{id}`

### Route Organization

- Group related routes in separate files
- Use consistent parameter naming across routes
- Document complex topic patterns

### Performance Considerations

- Use appropriate QoS levels (0 for logs, 1 for commands, 2 for critical)
- Enable shared subscriptions for high-volume topics
- Apply rate limiting to prevent abuse

## Next Steps

- [Route Parameters](route-parameters.md) - Learn parameter extraction
- [Route Groups](route-groups.md) - Organize routes with prefixes
- [Controllers](../controllers/README.md) - Create handler functions
