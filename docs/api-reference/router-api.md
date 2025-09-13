# Router API

Complete API reference for the RouteMQ Router class and related components.

## Router Class

The `Router` class is the core routing component that manages MQTT topic patterns and dispatches messages to appropriate handlers.

### Constructor

```python
from core.router import Router

router = Router()
```

Creates a new router instance with an empty route collection.

### Methods

#### on(topic, handler, qos=0, middleware=None, shared=False, worker_count=1)

Register a route handler for a specific topic pattern.

**Parameters:**
- `topic` (str): MQTT topic pattern with optional parameters (e.g., `"devices/{device_id}/status"`)
- `handler` (callable): Async function to handle matching messages
- `qos` (int, optional): Quality of Service level (0, 1, or 2). Default: 0
- `middleware` (List[Middleware], optional): Middleware to apply to this route. Default: None
- `shared` (bool, optional): Enable shared subscription for load balancing. Default: False
- `worker_count` (int, optional): Number of workers for shared subscriptions. Default: 1

**Returns:** None

**Example:**
```python
router.on("sensors/{sensor_id}/temperature", 
          SensorController.handle_temperature, 
          qos=1, 
          shared=True, 
          worker_count=3)
```

#### group(prefix="", middleware=None)

Create a route group with shared prefix and middleware.

**Parameters:**
- `prefix` (str, optional): Common topic prefix for all routes in the group. Default: ""
- `middleware` (List[Middleware], optional): Middleware to apply to all routes in the group. Default: None

**Returns:** RouterGroup instance

**Example:**
```python
with router.group(prefix="api/v1", middleware=[AuthMiddleware()]) as api:
    api.on("users/{user_id}", UserController.get_user)
    api.on("devices/{device_id}", DeviceController.get_device)
```

#### dispatch(topic, payload, client)

Find a matching route and dispatch the message through middleware to the handler.

**Parameters:**
- `topic` (str): The actual MQTT topic that received a message
- `payload` (Any): Message payload (parsed JSON or raw bytes/string)
- `client`: MQTT client instance

**Returns:** Any (the return value from the handler)

**Raises:** ValueError if no matching route is found

**Example:**
```python
# Internal usage - typically called by the framework
result = await router.dispatch("sensors/temp001/temperature", 
                               {"value": 23.5, "unit": "C"}, 
                               mqtt_client)
```

#### get_total_workers_needed()

Calculate the total number of workers needed for all shared routes.

**Returns:** int - Maximum worker count across all shared routes

**Example:**
```python
worker_count = router.get_total_workers_needed()
print(f"Need {worker_count} workers for shared subscriptions")
```

### Properties

#### routes

List of all registered Route objects.

**Type:** List[Route]

**Example:**
```python
print(f"Router has {len(router.routes)} routes registered")
for route in router.routes:
    print(f"Route: {route.topic} (QoS: {route.qos})")
```

## Route Class

Represents an individual route with its pattern, handler, and configuration.

### Constructor

```python
Route(topic, handler, qos=0, middleware=None, shared=False, worker_count=1)
```

**Note:** Routes are typically created internally by `Router.on()`. Direct instantiation is rarely needed.

### Properties

#### topic
The original topic pattern with parameters.
**Type:** str
**Example:** `"devices/{device_id}/status"`

#### handler
The async function that handles matching messages.
**Type:** Callable

#### qos
Quality of Service level for this route.
**Type:** int

#### middleware
List of middleware applied to this route.
**Type:** List[Middleware]

#### shared
Whether this route uses shared subscriptions.
**Type:** bool

#### worker_count
Number of workers for shared subscriptions.
**Type:** int

#### pattern
Compiled regex pattern for topic matching.
**Type:** re.Pattern

#### mqtt_topic
MQTT subscription topic with wildcards.
**Type:** str
**Example:** `"devices/+/status"` (for pattern `"devices/{device_id}/status"`)

### Methods

#### matches(topic)

Check if a topic matches this route and extract parameters.

**Parameters:**
- `topic` (str): Actual MQTT topic

**Returns:** dict[str, str] | None - Extracted parameters or None if no match

**Example:**
```python
route = Route("devices/{device_id}/status", handler)
params = route.matches("devices/sensor001/status")
# Returns: {"device_id": "sensor001"}
```

