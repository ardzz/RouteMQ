# Router Discovery

RouteMQ automatically discovers and loads route definitions from your application using a convention-based approach inspired by modern web frameworks.

## Discovery Process

The RouterRegistry class handles automatic route discovery through these steps:

1. **Package Scanning**: Scans the `app/routers` directory for Python modules
2. **Module Import**: Dynamically imports each router module
3. **Router Extraction**: Looks for a `router` variable in each module
4. **Route Merging**: Combines all routes into a single master router

## File Structure Convention

```
app/
└── routers/
    ├── __init__.py
    ├── device_routes.py      # Device-related routes
    ├── sensor_routes.py      # Sensor-related routes
    ├── alerts_routes.py      # Alert handling routes
    └── api_routes.py         # API gateway routes
```

## Router Module Format

Each router file must export a `router` variable:

```python
# app/routers/device_routes.py
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.auth_middleware import AuthMiddleware

# Create router instance - REQUIRED
router = Router()

# Define routes
router.on("devices/{device_id}/status", DeviceController.get_status)
router.on("devices/{device_id}/command", DeviceController.handle_command, qos=1)

# Use route groups for organization
with router.group(prefix="devices", middleware=[AuthMiddleware()]) as devices:
    devices.on("heartbeat/{device_id}", DeviceController.heartbeat)
    devices.on("telemetry/{device_id}", DeviceController.telemetry, qos=2)
```

## Discovery Configuration

### Default Discovery

By default, RouterRegistry scans `app.routers`:

```python
# bootstrap/app.py
from core.router_registry import RouterRegistry

# Uses app.routers by default
registry = RouterRegistry()
main_router = registry.discover_and_load_routers()
```

### Custom Directory

You can specify a different router directory:

```python
# Custom router location
registry = RouterRegistry("my_app.custom_routes")
main_router = registry.discover_and_load_routers()
```

## Module Discovery Rules

### Included Modules

- All `.py` files in the router directory
- Non-package modules (files, not directories)
- Modules that don't start with underscore (`_`)

### Excluded Modules

- `__init__.py` files
- Private modules starting with `_`
- Subdirectories (packages)
- Files without `.py` extension

### Example Directory Structure

```
app/routers/
├── __init__.py           # ❌ Excluded (init file)
├── _private.py           # ❌ Excluded (private module)
├── device_routes.py      # ✅ Included
├── sensor_routes.py      # ✅ Included
├── api_routes.py         # ✅ Included
└── helpers/              # ❌ Excluded (subdirectory)
    └── utils.py
```

## Route Merging Process

### Sequential Loading

Routes are loaded and merged in alphabetical order:

```python
# Discovery order
1. api_routes.py
2. device_routes.py  
3. sensor_routes.py
```

### Route Combination

All routes from discovered modules are combined into a single router:

```python
# Before merging
device_routes.py: 3 routes
sensor_routes.py: 5 routes
api_routes.py: 2 routes

# After merging
main_router: 10 total routes
```

### Conflict Resolution

- **Topic Conflicts**: Later-loaded routes override earlier ones with same topic
- **Middleware Isolation**: Each route maintains its own middleware chain
- **No Cross-Contamination**: Routes from different files don't affect each other

## Worker Process Discovery

Workers need to reload routes in separate processes:

```python
# RouterRegistry provides path for workers
registry = RouterRegistry("app.routers")
router_path = registry.get_router_module_path_for_workers()

# Workers use the same path to reload routes
worker_registry = RouterRegistry(router_path)
worker_router = worker_registry.discover_and_load_routers()
```

## Error Handling

### Import Errors

When a router module can't be imported:

```python
# RouterRegistry logs error and continues
ERROR: Could not import router module 'app.routers.broken_routes': ModuleNotFoundError
INFO: Using routes from successfully loaded modules
```

### Missing Router Variable

When a module doesn't export `router`:

```python
# Warning logged, module skipped
WARNING: Module app.routers.no_router does not have a 'router' attribute
```

### Invalid Router Type

When `router` variable isn't a Router instance:

```python
# Warning logged, module skipped  
WARNING: Module app.routers.bad_router has 'router' attribute but it's not a Router instance
```

## Development Workflow

### Adding New Routes

1. Create new file in `app/routers/`
2. Define router and routes
3. Restart application (routes loaded at startup)

```python
# app/routers/new_feature.py
from core.router import Router
from app.controllers.new_controller import NewController

router = Router()
router.on("new/feature/{id}", NewController.handle)
```

### Route Organization

Group related routes in the same file:

```python
# app/routers/iot_devices.py
router = Router()

# All IoT device routes in one file
with router.group(prefix="iot") as iot:
    iot.on("sensors/{sensor_id}/data", IoTController.sensor_data)
    iot.on("actuators/{actuator_id}/command", IoTController.actuator_command)
    iot.on("gateways/{gateway_id}/status", IoTController.gateway_status)
```

## Advanced Features

### Conditional Route Loading

Load routes based on environment:

```python
# app/routers/debug_routes.py
import os
from core.router import Router

router = Router()

# Only load debug routes in development
if os.getenv("ENVIRONMENT") == "development":
    router.on("debug/test", DebugController.test_endpoint)
```

### Dynamic Route Generation

Generate routes programmatically:

```python
# app/routers/dynamic_routes.py
from core.router import Router

router = Router()

# Generate routes for multiple devices
device_types = ["temperature", "humidity", "pressure"]
for device_type in device_types:
    router.on(f"sensors/{device_type}/{{device_id}}", 
              SensorController.handle_sensor_data)
```

## Logging and Debugging

### Discovery Logging

RouterRegistry provides detailed logging:

```
INFO: Discovered router modules: ['app.routers.api_routes', 'app.routers.device_routes']
INFO: Merged 3 routes from app.routers.api_routes
INFO: Merged 5 routes from app.routers.device_routes  
INFO: Successfully loaded 8 total routes from 2 modules
```

### Route Inspection

Debug loaded routes:

```python
registry = RouterRegistry()
router = registry.discover_and_load_routers()

# Inspect loaded routes
for route in router.routes:
    print(f"Topic: {route.topic}")
    print(f"MQTT Topic: {route.mqtt_topic}")
    print(f"Handler: {route.handler}")
    print(f"Shared: {route.shared}")
```

## Best Practices

### File Naming

Use descriptive names that group related functionality:

- ✅ `device_management.py`
- ✅ `sensor_telemetry.py`
- ✅ `user_authentication.py`
- ❌ `routes.py`
- ❌ `misc.py`

### Route Organization

Group routes logically within files:

```python
# Good: Related routes together
with router.group(prefix="users") as users:
    users.on("login/{user_id}", AuthController.login)
    users.on("logout/{user_id}", AuthController.logout)
    users.on("profile/{user_id}", UserController.get_profile)
```

### Error Prevention

Always include the router variable:

```python
# Required at module level
router = Router()

# Not inside functions or classes
def create_router():  # ❌ Wrong
    return Router()
```

## Next Steps

- [Message Flow](message-flow.md) - Understand how discovered routes process messages
- [Middleware Pipeline](middleware-pipeline.md) - Add cross-cutting concerns to routes
- [Creating Routes](../routing/README.md) - Learn route definition syntax
