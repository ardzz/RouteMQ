# Controller Best Practices

This guide covers best practices for organizing, writing, and maintaining controllers in RouteMQ applications.

## Controller Organization

### Directory Structure

Organize controllers by domain or functionality:

```
app/controllers/
├── __init__.py
├── device_controller.py      # Device management
├── sensor_controller.py      # Sensor data handling
├── user_controller.py        # User management
├── notification_controller.py # Notifications
└── analytics_controller.py   # Analytics and reporting
```

### Naming Conventions

#### Controller Classes
- Use PascalCase with "Controller" suffix
- Be specific about the domain: `DeviceController`, `SensorController`
- Avoid generic names: `DataController`, `MessageController`

```python
# Good
class DeviceController(Controller):
    pass

class SensorDataController(Controller):
    pass

# Avoid
class Controller1(Controller):
    pass

class GenericController(Controller):
    pass
```

#### Method Names
- Use descriptive action-based names
- Start with verbs: `handle_`, `process_`, `validate_`
- Include the operation: `handle_device_registration`, `process_sensor_data`

```python
# Good
@staticmethod
async def handle_device_registration(device_id: str, payload, client):
    pass

@staticmethod
async def process_temperature_reading(device_id: str, payload, client):
    pass

# Avoid
@staticmethod
async def method1(device_id: str, payload, client):
    pass

@staticmethod
async def handle(device_id: str, payload, client):
    pass
```

## Code Structure

### Single Responsibility Principle

Each controller should handle one domain:

```python
# Good: Focused on device operations
class DeviceController(Controller):
    @staticmethod
    async def handle_registration(device_id: str, payload, client):
        pass
    
    @staticmethod
    async def handle_status_update(device_id: str, payload, client):
        pass
    
    @staticmethod
    async def handle_configuration(device_id: str, payload, client):
        pass

# Avoid: Mixed responsibilities
class MegaController(Controller):
    @staticmethod
    async def handle_device_registration(device_id: str, payload, client):
        pass
    
    @staticmethod
    async def handle_user_login(user_id: str, payload, client):
        pass
    
    @staticmethod
    async def handle_sensor_data(device_id: str, payload, client):
        pass
```

### Method Organization

Group related methods and use helper methods:

```python
class DeviceController(Controller):
    # Public handler methods
    @staticmethod
    async def handle_device_registration(device_id: str, payload, client):
        """Handle device registration"""
        # Validate input
        validation_result = DeviceController.validate_registration_data(payload)
        if not validation_result['valid']:
            return {"error": validation_result['message']}
        
        # Register device
        result = await DeviceController.register_device(device_id, payload)
        
        # Send response
        await DeviceController.send_registration_response(device_id, result, client)
        
        return result
    
    # Helper methods (private-like, not handlers)
    @staticmethod
    def validate_registration_data(payload):
        """Validate registration payload"""
        if not payload.get('name'):
            return {'valid': False, 'message': 'Device name required'}
        
        if not payload.get('type'):
            return {'valid': False, 'message': 'Device type required'}
        
        return {'valid': True}
    
    @staticmethod
    async def register_device(device_id: str, payload):
        """Register device in database"""
        # Database operations
        pass
    
    @staticmethod
    async def send_registration_response(device_id: str, result, client):
        """Send registration response"""
        response_topic = f"devices/{device_id}/registration/response"
        client.publish(response_topic, json.dumps(result))
```

## Error Handling Best Practices

### Comprehensive Error Handling

Always handle different types of errors:

