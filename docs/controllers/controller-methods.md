# Controller Methods

Controller methods are the handler functions that process MQTT messages. This guide covers different patterns and best practices for writing effective controller methods.

## Method Signatures

### Basic Handler Pattern

```python
@staticmethod
async def handler_name(payload, client):
    """Handle messages without route parameters"""
    # Process payload
    return result
```

### Single Parameter Handler

```python
@staticmethod
async def handler_name(param: str, payload, client):
    """Handle messages with one route parameter"""
    # Process with parameter
    return result
```

### Multiple Parameters Handler

```python
@staticmethod
async def handler_name(param1: str, param2: str, payload, client):
    """Handle messages with multiple route parameters"""
    # Process with multiple parameters
    return result
```

## Parameter Types

### Route Parameters

Route parameters are automatically extracted from the MQTT topic and passed to your handler:

```python
# Route: devices/{device_id}/sensors/{sensor_type}
@staticmethod
async def handle_sensor_data(device_id: str, sensor_type: str, payload, client):
    print(f"Device: {device_id}")      # e.g., "device123"
    print(f"Sensor: {sensor_type}")   # e.g., "temperature"
```

### Payload Parameter

The `payload` parameter contains the parsed message data:

```python
@staticmethod
async def handle_data(device_id: str, payload, client):
    # payload is a dict if message was valid JSON
    temperature = payload.get('temperature')
    humidity = payload.get('humidity')
    
    # payload is raw bytes/string if not JSON
    if isinstance(payload, str):
        # Handle raw string data
        pass
```

### Client Parameter

The `client` parameter is the MQTT client instance for publishing responses:

```python
@staticmethod
async def handle_command(device_id: str, payload, client):
    # Process command
    result = {"status": "completed"}
    
    # Publish response
    response_topic = f"devices/{device_id}/response"
    client.publish(response_topic, json.dumps(result))
```

## Handler Patterns

### Fire and Forget

Simple handlers that process messages without sending responses:

```python
from core.controller import Controller
import logging

class LoggingController(Controller):
    @staticmethod
    async def log_event(event_type: str, payload, client):
        """Log events without responding"""
        logging.info(f"Event {event_type}: {payload}")
        
        # No response needed
        return {"logged": True}
```

### Request-Response

Handlers that process requests and send responses:

```python
from core.controller import Controller
import json

class ApiController(Controller):
    @staticmethod
    async def handle_request(device_id: str, payload, client):
        """Process request and send response"""
        request_id = payload.get('request_id')
        
        # Process the request
        result = await ApiController.process_request(payload)
        
        # Send response
        response = {
            "request_id": request_id,
            "result": result,
            "timestamp": time.time()
        }
        
        response_topic = f"devices/{device_id}/response"
        client.publish(response_topic, json.dumps(response))
        
        return result
```

### Publish-Subscribe

Handlers that receive messages and broadcast to multiple topics:

```python
from core.controller import Controller
import json

class BroadcastController(Controller):
    @staticmethod
    async def handle_broadcast(channel: str, payload, client):
        """Receive and broadcast messages"""
        message = payload.get('message')
        sender = payload.get('sender')
        
        # Broadcast to all subscribers
        broadcast_message = {
            "channel": channel,
            "message": message,
            "sender": sender,
            "timestamp": time.time()
        }
        
        # Publish to multiple topics
        client.publish(f"broadcast/{channel}/all", json.dumps(broadcast_message))
        client.publish(f"notifications/{channel}", json.dumps(broadcast_message))
        
        return {"broadcast": True}
```

### State Management

Handlers that maintain state across messages:

```python
from core.controller import Controller
from core.redis_manager import redis_manager
import json

class StateController(Controller):
    @staticmethod
    async def update_state(device_id: str, payload, client):
        """Update and maintain device state"""
        new_state = payload.get('state')
        
        # Get current state
        state_key = f"device:{device_id}:state"
        current_state = await redis_manager.get_json(state_key) or {}
        
        # Update state
        current_state.update(new_state)
        
        # Save updated state
        await redis_manager.set_json(state_key, current_state, ex=3600)
        
        # Notify state change
        state_topic = f"devices/{device_id}/state"
        client.publish(state_topic, json.dumps(current_state))
        
        return current_state
```

## Advanced Patterns

### Batch Processing

