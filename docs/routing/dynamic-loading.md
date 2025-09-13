# Dynamic Router Loading

RouteMQ automatically discovers and loads route files from your application directory, enabling modular route organization and hot-swappable routing configurations.

## Overview

The RouterRegistry class provides automatic route discovery and loading capabilities:

- **Auto-discovery**: Scans `app/routers/` directory for route files
- **Dynamic import**: Loads route modules at runtime
- **Route merging**: Combines routes from multiple files into a single router
- **Error handling**: Graceful handling of missing or broken route files
- **Worker synchronization**: Ensures workers load the same route configuration

## How Dynamic Loading Works

### Discovery Process

```python
from core.router_registry import RouterRegistry

# Create registry with default directory
registry = RouterRegistry("app.routers")

# Discover and load all routes
main_router = registry.discover_and_load_routers()
```

The discovery process follows these steps:

1. **Package Import**: Imports the router package (`app.routers`)
2. **Module Scanning**: Uses `pkgutil.iter_modules()` to find all Python files
3. **Module Loading**: Dynamically imports each discovered module
4. **Router Extraction**: Looks for a `router` variable in each module
5. **Route Merging**: Combines all routes into a single master router

### File Structure Requirements

```
app/routers/
├── __init__.py              # Required package file
├── devices.py               # Device-related routes
├── sensors.py               # Sensor data routes
├── api.py                   # API endpoints
├── notifications.py         # Notification routes
└── admin.py                 # Admin routes
```

### Router Module Format

Each router file must export a `router` variable:

```python
# app/routers/devices.py
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.auth_middleware import AuthMiddleware

# REQUIRED: Export router variable
router = Router()

# Define routes
router.on("devices/{device_id}/status", DeviceController.get_status)
router.on("devices/{device_id}/control", DeviceController.control, qos=1)

# Use groups for organization
with router.group(prefix="devices", middleware=[AuthMiddleware()]) as devices:
    devices.on("heartbeat/{device_id}", DeviceController.heartbeat)
    devices.on("telemetry/{device_id}", DeviceController.telemetry, qos=2)
```

## Configuration Options

### Custom Router Directory

```python
# Use custom router directory
registry = RouterRegistry("custom_app.routes")
main_router = registry.discover_and_load_routers()

# Multiple directories (advanced usage)
registries = [
    RouterRegistry("app.api_routes"),
    RouterRegistry("app.device_routes"),
    RouterRegistry("plugins.external_routes")
]

combined_router = Router()
for registry in registries:
    router = registry.discover_and_load_routers()
    for route in router.routes:
        combined_router.routes.append(route)
```

### Environment-Based Loading

```python
import os
from core.router_registry import RouterRegistry

def create_router_registry():
    """Create router registry based on environment"""
    
    environment = os.getenv('ENVIRONMENT', 'development')
    
    if environment == 'production':
        return RouterRegistry("app.routers.production")
    elif environment == 'testing':
        return RouterRegistry("app.routers.testing")
    else:
        return RouterRegistry("app.routers")

registry = create_router_registry()
main_router = registry.discover_and_load_routers()
```

## Route File Organization

### Modular Organization

Organize routes by functional domain:

```python
# app/routers/iot_devices.py
from core.router import Router
from app.controllers.iot_controller import IoTController

router = Router()

# IoT device management
with router.group(prefix="iot") as iot:
    iot.on("devices/{device_id}/register", IoTController.register_device)
    iot.on("devices/{device_id}/data", IoTController.handle_data, qos=1)
    iot.on("devices/{device_id}/firmware", IoTController.firmware_update, qos=2)
```

```python
# app/routers/user_management.py
from core.router import Router
from app.controllers.user_controller import UserController
from app.middleware.auth_middleware import AuthMiddleware

router = Router()

# User management routes
auth_required = [AuthMiddleware()]

with router.group(prefix="users", middleware=auth_required) as users:
    users.on("profile/{user_id}", UserController.get_profile)
    users.on("settings/{user_id}/update", UserController.update_settings)
    users.on("notifications/{user_id}", UserController.get_notifications)
```

### Feature-Based Organization