```python
from core.controller import Controller
import logging
import json

class RobustController(Controller):
    @staticmethod
    async def handle_sensor_data(device_id: str, sensor_type: str, payload, client):
        """Handle sensor data with comprehensive error handling"""
        try:
            # Validate input
            if not RobustController.validate_sensor_data(payload):
                error = {"error": "Invalid sensor data format"}
                await RobustController.send_error_response(device_id, error, client)
                return error
            
            # Process data
            result = await RobustController.process_sensor_data(device_id, sensor_type, payload)
            
            # Send success response
            await RobustController.send_success_response(device_id, result, client)
            
            return result
            
        except ValueError as e:
            # Handle validation errors
            error = {"error": f"Validation failed: {str(e)}"}
            logging.warning(f"Validation error for device {device_id}: {e}")
            await RobustController.send_error_response(device_id, error, client)
            return error
            
        except ConnectionError as e:
            # Handle external service errors
            error = {"error": "External service unavailable"}
            logging.error(f"Connection error for device {device_id}: {e}")
            await RobustController.send_error_response(device_id, error, client)
            return error
            
        except Exception as e:
            # Handle unexpected errors
            error = {"error": "Internal server error"}
            logging.error(f"Unexpected error for device {device_id}: {e}", exc_info=True)
            await RobustController.send_error_response(device_id, error, client)
            return error
    
    @staticmethod
    async def send_error_response(device_id: str, error, client):
        """Send standardized error response"""
        error_topic = f"devices/{device_id}/error"
        client.publish(error_topic, json.dumps(error))
    
    @staticmethod
    async def send_success_response(device_id: str, result, client):
        """Send standardized success response"""
        response_topic = f"devices/{device_id}/response"
        client.publish(response_topic, json.dumps(result))
```

### Error Response Standards

Use consistent error response formats:

```python
# Standardized error responses
def create_error_response(error_type: str, message: str, details=None):
    """Create standardized error response"""
    response = {
        "status": "error",
        "error_type": error_type,
        "message": message,
        "timestamp": time.time()
    }
    
    if details:
        response["details"] = details
    
    return response

# Usage in controllers
@staticmethod
async def handle_data(device_id: str, payload, client):
    try:
        # Process data
        pass
    except ValueError as e:
        error = create_error_response("validation_error", str(e))
        return error
    except Exception as e:
        error = create_error_response("internal_error", "Processing failed")
        return error
```

## Performance Best Practices

### Async Operations

Use async/await properly for I/O operations:

```python
class PerformantController(Controller):
    @staticmethod
    async def handle_multiple_operations(device_id: str, payload, client):
        """Handle multiple async operations efficiently"""
        
        # Good: Concurrent operations
        import asyncio
        
        # Start all operations concurrently
        cache_task = redis_manager.get_json(f"device:{device_id}:cache")
        db_task = DeviceModel.get_device_info(device_id)
        validation_task = PerformantController.validate_payload(payload)
        
        # Wait for all to complete
        cache_data, db_data, validation_result = await asyncio.gather(
            cache_task, db_task, validation_task, return_exceptions=True
        )
        
        # Process results
        return {"processed": True}
    
    @staticmethod
    async def validate_payload(payload):
        """Async validation (if needed)"""
        # Simulate async validation
        await asyncio.sleep(0.1)
        return True
```

### Database Session Management

Always manage database sessions properly:

```python
class DatabaseController(Controller):
    @staticmethod
    async def handle_with_proper_session_management(device_id: str, payload, client):
        """Proper database session management"""
        session = await DeviceModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            # All database operations within try block
            result = await DatabaseController.perform_db_operations(session, device_id, payload)
            await session.commit()
            return result
            
        except Exception as e:
            # Rollback on any error
            await session.rollback()
            logging.error(f"Database error: {e}")
            return {"error": "Database operation failed"}
            
        finally:
            # Always close session
            await session.close()
```

### Caching Strategies

Implement smart caching to reduce database load:

```python
class CachedController(Controller):
    @staticmethod
    async def handle_with_smart_caching(device_id: str, payload, client):
        """Implement multi-level caching"""
        cache_key = f"device:{device_id}:data"
        
        # Level 1: Try memory cache (if implemented)
        # Level 2: Try Redis cache
        cached_data = await redis_manager.get_json(cache_key)
        if cached_data:
            # Update cache hit metrics
            await redis_manager.incr(f"metrics:cache_hits:{device_id}")
            return cached_data
        
        # Level 3: Fetch from database
        session = await DeviceModel.get_session()
        if session:
            try:
                data = await CachedController.fetch_from_database(session, device_id)
                
                # Cache for future requests
                await redis_manager.set_json(cache_key, data, ex=300)  # 5 minutes
                
                # Update cache miss metrics
                await redis_manager.incr(f"metrics:cache_misses:{device_id}")
                
                return data
                
            finally:
                await session.close()
        
        return {"error": "Data not available"}
```

