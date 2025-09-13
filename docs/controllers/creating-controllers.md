# Creating Controllers

Controllers in RouteMQ handle the business logic for processing MQTT messages. They extend the base `Controller` class and contain static async methods that process incoming messages.

## Basic Controller Structure

All controllers should extend the `Controller` base class:

```python
from core.controller import Controller

class DeviceController(Controller):
    @staticmethod
    async def handle_message(device_id: str, payload, client):
        """Handle incoming MQTT messages for devices"""
        # Your business logic here
        return {"status": "success"}
```

## Controller Requirements

### 1. Extend Controller Base Class

```python
from core.controller import Controller

class MyController(Controller):
    # Your controller methods here
```

### 2. Use Static Async Methods

All handler methods must be:
- Static methods (decorated with `@staticmethod`)
- Async functions (use `async def`)
- Accept the correct parameters based on your route

```python
@staticmethod
async def my_handler(param1: str, payload, client):
    # Process the message
    pass
```

### 3. Method Parameters

Controller methods receive parameters in this order:
1. **Route parameters** - Extracted from the MQTT topic pattern
2. **payload** - The parsed message payload (dict if JSON, raw if not)
3. **client** - The MQTT client instance for publishing responses

```python
# For route: devices/{device_id}/sensors/{sensor_type}
@staticmethod
async def handle_sensor_data(device_id: str, sensor_type: str, payload, client):
    print(f"Device: {device_id}, Sensor: {sensor_type}")
    print(f"Data: {payload}")
```

## Example Controllers

### Simple Message Handler

```python
from core.controller import Controller
import json

class SimpleController(Controller):
    @staticmethod
    async def handle_ping(payload, client):
        """Handle ping messages"""
        response = {"pong": True, "timestamp": payload.get("timestamp")}
        client.publish("system/pong", json.dumps(response))
        return response
```

### Device Control Controller

```python
from core.controller import Controller
import json
import time

class DeviceController(Controller):
    @staticmethod
    async def handle_control(device_id: str, payload, client):
        """Handle device control commands"""
        command = payload.get('command')
        
        print(f"Controlling device {device_id}: {command}")
        
        # Process the command
        if command == 'restart':
            result = await DeviceController.restart_device(device_id)
        elif command == 'shutdown':
            result = await DeviceController.shutdown_device(device_id)
        else:
            result = {"error": "Unknown command"}
        
        # Publish response
        response_topic = f"devices/{device_id}/control/response"
        client.publish(response_topic, json.dumps(result))
        
        return result
    
    @staticmethod
    async def restart_device(device_id: str):
        """Restart a specific device"""
        # Implement restart logic
        return {"status": "restarted", "device_id": device_id}
    
    @staticmethod
    async def shutdown_device(device_id: str):
        """Shutdown a specific device"""
        # Implement shutdown logic
        return {"status": "shutdown", "device_id": device_id}
```

## Controller Organization

### File Naming

- Use descriptive names: `device_controller.py`, `sensor_controller.py`
- Place controllers in the `app/controllers/` directory
- Use snake_case for file names

### Class Naming

- Use PascalCase for class names
- End with "Controller": `DeviceController`, `SensorController`
- Keep names descriptive and specific

### Method Naming

- Use descriptive method names: `handle_control`, `process_data`
- Use snake_case for method names
- Start with action verbs: `handle_`, `process_`, `validate_`

## Error Handling

Always include proper error handling in your controllers:

```python
from core.controller import Controller
import json
import logging

class SafeController(Controller):
    @staticmethod
    async def handle_data(device_id: str, payload, client):
        try:
            # Process the data
            result = await SafeController.process_device_data(device_id, payload)
            
            # Send success response
            response_topic = f"devices/{device_id}/response"
            client.publish(response_topic, json.dumps({
                "status": "success",
                "result": result
            }))
            
            return result
            
        except ValueError as e:
            error_msg = f"Invalid data for device {device_id}: {e}"
            logging.error(error_msg)
            
            # Send error response
            response_topic = f"devices/{device_id}/error"
            client.publish(response_topic, json.dumps({
                "status": "error",
                "message": str(e)
            }))
            
            return {"error": str(e)}
        
        except Exception as e:
            error_msg = f"Unexpected error for device {device_id}: {e}"
            logging.error(error_msg)
            
            # Send generic error response
            response_topic = f"devices/{device_id}/error"
            client.publish(response_topic, json.dumps({
                "status": "error",
                "message": "Internal server error"
            }))
            
            return {"error": "Internal server error"}
```

## Next Steps

- [Controller Methods](controller-methods.md) - Learn about different handler patterns
- [Using Redis in Controllers](redis-integration.md) - Add caching to your controllers
- [Database Operations](database-operations.md) - Work with database models
- [Best Practices](best-practices.md) - Follow controller organization guidelines
