# Route Parameters

Learn how to extract dynamic values from MQTT topics using RouteMQ's parameter system, enabling flexible and data-driven message routing.

## Parameter Syntax

Route parameters are defined using curly braces `{}` in topic patterns:

```python
from core.router import Router
from app.controllers.device_controller import DeviceController

router = Router()

# Single parameter
router.on("devices/{device_id}", DeviceController.handle_device)

# Multiple parameters  
router.on("buildings/{building_id}/floors/{floor_id}/sensors/{sensor_id}", 
          DeviceController.handle_sensor)
```

## Parameter Extraction

Parameters are automatically extracted and passed as keyword arguments to your handler functions:

```python
class DeviceController:
    async def handle_device(self, device_id, payload, client):
        """
        device_id: Extracted from {device_id} in the topic
        payload: Message payload
        client: MQTT client instance
        """
        print(f"Handling device: {device_id}")
        data = json.loads(payload)
        # Process device data...

    async def handle_sensor(self, building_id, floor_id, sensor_id, payload, client):
        """
        All parameters extracted from topic pattern
        """
        print(f"Sensor {sensor_id} on floor {floor_id} of building {building_id}")
        # Process sensor data...
```

## Parameter Patterns

### Basic Parameters

```python
# Device ID parameter
router.on("devices/{device_id}/status", handler)
# Matches: devices/sensor001/status → device_id="sensor001"
# Matches: devices/pump_02/status → device_id="pump_02"

# User parameter
router.on("users/{username}/preferences", handler) 
# Matches: users/john_doe/preferences → username="john_doe"
```

### Nested Parameters

```python
# Hierarchical structure
router.on("sites/{site_id}/zones/{zone_id}/devices/{device_id}", handler)

# Example handler
async def handle_device_in_zone(self, site_id, zone_id, device_id, payload, client):
    print(f"Site: {site_id}, Zone: {zone_id}, Device: {device_id}")
```

### Mixed Static and Dynamic

```python
# API versioning with parameters
router.on("api/v1/users/{user_id}/devices/{device_id}/config", handler)

# Category-based routing
router.on("sensors/{category}/{sensor_id}/readings", handler)
# Matches: sensors/temperature/temp001/readings → category="temperature", sensor_id="temp001"
```

## Parameter Validation

### Custom Validation in Handlers

```python
class DeviceController:
    async def handle_device_command(self, device_id, command_type, payload, client):
        # Validate device ID format
        if not re.match(r'^[a-zA-Z0-9_-]+$', device_id):
            print(f"Invalid device ID format: {device_id}")
            return
        
        # Validate command type
        valid_commands = ['start', 'stop', 'restart', 'status']
        if command_type not in valid_commands:
            print(f"Invalid command: {command_type}")
            return
        
        # Process valid command
        await self.execute_device_command(device_id, command_type, payload)
```

### Using Middleware for Validation

```python
from app.middleware.validation_middleware import ParameterValidationMiddleware

# Create validation rules
device_validator = ParameterValidationMiddleware({
    'device_id': r'^[a-zA-Z0-9_-]{1,50}$',
    'command_type': ['start', 'stop', 'restart', 'status']
})

# Apply to route
router.on("devices/{device_id}/commands/{command_type}", 
          DeviceController.handle_command,
          middleware=[device_validator])
```

## Working with Different Data Types

### String Parameters (Default)

```python
# All parameters are strings by default
router.on("users/{user_id}/settings/{setting_name}", handler)

async def handler(self, user_id, setting_name, payload, client):
    # user_id and setting_name are strings
    print(f"User: {user_id}, Setting: {setting_name}")
```

### Converting to Other Types

```python
async def handle_sensor_reading(self, sensor_id, reading_type, payload, client):
    # Convert parameters as needed
    try:
        # If sensor_id should be numeric
        sensor_number = int(sensor_id)
        
        # Parse payload
        data = json.loads(payload)
        timestamp = int(data.get('timestamp', 0))
        
        print(f"Sensor {sensor_number}: {reading_type} reading at {timestamp}")
    except ValueError as e:
        print(f"Parameter conversion error: {e}")
```

