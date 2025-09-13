# Routing

Learn how to define and organize routes in RouteMQ.

## Topics

- [Route Definition](route-definition.md) - Basic route syntax and patterns
- [Route Parameters](route-parameters.md) - Extracting variables from topics
- [Route Groups](route-groups.md) - Organizing routes with common prefixes
- [Dynamic Router Loading](dynamic-loading.md) - Auto-discovery of route files
- [Shared Subscriptions](shared-subscriptions.md) - Horizontal scaling with workers

## Quick Overview

Routes in RouteMQ map MQTT topics to handler functions using an expressive syntax:

```python
from core.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()

# Simple route
router.on("sensors/temperature", SensorController.handle_temperature)

# Route with parameters
router.on("devices/{device_id}/status", SensorController.handle_device_status)

# Route with options
router.on("high-volume/{topic}", SensorController.handle_bulk, 
          qos=2, shared=True, worker_count=5)
```

## Route Organization

### Router File Structure

```
app/routers/
├── __init__.py
├── devices.py      # Device-related routes
├── sensors.py      # Sensor data routes
├── users.py        # User management routes
├── notifications.py # Notification routes
└── api.py          # General API routes
```

### Example Router File

```python
# app/routers/devices.py
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

router = Router()

# Rate limiting middleware
rate_limit = RateLimitMiddleware(max_requests=100, window_seconds=60)

# Device control routes
with router.group(prefix="devices", middleware=[LoggingMiddleware(), rate_limit]) as devices:
    devices.on("control/{device_id}", DeviceController.handle_control, qos=1, shared=True, worker_count=2)
    devices.on("status/{device_id}", DeviceController.handle_status, qos=0)
    devices.on("config/{device_id}/update", DeviceController.handle_config, qos=1)
```

## Next Steps

- [Route Definition](route-definition.md) - Learn detailed route syntax
- [Controllers](../controllers/README.md) - Create route handlers
- [Middleware](../middleware/README.md) - Add route processing logic