Handle multiple items in a single message:

```python
from core.controller import Controller
import json
import asyncio

class BatchController(Controller):
    @staticmethod
    async def process_batch(payload, client):
        """Process multiple items in batch"""
        items = payload.get('items', [])
        
        # Process items concurrently
        tasks = [BatchController.process_item(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Send batch results
        response = {
            "processed": len(results),
            "results": results
        }
        
        client.publish("batch/results", json.dumps(response))
        return response
    
    @staticmethod
    async def process_item(item):
        """Process individual item"""
        # Simulate processing
        await asyncio.sleep(0.1)
        return {"id": item.get('id'), "processed": True}
```

### Pipeline Processing

Chain multiple processing steps:

```python
from core.controller import Controller
import json

class PipelineController(Controller):
    @staticmethod
    async def process_pipeline(device_id: str, payload, client):
        """Process data through multiple stages"""
        data = payload.get('data')
        
        # Stage 1: Validate
        validated_data = await PipelineController.validate_data(data)
        if not validated_data:
            return {"error": "Validation failed"}
        
        # Stage 2: Transform
        transformed_data = await PipelineController.transform_data(validated_data)
        
        # Stage 3: Enrich
        enriched_data = await PipelineController.enrich_data(transformed_data)
        
        # Stage 4: Store
        stored = await PipelineController.store_data(device_id, enriched_data)
        
        # Notify completion
        result_topic = f"devices/{device_id}/pipeline/complete"
        client.publish(result_topic, json.dumps({
            "status": "completed",
            "stages": ["validate", "transform", "enrich", "store"]
        }))
        
        return enriched_data
```

### Error Recovery

Handle errors and implement retry logic:

```python
from core.controller import Controller
import json
import asyncio
import logging

class ReliableController(Controller):
    @staticmethod
    async def reliable_process(device_id: str, payload, client):
        """Process with retry logic"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                result = await ReliableController.process_data(payload)
                
                # Success - send result
                response_topic = f"devices/{device_id}/success"
                client.publish(response_topic, json.dumps(result))
                
                return result
                
            except Exception as e:
                logging.warning(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    # Wait before retry
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                else:
                    # Final failure
                    error_topic = f"devices/{device_id}/error"
                    client.publish(error_topic, json.dumps({
                        "error": "Processing failed after retries",
                        "attempts": max_retries
                    }))
                    
                    return {"error": "Processing failed"}
```

## Method Organization

### Grouping Related Methods

Organize related functionality in the same controller:

```python
class DeviceController(Controller):
    # Device lifecycle methods
    @staticmethod
    async def handle_connect(device_id: str, payload, client):
        """Handle device connection"""
        pass
    
    @staticmethod
    async def handle_disconnect(device_id: str, payload, client):
        """Handle device disconnection"""
        pass
    
    # Device control methods
    @staticmethod
    async def handle_restart(device_id: str, payload, client):
        """Handle device restart command"""
        pass
    
    @staticmethod
    async def handle_shutdown(device_id: str, payload, client):
        """Handle device shutdown command"""
        pass
    
    # Helper methods (not handlers)
    @staticmethod
    async def get_device_status(device_id: str):
        """Get current device status"""
        pass
```

### Separation of Concerns

Keep controllers focused on specific domains:

```python
# Good: Focused controllers
class UserController(Controller):
    """Handle user-related operations"""
    pass

class DeviceController(Controller):
    """Handle device-related operations"""
    pass

class NotificationController(Controller):
    """Handle notification operations"""
    pass

# Avoid: Mixed responsibilities
class MegaController(Controller):
    """Handles everything - avoid this pattern"""
    pass
```

## Testing Controller Methods

Example test structure for controller methods:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.controllers.device_controller import DeviceController

@pytest.mark.asyncio
async def test_handle_control():
    # Arrange
    device_id = "test_device"
    payload = {"command": "restart"}
    client = MagicMock()
    
    # Act
    result = await DeviceController.handle_control(device_id, payload, client)
    
    # Assert
    assert result["status"] == "restarted"
    client.publish.assert_called_once()
```

## Next Steps

- [Using Redis in Controllers](redis-integration.md) - Add caching and state management
- [Database Operations](database-operations.md) - Work with database models
- [Best Practices](best-practices.md) - Follow controller organization guidelines
