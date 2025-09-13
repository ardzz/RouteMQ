# Controller API

Complete API reference for the RouteMQ Controller base class and controller development patterns.

## Controller Class

The `Controller` class is the base class that all application controllers should extend. It provides common functionality and logging capabilities for handling MQTT messages.

### Import

```python
from core.controller import Controller
```

### Constructor

```python
class MyController(Controller):
    pass
```

Controllers inherit from the base `Controller` class and implement static or instance methods to handle MQTT messages.

### Properties

#### logger

Class-level logger instance for all controllers.

**Type:** logging.Logger  
**Name:** "RouteMQ.Controller"

**Example:**
```python
class DeviceController(Controller):
    async def handle_status(self, device_id, payload, client):
        self.logger.info(f"Processing status for device {device_id}")
        # Handle the message...
```

## Controller Development Patterns

### Handler Method Signatures

Controller methods that handle MQTT messages should follow this signature pattern:

```python
@staticmethod
async def handler_name(param1, param2, ..., payload, client):
    """
    Args:
        param1, param2, etc.: Route parameters extracted from topic
        payload: Message payload (parsed JSON dict or raw string/bytes)
        client: MQTT client instance for publishing responses
    
    Returns:
        Any: Optional return value (typically for testing or chaining)
    """
    pass
```

### Static Methods (Recommended)

Static methods are the recommended approach for handlers as they don't require class instantiation:

```python
class DeviceController(Controller):
    @staticmethod
    async def handle_device_status(device_id, payload, client):
        """Handle device status updates."""
        Controller.logger.info(f"Device {device_id} status update")
        
        # Process the payload
        if isinstance(payload, dict):
            status = payload.get('status')
            timestamp = payload.get('timestamp')
        else:
            # Handle raw payload
            status = payload
            
        # Your business logic here
        await DeviceController._update_device_status(device_id, status)
        
        # Optional: publish response
        response_topic = f"devices/{device_id}/status/ack"
        client.publish(response_topic, '{"received": true}')
    
    @staticmethod
    async def _update_device_status(device_id: str, status: str):
        """Private helper method for database operations."""
        # Database update logic
        pass
```

### Instance Methods

Instance methods can be used when you need to maintain state or inject dependencies:

```python
class UserController(Controller):
    def __init__(self, user_service=None):
        self.user_service = user_service or UserService()
    
    async def handle_user_action(self, user_id, action, payload, client):
        """Handle user actions requiring service injection."""
        self.logger.info(f"User {user_id} performed action: {action}")
        
        # Use injected service
        user = await self.user_service.get_user(user_id)
        if user:
            await self.user_service.log_action(user_id, action, payload)
```

## Common Controller Patterns

### Parameter Validation

Always validate route parameters and payload data:

```python
class DeviceController(Controller):
    @staticmethod
    async def handle_device_command(device_id, command, payload, client):
        # Validate device ID format
        if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', device_id):
            Controller.logger.error(f"Invalid device ID format: {device_id}")
            return {"error": "Invalid device ID format"}
        
        # Validate command
        valid_commands = ['start', 'stop', 'restart', 'configure']
        if command not in valid_commands:
            Controller.logger.error(f"Invalid command: {command}")
            return {"error": f"Invalid command. Valid commands: {valid_commands}"}
        
        # Validate payload
        if not isinstance(payload, dict):
            Controller.logger.error("Payload must be a JSON object")
            return {"error": "Invalid payload format"}
        
        # Process valid command
        return await DeviceController._execute_command(device_id, command, payload)
```

### Error Handling

Implement robust error handling in your controllers:

```python
class SensorController(Controller):
    @staticmethod
    async def handle_sensor_data(sensor_id, data_type, payload, client):
        try:
            # Validate sensor exists
            sensor = await SensorController._get_sensor(sensor_id)
            if not sensor:
                raise ValueError(f"Sensor {sensor_id} not found")
            
            # Process sensor data
            result = await SensorController._process_sensor_data(
                sensor, data_type, payload
            )
            
            Controller.logger.info(f"Successfully processed {data_type} data for sensor {sensor_id}")
            return result
            
        except ValueError as e:
            Controller.logger.error(f"Validation error: {e}")
            return {"error": str(e)}
        except Exception as e:
            Controller.logger.error(f"Unexpected error processing sensor data: {e}")
            return {"error": "Internal server error"}
```

### Database Integration

Controllers can integrate with database models:

```python
from app.models.device import Device

class DeviceController(Controller):
    @staticmethod
    async def handle_device_registration(device_id, payload, client):
        """Register a new device."""
        try:
            # Validate payload
            required_fields = ['name', 'type', 'location']
            for field in required_fields:
                if field not in payload:
                    raise ValueError(f"Missing required field: {field}")
            
            # Create device record
            device = Device(
                device_id=device_id,
                name=payload['name'],
                device_type=payload['type'],
                location=payload['location'],
                status='active'
            )
            
            await device.save()
            
            Controller.logger.info(f"Device {device_id} registered successfully")
            
            # Publish confirmation
            response_topic = f"devices/{device_id}/registration/ack"
            client.publish(response_topic, '{"status": "registered"}')
            
            return {"device_id": device_id, "status": "registered"}
            
        except Exception as e:
            Controller.logger.error(f"Device registration failed: {e}")
            return {"error": str(e)}
```

### Redis Integration

Use Redis for caching and temporary data:

```python
from core.redis_manager import redis_manager

class CacheController(Controller):
    @staticmethod
    async def handle_cache_request(key, operation, payload, client):
        """Handle cache operations."""
        try:
            if operation == 'get':
                value = await redis_manager.get(key)
                return {"key": key, "value": value}
            
            elif operation == 'set':
                ttl = payload.get('ttl', 3600)  # Default 1 hour
                success = await redis_manager.set(key, payload['value'], ex=ttl)
                return {"key": key, "success": success}
            
            elif operation == 'delete':
                deleted = await redis_manager.delete(key)
                return {"key": key, "deleted": deleted > 0}
            
            else:
                raise ValueError(f"Unknown operation: {operation}")
                
        except Exception as e:
            Controller.logger.error(f"Cache operation failed: {e}")
            return {"error": str(e)}
```

### Response Publishing

Controllers can publish responses back to MQTT:

```python
class CommandController(Controller):
    @staticmethod
    async def handle_device_command(device_id, command, payload, client):
        """Execute device command and publish result."""
        try:
            # Execute command
            result = await CommandController._execute_device_command(
                device_id, command, payload
            )
            
            # Publish success response
            response_topic = f"devices/{device_id}/commands/{command}/result"
            response_payload = {
                "command": command,
                "status": "success",
                "result": result,
                "timestamp": time.time()
            }
            
            client.publish(response_topic, json.dumps(response_payload))
            
            Controller.logger.info(f"Command {command} executed successfully for device {device_id}")
            return response_payload
            
        except Exception as e:
            # Publish error response
            error_topic = f"devices/{device_id}/commands/{command}/error"
            error_payload = {
                "command": command,
                "status": "error",
                "error": str(e),
                "timestamp": time.time()
            }
            
            client.publish(error_topic, json.dumps(error_payload))
            
            Controller.logger.error(f"Command {command} failed for device {device_id}: {e}")
            return error_payload
```

## Controller Organization

### Single Responsibility

Each controller should handle a specific domain:

```python
# Device management
class DeviceController(Controller):
    @staticmethod
    async def handle_registration(device_id, payload, client): pass
    
    @staticmethod
    async def handle_status_update(device_id, payload, client): pass
    
    @staticmethod
    async def handle_configuration(device_id, payload, client): pass

# User management  
class UserController(Controller):
    @staticmethod
    async def handle_login(user_id, payload, client): pass
    
    @staticmethod
    async def handle_profile_update(user_id, payload, client): pass

# Analytics
class AnalyticsController(Controller):
    @staticmethod
    async def handle_event_tracking(event_type, payload, client): pass
    
    @staticmethod
    async def handle_metrics_collection(metric_name, payload, client): pass
```

