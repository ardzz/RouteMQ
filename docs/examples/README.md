# Examples

Practical examples and use cases for RouteMQ applications.

## Topics

- [IoT Device Management](iot-devices.md) - Managing IoT devices with MQTT
- [Sensor Data Collection](sensor-data.md) - Collecting and processing sensor data
- [Real-time Notifications](notifications.md) - Push notifications and alerts
- [API Gateway](api-gateway.md) - Using RouteMQ as an API gateway
- [Chat Application](chat-app.md) - Building a real-time chat system

## Complete IoT Example

This example shows a complete IoT device management system:

### Device Router
```python
# app/routers/devices.py
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

router = Router()

auth = AuthMiddleware()
rate_limit = RateLimitMiddleware(max_requests=100, window_seconds=60)

with router.group(prefix="devices", middleware=[auth, rate_limit]) as devices:
    devices.on("register/{device_id}", DeviceController.register_device, qos=1)
    devices.on("heartbeat/{device_id}", DeviceController.heartbeat, qos=0)
    devices.on("data/{device_id}", DeviceController.receive_data, qos=1)
    devices.on("control/{device_id}", DeviceController.control_device, qos=2, shared=True)
```

### Device Controller
```python
# app/controllers/device_controller.py
from core.controller import Controller
from core.redis_manager import redis_manager
from app.models.device import Device
import json
import time

class DeviceController(Controller):
    @staticmethod
    async def register_device(device_id, payload, client):
        """Register a new device"""
        device_info = {
            "device_id": device_id,
            "name": payload.get("name"),
            "type": payload.get("type"),
            "firmware": payload.get("firmware"),
            "registered_at": time.time()
        }
        
        # Store in Redis for quick access
        await redis_manager.set_json(f"device:{device_id}", device_info, ex=86400)
        
        # Store in database for persistence
        device = Device(**device_info)
        await device.save()
        
        # Publish registration confirmation
        response_topic = f"devices/{device_id}/register/response"
        client.publish(response_topic, json.dumps({
            "status": "registered",
            "device_id": device_id,
            "timestamp": time.time()
        }))
        
        return {"status": "registered"}
    
    @staticmethod
    async def receive_data(device_id, payload, client):
        """Receive and process device data"""
        # Update last seen timestamp
        await redis_manager.set(f"device:{device_id}:last_seen", time.time(), ex=3600)
        
        # Process sensor data
        if "temperature" in payload:
            await DeviceController._process_temperature(device_id, payload["temperature"])
        
        if "humidity" in payload:
            await DeviceController._process_humidity(device_id, payload["humidity"])
        
        return {"status": "processed"}
```

## Sensor Data Pipeline

```python
# app/routers/sensors.py
from core.router import Router
from app.controllers.sensor_controller import SensorController
from app.middleware.validation import ValidationMiddleware

router = Router()

validation = ValidationMiddleware(schema="sensor_data.json")

with router.group(prefix="sensors", middleware=[validation]) as sensors:
    sensors.on("temperature/{sensor_id}", SensorController.handle_temperature, qos=1)
    sensors.on("batch/{location}", SensorController.handle_batch, qos=2, shared=True, worker_count=3)
```

## Real-time Chat System

```python
# app/routers/chat.py
from core.router import Router
from app.controllers.chat_controller import ChatController
from app.middleware.auth import AuthMiddleware

router = Router()

auth = AuthMiddleware()

with router.group(prefix="chat", middleware=[auth]) as chat:
    chat.on("message/{room_id}", ChatController.handle_message, qos=1)
    chat.on("join/{room_id}", ChatController.join_room, qos=1)
    chat.on("leave/{room_id}", ChatController.leave_room, qos=1)
```

## Performance Monitoring Example

```python
# app/middleware/performance.py
from core.middleware import Middleware
from core.redis_manager import redis_manager
import time

class PerformanceMiddleware(Middleware):
    async def handle(self, context, next_handler):
        start_time = time.time()
        topic = context['topic']
        
        # Track request count
        await redis_manager.incr(f"stats:requests:{topic}:count")
        await redis_manager.incr("stats:requests:total")
        
        # Execute handler
        result = await next_handler(context)
        
        # Track processing time
        processing_time = time.time() - start_time
        await redis_manager.set_json(f"stats:requests:{topic}:last_time", {
            "duration": processing_time,
            "timestamp": time.time()
        }, ex=3600)
        
        # Track slow requests
        if processing_time > 1.0:  # Over 1 second
            await redis_manager.incr(f"stats:slow_requests:{topic}")
        
        return result
```

## Next Steps

- [IoT Device Management](iot-devices.md) - Complete IoT example
- [Sensor Data Collection](sensor-data.md) - Data processing patterns
- [API Gateway](api-gateway.md) - Gateway implementation