```python
# app/routers/monitoring.py
from core.router import Router
from app.controllers.monitoring_controller import MonitoringController

router = Router()

# System monitoring routes
router.on("system/health", MonitoringController.health_check)
router.on("system/metrics", MonitoringController.get_metrics)
router.on("system/alerts/{alert_id}", MonitoringController.handle_alert)

# Application monitoring
with router.group(prefix="monitoring") as monitor:
    monitor.on("performance/{metric_type}", MonitoringController.performance_metrics)
    monitor.on("errors/{error_type}", MonitoringController.error_tracking)
```

## Advanced Features

### Conditional Route Loading

```python
# app/routers/debug_routes.py
import os
from core.router import Router
from app.controllers.debug_controller import DebugController

router = Router()

# Only load debug routes in development
if os.getenv('ENVIRONMENT') == 'development':
    router.on("debug/test/{test_id}", DebugController.run_test)
    router.on("debug/logs", DebugController.get_logs)
    router.on("debug/performance", DebugController.performance_test)
else:
    # Production: minimal debug routes
    router.on("debug/health", DebugController.health_only)
```

### Dynamic Route Generation

```python
# app/routers/dynamic_sensors.py
from core.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()

# Generate routes for different sensor types
sensor_types = ["temperature", "humidity", "pressure", "motion"]

for sensor_type in sensor_types:
    # Create route for each sensor type
    topic = f"sensors/{sensor_type}/{{sensor_id}}"
    router.on(topic, SensorController.handle_sensor_data)
    
    # Historical data routes
    history_topic = f"sensors/{sensor_type}/{{sensor_id}}/history"
    router.on(history_topic, SensorController.get_history)
```

### Plugin System Integration

```python
# app/routers/plugin_loader.py
import importlib
import os
from core.router import Router

router = Router()

# Load plugin routes dynamically
plugins_dir = os.getenv('PLUGINS_DIRECTORY', 'plugins')

if os.path.exists(plugins_dir):
    for plugin_name in os.listdir(plugins_dir):
        plugin_path = os.path.join(plugins_dir, plugin_name)
        
        if os.path.isdir(plugin_path) and not plugin_name.startswith('.'):
            try:
                # Import plugin router
                plugin_module = importlib.import_module(f"{plugins_dir}.{plugin_name}.routes")
                
                if hasattr(plugin_module, 'router'):
                    plugin_router = plugin_module.router
                    
                    # Merge plugin routes with namespace
                    with router.group(prefix=f"plugins/{plugin_name}") as plugin_group:
                        for route in plugin_router.routes:
                            plugin_group.on(route.topic, route.handler, 
                                          qos=route.qos, middleware=route.middleware)
                            
            except ImportError as e:
                print(f"Failed to load plugin {plugin_name}: {e}")
```

## Error Handling and Debugging

### Logging and Diagnostics

The RouterRegistry provides comprehensive logging:

```python
import logging

# Enable debug logging for router discovery
logging.getLogger("RouteMQ.RouterRegistry").setLevel(logging.DEBUG)

registry = RouterRegistry("app.routers")
main_router = registry.discover_and_load_routers()
```

Log output example:
```
INFO - Discovered router modules: ['app.routers.devices', 'app.routers.sensors', 'app.routers.api']
INFO - Merged 5 routes from app.routers.devices
INFO - Merged 8 routes from app.routers.sensors
INFO - Merged 12 routes from app.routers.api
INFO - Successfully loaded 25 total routes from 3 modules
```

### Common Issues and Solutions

#### Missing Router Variable
```python
# ❌ Wrong: No router variable exported
from core.router import Router

my_router = Router()  # Not named 'router'
my_router.on("test", handler)

# ✅ Correct: Export as 'router'
router = Router()
router.on("test", handler)
```

#### Import Errors
```python
# Handle missing dependencies gracefully
try:
    from optional_dependency import OptionalController
    router.on("optional/route", OptionalController.handle)
except ImportError:
    # Skip routes that depend on missing packages
    pass
```

#### Circular Imports
```python
# ❌ Wrong: Importing other route files
from app.routers.other_routes import some_function  # Circular import risk

# ✅ Correct: Import only controllers and middleware
from app.controllers.my_controller import MyController
from app.middleware.my_middleware import MyMiddleware
```

## Testing Dynamic Loading

### Unit Testing