### Method Naming Conventions

Use descriptive method names that indicate the action:

```python
class DeviceController(Controller):
    # Good naming
    @staticmethod
    async def handle_device_status_update(device_id, payload, client): pass
    
    @staticmethod
    async def handle_device_command_execution(device_id, command, payload, client): pass
    
    @staticmethod
    async def handle_device_configuration_change(device_id, payload, client): pass
    
    # Avoid generic names like:
    # async def handle(self, ...): pass
    # async def process(self, ...): pass
```

## Testing Controllers

### Unit Testing

Test controller methods independently:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.controllers.device_controller import DeviceController

@pytest.mark.asyncio
async def test_handle_device_status():
    # Mock client
    mock_client = MagicMock()
    
    # Test data
    device_id = "test_device_001"
    payload = {"status": "online", "battery": 85}
    
    # Call handler
    result = await DeviceController.handle_device_status(device_id, payload, mock_client)
    
    # Assertions
    assert result["device_id"] == device_id
    assert result["status"] == "online"
    mock_client.publish.assert_called_once()
```

### Integration Testing

Test with actual MQTT client and database:

```python
@pytest.mark.asyncio
async def test_device_registration_integration():
    # Setup test client and database
    client = await setup_test_mqtt_client()
    await setup_test_database()
    
    # Test device registration
    device_id = "integration_test_device"
    payload = {
        "name": "Test Device",
        "type": "sensor",
        "location": "test_lab"
    }
    
    result = await DeviceController.handle_device_registration(
        device_id, payload, client
    )
    
    # Verify device was created
    device = await Device.get(device_id=device_id)
    assert device is not None
    assert device.name == "Test Device"
```

## Best Practices

### 1. Keep Controllers Thin
Controllers should orchestrate, not implement business logic:

```python
# Good - thin controller
class OrderController(Controller):
    @staticmethod
    async def handle_order_creation(order_id, payload, client):
        order_service = OrderService()
        result = await order_service.create_order(order_id, payload)
        return result

# Avoid - fat controller with business logic
class OrderController(Controller):
    @staticmethod
    async def handle_order_creation(order_id, payload, client):
        # Lots of business logic here...
        # Database operations...
        # Validation logic...
        # Email sending...
        pass
```

### 2. Use Dependency Injection
Make controllers testable by injecting dependencies:

```python
class NotificationController(Controller):
    def __init__(self, email_service=None, sms_service=None):
        self.email_service = email_service or EmailService()
        self.sms_service = sms_service or SMSService()
    
    async def handle_notification(self, user_id, notification_type, payload, client):
        if notification_type == 'email':
            await self.email_service.send_email(user_id, payload)
        elif notification_type == 'sms':
            await self.sms_service.send_sms(user_id, payload)
```

### 3. Consistent Error Response Format
Use consistent error response formats across controllers:

```python
class BaseController(Controller):
    @staticmethod
    def error_response(message: str, code: str = None, details: dict = None):
        """Standard error response format."""
        return {
            "error": True,
            "message": message,
            "code": code,
            "details": details or {},
            "timestamp": time.time()
        }
    
    @staticmethod
    def success_response(data: Any = None, message: str = "Success"):
        """Standard success response format."""
        return {
            "success": True,
            "message": message,
            "data": data,
            "timestamp": time.time()
        }
```

### 4. Use Type Hints
Add type hints for better code documentation and IDE support:

```python
from typing import Dict, Any, Optional

class DeviceController(Controller):
    @staticmethod
    async def handle_device_update(
        device_id: str, 
        payload: Dict[str, Any], 
        client: Any
    ) -> Dict[str, Any]:
        """Update device with type hints."""
        # Implementation...
        return {"device_id": device_id, "updated": True}
```