## Testing Best Practices

### Testable Controller Design

Design controllers to be easily testable:

```python
class TestableController(Controller):
    @staticmethod
    async def handle_data(device_id: str, payload, client):
        """Testable controller method"""
        # Separate validation
        validation_result = TestableController.validate_input(device_id, payload)
        if not validation_result['valid']:
            return {"error": validation_result['message']}
        
        # Separate processing
        processed_data = await TestableController.process_data(payload)
        
        # Separate response sending
        await TestableController.send_response(device_id, processed_data, client)
        
        return processed_data
    
    @staticmethod
    def validate_input(device_id: str, payload):
        """Pure function - easy to test"""
        if not device_id:
            return {'valid': False, 'message': 'Device ID required'}
        
        if not isinstance(payload, dict):
            return {'valid': False, 'message': 'Payload must be a dictionary'}
        
        return {'valid': True}
    
    @staticmethod
    async def process_data(payload):
        """Separate processing logic - can be mocked"""
        # Processing logic here
        return {"processed": payload}
    
    @staticmethod
    async def send_response(device_id: str, data, client):
        """Separate response sending - can be mocked"""
        response_topic = f"devices/{device_id}/response"
        client.publish(response_topic, json.dumps(data))
```

### Test Examples

```python
# test_controllers.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.controllers.testable_controller import TestableController

@pytest.mark.asyncio
async def test_handle_data_success():
    # Arrange
    device_id = "test_device"
    payload = {"temperature": 25.5}
    client = MagicMock()
    
    # Act
    result = await TestableController.handle_data(device_id, payload, client)
    
    # Assert
    assert result["processed"] == payload
    client.publish.assert_called_once()

def test_validate_input_valid():
    # Arrange
    device_id = "test_device"
    payload = {"temperature": 25.5}
    
    # Act
    result = TestableController.validate_input(device_id, payload)
    
    # Assert
    assert result['valid'] is True

def test_validate_input_invalid_device_id():
    # Arrange
    device_id = ""
    payload = {"temperature": 25.5}
    
    # Act
    result = TestableController.validate_input(device_id, payload)
    
    # Assert
    assert result['valid'] is False
    assert "Device ID required" in result['message']
```

## Security Best Practices

### Input Validation

Always validate and sanitize input:

```python
class SecureController(Controller):
    @staticmethod
    async def handle_secure_data(device_id: str, payload, client):
        """Handle data with security considerations"""
        
        # Validate device_id format
        if not SecureController.is_valid_device_id(device_id):
            return {"error": "Invalid device ID format"}
        
        # Validate payload structure
        if not SecureController.validate_payload_structure(payload):
            return {"error": "Invalid payload structure"}
        
        # Sanitize string inputs
        sanitized_payload = SecureController.sanitize_payload(payload)
        
        # Process with sanitized data
        result = await SecureController.process_secure_data(device_id, sanitized_payload)
        
        return result
    
    @staticmethod
    def is_valid_device_id(device_id: str) -> bool:
        """Validate device ID format"""
        import re
        # Allow alphanumeric, hyphens, underscores, max 255 chars
        pattern = r'^[a-zA-Z0-9_-]{1,255}$'
        return bool(re.match(pattern, device_id))
    
    @staticmethod
    def validate_payload_structure(payload) -> bool:
        """Validate payload structure"""
        if not isinstance(payload, dict):
            return False
        
        # Check for required fields
        required_fields = ['timestamp', 'data']
        return all(field in payload for field in required_fields)
    
    @staticmethod
    def sanitize_payload(payload):
        """Sanitize payload data"""
        import html
        
        sanitized = {}
        for key, value in payload.items():
            if isinstance(value, str):
                # Escape HTML and limit length
                sanitized[key] = html.escape(value)[:1000]
            elif isinstance(value, (int, float)):
                # Validate numeric ranges
                sanitized[key] = max(-1000000, min(1000000, value))
            else:
                sanitized[key] = value
        
        return sanitized
```