#### get_subscription_topic(group_name=None)

Get the MQTT subscription topic, with shared prefix if needed.

**Parameters:**
- `group_name` (str, optional): Group name for shared subscriptions

**Returns:** str - MQTT subscription topic

**Example:**
```python
# Regular subscription
topic = route.get_subscription_topic()
# Returns: "devices/+/status"

# Shared subscription
topic = route.get_subscription_topic("worker_group")
# Returns: "$share/worker_group/devices/+/status"
```

## RouterGroup Class

Context manager for grouping routes with shared prefixes and middleware.

### Constructor

```python
RouterGroup(router, prefix="", middleware=None)
```

**Note:** RouterGroup instances are created by `Router.group()`. Direct instantiation is not recommended.

### Methods

#### on(topic, handler, qos=0, middleware=None, shared=False, worker_count=1)

Register a route handler within this group.

**Parameters:** Same as `Router.on()`, but `topic` is relative to the group's prefix

**Example:**
```python
with router.group(prefix="sensors", middleware=[LoggingMiddleware()]) as sensors:
    # This creates route "sensors/temperature/{sensor_id}"
    sensors.on("temperature/{sensor_id}", handle_temperature)
```

### Properties

#### router
Reference to the parent Router instance.
**Type:** Router

#### prefix
Topic prefix for this group.
**Type:** str

#### middleware
Middleware applied to all routes in this group.
**Type:** List[Middleware]

## Topic Pattern Syntax

RouteMQ uses Laravel-style route parameters in topic patterns:

### Parameter Syntax
- `{parameter_name}` - Captures a single topic level
- Parameters can contain letters, numbers, underscores, and hyphens
- Parameters cannot contain forward slashes

### Examples

```python
# Simple parameter
"users/{user_id}"                    # Matches: users/123, users/john_doe

# Multiple parameters
"buildings/{building_id}/floors/{floor_id}"  # Matches: buildings/A/floors/1

# Mixed static and dynamic
"api/v1/devices/{device_id}/config"  # Matches: api/v1/devices/sensor01/config
```

### MQTT Wildcard Conversion

Route parameters are automatically converted to MQTT wildcards:

```python
"devices/{device_id}/status"     → "devices/+/status"
"sensors/{type}/{location}"      → "sensors/+/+"
"api/{version}/users/{user_id}"  → "api/+/users/+"
```

## Error Handling

### Common Exceptions

#### ValueError
Raised by `dispatch()` when no route matches the topic.

```python
try:
    await router.dispatch("unknown/topic", payload, client)
except ValueError as e:
    print(f"No route found: {e}")
```

### Best Practices

1. **Route Order**: Routes are matched in registration order. More specific routes should be registered first.

2. **Parameter Validation**: Validate parameters in your handlers:
```python
async def handle_device(device_id, payload, client):
    if not re.match(r'^[a-zA-Z0-9_-]+$', device_id):
        raise ValueError(f"Invalid device ID: {device_id}")
```

3. **Middleware Usage**: Use middleware for cross-cutting concerns:
```python
with router.group(middleware=[AuthMiddleware(), LoggingMiddleware()]) as secure:
    secure.on("admin/{action}", AdminController.handle)
```

4. **Shared Subscriptions**: Use for high-throughput scenarios:
```python
router.on("logs/{level}", LogController.handle, 
          shared=True, worker_count=5, qos=0)
```

## Complete Example

```python
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

# Create router
router = Router()

# Simple route
router.on("ping", DeviceController.handle_ping)

# Route with parameters and QoS
router.on("devices/{device_id}/commands/{command}", 
          DeviceController.handle_command, 
          qos=2)

# Grouped routes with middleware
auth_middleware = [AuthMiddleware(), RateLimitMiddleware(max_requests=100)]
with router.group(prefix="secure/api", middleware=auth_middleware) as secure_api:
    secure_api.on("users/{user_id}/profile", UserController.get_profile)
    secure_api.on("devices/{device_id}/control", DeviceController.control_device)

# High-throughput route with load balancing
router.on("telemetry/{sensor_type}/{sensor_id}", 
          TelemetryController.handle_data,
          qos=0, 
          shared=True, 
          worker_count=8)

# Check total workers needed
print(f"Total workers needed: {router.get_total_workers_needed()}")
```