```python
import pytest
from core.router_registry import RouterRegistry

def test_router_discovery():
    """Test that router discovery works correctly"""
    
    registry = RouterRegistry("tests.fixtures.test_routers")
    router = registry.discover_and_load_routers()
    
    # Verify routes were loaded
    assert len(router.routes) > 0
    
    # Test specific route exists
    route_topics = [route.topic for route in router.routes]
    assert "test/route/{id}" in route_topics

def test_missing_router_directory():
    """Test handling of missing router directory"""
    
    registry = RouterRegistry("nonexistent.package")
    router = registry.discover_and_load_routers()
    
    # Should return empty router without crashing
    assert len(router.routes) == 0

def test_invalid_router_module():
    """Test handling of invalid router modules"""
    
    # Create test module without router variable
    registry = RouterRegistry("tests.fixtures.invalid_routers")
    router = registry.discover_and_load_routers()
    
    # Should handle gracefully
    assert isinstance(router, Router)
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_dynamic_routes_work():
    """Test that dynamically loaded routes actually work"""
    
    from bootstrap.app import Application
    
    # Create application with dynamic loading
    app = Application()  # Uses RouterRegistry internally
    
    # Test that routes were loaded and work
    result = await app.router.dispatch(
        topic="devices/device123/status",
        payload={"test": "data"},
        client=None
    )
    
    assert result is not None
    assert "error" not in result
```

## Production Considerations

### Performance Optimization

```python
# Cache loaded routers for better performance
class CachedRouterRegistry(RouterRegistry):
    _router_cache = {}
    
    def discover_and_load_routers(self):
        """Load routers with caching"""
        
        cache_key = f"{self.router_directory}:{self._get_module_timestamps()}"
        
        if cache_key in self._router_cache:
            self.logger.debug("Using cached router")
            return self._router_cache[cache_key]
        
        router = super().discover_and_load_routers()
        self._router_cache[cache_key] = router
        
        return router
    
    def _get_module_timestamps(self):
        """Get modification timestamps for cache invalidation"""
        # Implementation to check file modification times
        pass
```

### Hot Reloading (Development)

```python
import importlib
import sys

class HotReloadRouterRegistry(RouterRegistry):
    """Router registry with hot reloading for development"""
    
    def reload_routes(self):
        """Reload all route modules"""
        
        # Clear module cache
        modules_to_reload = [
            module for module in sys.modules.keys()
            if module.startswith(self.router_directory)
        ]
        
        for module_name in modules_to_reload:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
        
        # Reload routes
        self.main_router = Router()
        return self.discover_and_load_routers()

# Usage in development
if os.getenv('ENVIRONMENT') == 'development':
    registry = HotReloadRouterRegistry("app.routers")
else:
    registry = RouterRegistry("app.routers")
```

### Deployment Strategies

```python
# Pre-compile routes for production
def build_production_router():
    """Build and validate router for production deployment"""
    
    registry = RouterRegistry("app.routers")
    router = registry.discover_and_load_routers()
    
    # Validate all routes
    for route in router.routes:
        # Check handler exists and is callable
        if not callable(route.handler):
            raise ValueError(f"Invalid handler for route {route.topic}")
        
        # Validate middleware
        for middleware in route.middleware:
            if not hasattr(middleware, 'handle'):
                raise ValueError(f"Invalid middleware for route {route.topic}")
    
    print(f"✓ Validated {len(router.routes)} routes for production")
    return router

# Run during deployment
if __name__ == "__main__":
    build_production_router()
```

## Best Practices

### File Organization
- **One domain per file**: Group related routes in single files
- **Consistent naming**: Use descriptive file names (`user_management.py`, not `users.py`)
- **Logical grouping**: Use route groups for shared prefixes and middleware

### Route Definition
- **Export router variable**: Always name your router instance `router`
- **Import at module level**: Import controllers and middleware at the top
- **Avoid side effects**: Don't perform actions during module import

### Error Handling
- **Graceful degradation**: Handle missing dependencies gracefully
- **Comprehensive logging**: Use appropriate log levels for debugging
- **Validation**: Validate routes during development and deployment

### Performance
- **Lazy loading**: Only import what you need
- **Caching**: Cache loaded routes in production
- **Monitoring**: Monitor route loading performance

## Next Steps

- [Shared Subscriptions](shared-subscriptions.md) - Scale with worker processes
- [Route Definition](route-definition.md) - Learn detailed route syntax
- [Route Groups](route-groups.md) - Organize routes effectively
- [Controllers](../controllers/README.md) - Create route handlers
