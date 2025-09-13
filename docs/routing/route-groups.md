# Route Groups

Learn how to organize and structure your routes using RouteMQ's route groups, enabling shared prefixes, middleware, and logical organization of related endpoints.

## Overview

Route groups allow you to organize related routes under a common prefix and apply shared middleware, reducing code duplication and improving maintainability.

```python
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.auth_middleware import AuthMiddleware

router = Router()

# Group routes with common prefix and middleware
with router.group(prefix="devices", middleware=[AuthMiddleware()]) as devices:
    devices.on("status/{device_id}", DeviceController.handle_status)
    devices.on("config/{device_id}", DeviceController.handle_config)
    devices.on("commands/{device_id}", DeviceController.handle_commands)
```

## Basic Group Syntax

### Simple Prefix Grouping

```python
# Without groups (repetitive)
router.on("api/v1/users/list", UserController.list_users)
router.on("api/v1/users/create", UserController.create_user)
router.on("api/v1/users/{user_id}", UserController.get_user)

# With groups (cleaner)
with router.group(prefix="api/v1/users") as api_users:
    api_users.on("list", UserController.list_users)
    api_users.on("create", UserController.create_user)
    api_users.on("{user_id}", UserController.get_user)
```

The resulting MQTT topics become:
- `api/v1/users/list`
- `api/v1/users/create`
- `api/v1/users/{user_id}` (matches `api/v1/users/123`, etc.)

## Shared Middleware

### Applying Middleware to Groups

```python
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

# Create middleware instances
auth = AuthMiddleware()
rate_limit = RateLimitMiddleware(max_requests=100, window_seconds=60)
logging = LoggingMiddleware()

# Apply to entire group
with router.group(prefix="secure/api", middleware=[auth, rate_limit, logging]) as secure_api:
    secure_api.on("users/{user_id}", UserController.get_user)
    secure_api.on("devices/{device_id}/control", DeviceController.control)
    secure_api.on("admin/settings", AdminController.get_settings)
```

### Middleware Execution Order

Middleware executes in the order specified in the list:

```python
with router.group(middleware=[
    LoggingMiddleware(),      # Executes first
    AuthMiddleware(),         # Executes second  
    RateLimitMiddleware()     # Executes third
]) as protected:
    protected.on("endpoint", handler)
```

## Feature-based Organization

### IoT Device Management System

```python
from app.middleware.device_auth import DeviceAuthMiddleware
from app.middleware.telemetry_middleware import TelemetryMiddleware

# Device telemetry (high volume, basic auth)
telemetry_middleware = [DeviceAuthMiddleware(), TelemetryMiddleware()]
with router.group(prefix="telemetry", middleware=telemetry_middleware) as telemetry:
    telemetry.on("sensors/{sensor_id}/temperature", SensorController.handle_temperature, 
                 qos=0, shared=True, worker_count=5)
    telemetry.on("sensors/{sensor_id}/humidity", SensorController.handle_humidity,
                 qos=0, shared=True, worker_count=3)
    telemetry.on("devices/{device_id}/status", DeviceController.handle_status,
                 qos=1, shared=True, worker_count=2)

# Device commands (critical, authenticated)
command_middleware = [DeviceAuthMiddleware(), LoggingMiddleware()]
with router.group(prefix="commands", middleware=command_middleware) as commands:
    commands.on("devices/{device_id}/restart", DeviceController.restart, qos=2)
    commands.on("devices/{device_id}/update", DeviceController.update_firmware, qos=2)
    commands.on("devices/{device_id}/config", DeviceController.update_config, qos=1)

# Administrative operations (highly secured)
admin_middleware = [AdminAuthMiddleware(), AuditLogMiddleware(), RateLimitMiddleware(10, 60)]
with router.group(prefix="admin", middleware=admin_middleware) as admin:
    admin.on("devices/provision", AdminController.provision_device)
    admin.on("users/create", AdminController.create_user)
    admin.on("system/config", AdminController.update_system_config)
```

## API Versioning with Groups

```python
# Version 1 API (legacy support)
v1_middleware = [LoggingMiddleware(), LegacyCompatibilityMiddleware()]
with router.group(prefix="api/v1", middleware=v1_middleware) as v1:
    v1.on("users/{user_id}", UserControllerV1.get_user)
    v1.on("devices/{device_id}", DeviceControllerV1.get_device)

# Version 2 API (current)
v2_middleware = [LoggingMiddleware(), AuthMiddleware(), RateLimitMiddleware(200, 60)]
with router.group(prefix="api/v2", middleware=v2_middleware) as v2:
    v2.on("users/{user_id}", UserControllerV2.get_user)
    v2.on("devices/{device_id}", DeviceControllerV2.get_device)
    v2.on("analytics/events", AnalyticsController.track_event)
```

## Group Configuration Options

### Shared Subscription Settings

```python
# Apply shared subscription settings to entire group
with router.group(prefix="high-volume") as hv:
    # All routes in this group will use shared subscriptions
    hv.on("logs/{level}", LogController.handle, shared=True, worker_count=8)
    hv.on("metrics/{type}", MetricsController.handle, shared=True, worker_count=5)
    hv.on("events/{category}", EventController.handle, shared=True, worker_count=10)
```

### QoS Settings per Group

```python
# Critical operations group (QoS 2)
with router.group(prefix="critical") as critical:
    critical.on("alerts/{type}", AlertController.handle, qos=2)
    critical.on("commands/{device_id}", CommandController.handle, qos=2)

# Logging group (QoS 0)  
with router.group(prefix="logs") as logs:
    logs.on("info/{source}", LogController.handle_info, qos=0)
    logs.on("debug/{source}", LogController.handle_debug, qos=0)
```

## Environment-based Grouping

```python
import os

env = os.getenv('ENVIRONMENT', 'production')

# Different prefixes for different environments
prefix = f"env/{env}/api" if env != 'production' else "api"

with router.group(prefix=prefix) as api:
    api.on("health", HealthController.check)
    api.on("users/{user_id}", UserController.get_user)

# Production: api/health, api/users/{user_id}
# Staging: env/staging/api/health, env/staging/api/users/{user_id}
```

## Best Practices

### Logical Organization

- Group by domain/feature area (users, devices, analytics)
- Use consistent naming conventions across groups
- Keep related functionality together

### Middleware Strategy

```python
# Light middleware for high-volume routes
with router.group(prefix="telemetry", middleware=[BasicAuthMiddleware()]) as telemetry:
    # High-frequency sensor data
    
# Heavy middleware for admin routes  
admin_middleware = [
    AuthMiddleware(),
    AdminPermissionMiddleware(), 
    AuditLogMiddleware(),
    RateLimitMiddleware(max_requests=10)
]
with router.group(prefix="admin", middleware=admin_middleware) as admin:
    # Administrative operations
```

### Performance Considerations

- Group high-volume routes together for optimized middleware
- Use shared subscriptions for groups with heavy traffic
- Apply rate limiting at the group level for quota management
- Consider QoS requirements when grouping routes

### Security Boundaries

- Group routes by authentication requirements
- Apply authorization middleware at appropriate group levels
- Separate public and private API groups
- Use different middleware stacks for different security zones

## Next Steps

- [Dynamic Router Loading](dynamic-loading.md) - Auto-discover route files
- [Middleware](../middleware/README.md) - Create custom middleware for groups
- [Controllers](../controllers/README.md) - Organize handler functions by feature