## Advanced Parameter Patterns

### Optional-like Behavior with Multiple Routes

```python
# Handle both with and without optional parameter
router.on("api/devices", DeviceController.list_all_devices)
router.on("api/devices/{device_type}", DeviceController.list_devices_by_type)

class DeviceController:
    async def list_all_devices(self, payload, client):
        # Handle request for all devices
        pass
    
    async def list_devices_by_type(self, device_type, payload, client):
        # Handle request filtered by device type
        pass
```

### Parameter-based Routing Logic

```python
async def handle_device_action(self, device_id, action, payload, client):
    """Route to different logic based on action parameter"""
    
    action_handlers = {
        'start': self.start_device,
        'stop': self.stop_device,
        'restart': self.restart_device,
        'configure': self.configure_device,
        'status': self.get_device_status
    }
    
    handler = action_handlers.get(action)
    if handler:
        await handler(device_id, payload, client)
    else:
        print(f"Unknown action: {action}")

async def start_device(self, device_id, payload, client):
    print(f"Starting device {device_id}")
    # Implementation...
```

## Real-world Examples

### IoT Device Management

```python
# Device lifecycle management
router.on("devices/{device_id}/lifecycle/{event}", DeviceController.handle_lifecycle)

async def handle_lifecycle(self, device_id, event, payload, client):
    events = {
        'registered': self.on_device_registered,
        'activated': self.on_device_activated,
        'deactivated': self.on_device_deactivated,
        'maintenance': self.on_device_maintenance
    }
    
    if event in events:
        await events[event](device_id, json.loads(payload))
```

### Multi-tenant Applications

```python
# Tenant isolation with parameters
router.on("tenants/{tenant_id}/users/{user_id}/actions/{action}", 
          UserController.handle_tenant_user_action)

async def handle_tenant_user_action(self, tenant_id, user_id, action, payload, client):
    # Verify tenant access
    if not await self.verify_tenant_access(tenant_id):
        return
    
    # Process user action within tenant context
    await self.process_user_action(tenant_id, user_id, action, payload)
```

### API Gateway Pattern

```python
# Service routing based on parameters
router.on("api/{version}/{service}/{endpoint}", ApiController.route_to_service)

async def route_to_service(self, version, service, endpoint, payload, client):
    # Validate API version
    if version not in ['v1', 'v2']:
        return await self.send_error("Unsupported API version")
    
    # Route to appropriate service
    service_router = self.get_service_router(service)
    if service_router:
        await service_router.handle(endpoint, payload, version)
```

## Error Handling

### Parameter Access Errors

```python
async def robust_handler(self, **kwargs):
    """Handle missing or unexpected parameters gracefully"""
    
    # Extract required parameters
    device_id = kwargs.get('device_id')
    if not device_id:
        print("Missing required device_id parameter")
        return
    
    # Extract optional parameters
    zone_id = kwargs.get('zone_id', 'default')
    
    # Get remaining parameters
    payload = kwargs.get('payload')
    client = kwargs.get('client')
    
    # Process with parameters
    await self.process_device_message(device_id, zone_id, payload)
```

## Best Practices

### Parameter Naming

- Use descriptive names: `{device_id}` not `{id}`
- Be consistent across routes: always `{user_id}`, not mixed with `{userId}`
- Use snake_case for multi-word parameters: `{sensor_type}`

### Parameter Validation

- Validate early in handlers or use middleware
- Provide clear error messages for invalid parameters
- Log parameter validation failures for debugging

### Performance Considerations

- Keep parameter extraction lightweight
- Cache converted parameters when doing expensive conversions
- Use parameter-based caching keys for frequently accessed data

## Next Steps

- [Route Groups](route-groups.md) - Organize routes with common prefixes
- [Middleware](../middleware/README.md) - Add parameter validation logic
- [Controllers](../controllers/README.md) - Build robust handler functions