### Rate Limiting Integration

Implement rate limiting awareness:

```python
class RateLimitedController(Controller):
    @staticmethod
    async def handle_rate_limited_operation(device_id: str, payload, client):
        """Handle operations with rate limit awareness"""
        
        # Check rate limit info from middleware
        rate_limit_info = payload.get('rate_limit', {})
        remaining_requests = rate_limit_info.get('remaining', 0)
        
        # Adjust processing based on rate limit
        if remaining_requests < 5:
            # Low remaining requests - use cached data if available
            cached_data = await redis_manager.get_json(f"device:{device_id}:cached")
            if cached_data:
                return cached_data
        
        # Normal processing
        result = await RateLimitedController.process_data(device_id, payload)
        
        # Cache result for low rate limit situations
        await redis_manager.set_json(f"device:{device_id}:cached", result, ex=300)
        
        return result
```

## Documentation Best Practices

### Method Documentation

Use comprehensive docstrings:

```python
class WellDocumentedController(Controller):
    @staticmethod
    async def handle_sensor_calibration(device_id: str, sensor_type: str, payload, client):
        """
        Handle sensor calibration requests.
        
        This method processes calibration data for a specific sensor type on a device.
        It validates the calibration parameters, applies the calibration, and sends
        a confirmation response.
        
        Args:
            device_id (str): Unique identifier for the device (e.g., "sensor_001")
            sensor_type (str): Type of sensor to calibrate (e.g., "temperature", "humidity")
            payload (dict): Calibration data containing:
                - offset (float): Calibration offset value
                - scale (float): Calibration scale factor
                - reference_value (float): Reference measurement value
            client: MQTT client instance for publishing responses
        
        Returns:
            dict: Result dictionary containing:
                - calibrated (bool): Whether calibration was successful
                - offset (float): Applied offset value
                - scale (float): Applied scale factor
                - error (str): Error message if calibration failed
        
        Raises:
            ValueError: If calibration parameters are invalid
            ConnectionError: If device communication fails
        
        Example:
            payload = {
                "offset": 0.5,
                "scale": 1.02,
                "reference_value": 20.0
            }
            result = await handle_sensor_calibration("device_001", "temperature", payload, client)
        """
        try:
            # Implementation here
            pass
        except Exception as e:
            return {"error": str(e)}
```

## Monitoring and Logging

### Structured Logging

Use structured logging for better observability:

```python
import logging
import time

class MonitoredController(Controller):
    @staticmethod
    async def handle_monitored_operation(device_id: str, payload, client):
        """Handle operation with comprehensive monitoring"""
        start_time = time.time()
        operation_id = f"{device_id}_{int(start_time)}"
        
        # Log operation start
        logging.info("Operation started", extra={
            "operation_id": operation_id,
            "device_id": device_id,
            "operation": "monitored_operation",
            "payload_size": len(str(payload))
        })
        
        try:
            # Process operation
            result = await MonitoredController.process_operation(device_id, payload)
            
            # Log success
            duration = time.time() - start_time
            logging.info("Operation completed successfully", extra={
                "operation_id": operation_id,
                "device_id": device_id,
                "duration_ms": duration * 1000,
                "result_size": len(str(result))
            })
            
            # Update metrics
            await redis_manager.incr(f"metrics:operations:success:{device_id}")
            
            return result
            
        except Exception as e:
            # Log error
            duration = time.time() - start_time
            logging.error("Operation failed", extra={
                "operation_id": operation_id,
                "device_id": device_id,
                "duration_ms": duration * 1000,
                "error": str(e)
            }, exc_info=True)
            
            # Update error metrics
            await redis_manager.incr(f"metrics:operations:error:{device_id}")
            
            return {"error": "Operation failed"}
```

These best practices will help you build maintainable, performant, and secure controllers for your RouteMQ applications. Always consider the specific requirements of your use case and adapt these practices accordingly.
