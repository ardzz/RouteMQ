# IoT Device Management

This guide demonstrates how to build a comprehensive IoT device management system using RouteMQ with MQTT.

## Overview

The IoT device management system handles:
- Device registration and authentication
- Real-time device monitoring
- Device control and configuration
- Data collection and storage
- Device status tracking

## Architecture

```
IoT Devices <-> MQTT Broker <-> RouteMQ <-> Redis/Database
```

## Device Router Setup

```python
# app/routers/iot_devices.py
from core.router import Router
from app.controllers.iot_controller import IoTController
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.validation import ValidationMiddleware

router = Router()

# Middleware setup
auth = AuthMiddleware()
rate_limit = RateLimitMiddleware(max_requests=1000, window_seconds=60)
validation = ValidationMiddleware()

# Device management routes
with router.group(prefix="iot/devices", middleware=[auth, rate_limit]) as devices:
    # Device lifecycle
    devices.on("register/{device_id}", IoTController.register_device, qos=1)
    devices.on("unregister/{device_id}", IoTController.unregister_device, qos=1)
    devices.on("heartbeat/{device_id}", IoTController.heartbeat, qos=0)
    
    # Device data
    devices.on("data/{device_id}/{sensor_type}", IoTController.receive_sensor_data, qos=1)
    devices.on("status/{device_id}", IoTController.update_status, qos=1)
    
    # Device control (high priority)
    devices.on("control/{device_id}/command", IoTController.send_command, qos=2, shared=True)
    devices.on("control/{device_id}/config", IoTController.update_config, qos=2)
    
    # Firmware updates
    devices.on("firmware/{device_id}/update", IoTController.firmware_update, qos=2)
```

## IoT Controller Implementation

```python
# app/controllers/iot_controller.py
from core.controller import Controller
from core.redis_manager import redis_manager
from app.models.device import Device
from app.models.device_parameter import DeviceParameter
import json
import time
import uuid
from typing import Dict, Any

class IoTController(Controller):
    
    @staticmethod
    async def register_device(device_id: str, payload: Dict[str, Any], client):
        """Register a new IoT device"""
        try:
            device_info = {
                "device_id": device_id,
                "name": payload.get("name"),
                "type": payload.get("type", "unknown"),
                "firmware_version": payload.get("firmware_version"),
                "hardware_version": payload.get("hardware_version"),
                "location": payload.get("location"),
                "capabilities": payload.get("capabilities", []),
                "registered_at": time.time(),
                "last_seen": time.time(),
                "status": "online"
            }
            
            # Validate required fields
            if not device_info["name"] or not device_info["type"]:
                raise ValueError("Device name and type are required")
            
            # Store in Redis for fast access
            await redis_manager.set_json(f"device:{device_id}", device_info, ex=86400)
            await redis_manager.set(f"device:{device_id}:status", "online", ex=300)
            
            # Store in database for persistence
            device = Device(
                device_id=device_id,
                name=device_info["name"],
                device_type=device_info["type"],
                firmware_version=device_info["firmware_version"],
                hardware_version=device_info["hardware_version"],
                location=device_info["location"],
                capabilities=json.dumps(device_info["capabilities"]),
                is_active=True
            )
            await device.save()
            
            # Generate authentication token
            auth_token = str(uuid.uuid4())
            await redis_manager.set(f"device:{device_id}:token", auth_token, ex=86400)
            
            # Publish registration confirmation
            response_topic = f"iot/devices/{device_id}/register/response"
            response = {
                "status": "registered",
                "device_id": device_id,
                "auth_token": auth_token,
                "timestamp": time.time(),
                "server_config": {
                    "heartbeat_interval": 60,
                    "data_reporting_interval": 300,
                    "max_retry_attempts": 3
                }
            }
            client.publish(response_topic, json.dumps(response))
            
            # Log registration
            print(f"Device {device_id} registered successfully")
            
            return {"status": "registered", "device_id": device_id}
            
        except Exception as e:
            # Publish error response
            error_topic = f"iot/devices/{device_id}/register/error"
            error_response = {
                "status": "error",
                "message": str(e),
                "timestamp": time.time()
            }
            client.publish(error_topic, json.dumps(error_response))
            raise
    
    @staticmethod
    async def heartbeat(device_id: str, payload: Dict[str, Any], client):
        """Handle device heartbeat"""
        timestamp = time.time()
        
        # Update last seen
        await redis_manager.set(f"device:{device_id}:last_seen", timestamp, ex=3600)
        await redis_manager.set(f"device:{device_id}:status", "online", ex=300)
        
        # Update device info if provided
        if payload:
            device_update = {
                "battery_level": payload.get("battery_level"),
                "signal_strength": payload.get("signal_strength"),
                "memory_usage": payload.get("memory_usage"),
                "cpu_usage": payload.get("cpu_usage")
            }
            
            # Filter out None values
            device_update = {k: v for k, v in device_update.items() if v is not None}
            
            if device_update:
                await redis_manager.set_json(f"device:{device_id}:metrics", device_update, ex=3600)
        
        return {"status": "heartbeat_received", "timestamp": timestamp}
    
    @staticmethod
    async def receive_sensor_data(device_id: str, sensor_type: str, payload: Dict[str, Any], client):
        """Receive and process sensor data"""
        timestamp = time.time()
        
        # Update last seen
        await redis_manager.set(f"device:{device_id}:last_seen", timestamp, ex=3600)
        
        # Validate sensor data
        if "value" not in payload:
            raise ValueError("Sensor value is required")
        
        # Store sensor data
        sensor_data = {
            "device_id": device_id,
            "sensor_type": sensor_type,
            "value": payload["value"],
            "unit": payload.get("unit"),
            "timestamp": payload.get("timestamp", timestamp),
            "quality": payload.get("quality", "good")
        }
        
        # Store in Redis for real-time access
        await redis_manager.set_json(f"sensor:{device_id}:{sensor_type}:latest", sensor_data, ex=3600)
        
        # Store in database for historical data
        parameter = DeviceParameter(
            device_id=device_id,
            parameter_name=sensor_type,
            value=sensor_data["value"],
            unit=sensor_data["unit"],
            timestamp=sensor_data["timestamp"]
        )
        await parameter.save()
        
        # Check for alerts
        await IoTController._check_sensor_alerts(device_id, sensor_type, sensor_data["value"])
        
        # Publish to analytics topic
        analytics_topic = f"analytics/sensor_data/{sensor_type}"
        client.publish(analytics_topic, json.dumps(sensor_data))
        
        return {"status": "data_received", "timestamp": timestamp}
    
    @staticmethod
    async def send_command(device_id: str, payload: Dict[str, Any], client):
        """Send command to device"""
        command_id = str(uuid.uuid4())
        command = payload.get("command")
        parameters = payload.get("parameters", {})
        
        if not command:
            raise ValueError("Command is required")
        
        # Store command for tracking
        command_data = {
            "command_id": command_id,
            "device_id": device_id,
            "command": command,
            "parameters": parameters,
            "timestamp": time.time(),
            "status": "sent"
        }
        
        await redis_manager.set_json(f"command:{command_id}", command_data, ex=3600)
        
        # Send command to device
        command_topic = f"iot/devices/{device_id}/commands/{command_id}"
        command_message = {
            "command_id": command_id,
            "command": command,
            "parameters": parameters,
            "timestamp": time.time()
        }
        
        client.publish(command_topic, json.dumps(command_message))
        
        return {"status": "command_sent", "command_id": command_id}
    
    @staticmethod
    async def update_config(device_id: str, payload: Dict[str, Any], client):
        """Update device configuration"""
        config_id = str(uuid.uuid4())
        config_updates = payload.get("config", {})
        
        if not config_updates:
            raise ValueError("Configuration updates are required")
        
        # Store configuration update
        config_data = {
            "config_id": config_id,
            "device_id": device_id,
            "updates": config_updates,
            "timestamp": time.time()
        }
        
        await redis_manager.set_json(f"config:{config_id}", config_data, ex=3600)
        
        # Send configuration to device
        config_topic = f"iot/devices/{device_id}/config/{config_id}"
        config_message = {
            "config_id": config_id,
            "updates": config_updates,
            "timestamp": time.time()
        }
        
        client.publish(config_topic, json.dumps(config_message))
        
        return {"status": "config_sent", "config_id": config_id}
    
    @staticmethod
    async def firmware_update(device_id: str, payload: Dict[str, Any], client):
        """Handle firmware update process"""
        update_id = str(uuid.uuid4())
        firmware_version = payload.get("version")
        firmware_url = payload.get("url")
        checksum = payload.get("checksum")
        
        if not all([firmware_version, firmware_url, checksum]):
            raise ValueError("Firmware version, URL, and checksum are required")
        
        # Store update information
        update_data = {
            "update_id": update_id,
            "device_id": device_id,
            "version": firmware_version,
            "url": firmware_url,
            "checksum": checksum,
            "timestamp": time.time(),
            "status": "initiated"
        }
        
        await redis_manager.set_json(f"firmware_update:{update_id}", update_data, ex=7200)
        
        # Send firmware update command
        update_topic = f"iot/devices/{device_id}/firmware/update/{update_id}"
        update_message = {
            "update_id": update_id,
            "version": firmware_version,
            "url": firmware_url,
            "checksum": checksum,
            "timestamp": time.time()
        }
        
        client.publish(update_topic, json.dumps(update_message))
        
        return {"status": "firmware_update_initiated", "update_id": update_id}
    
    @staticmethod
    async def unregister_device(device_id: str, payload: Dict[str, Any], client):
        """Unregister a device"""
        # Update device status
        await redis_manager.delete(f"device:{device_id}")
        await redis_manager.delete(f"device:{device_id}:status")
        await redis_manager.delete(f"device:{device_id}:token")
        
        # Update database
        device = await Device.find_by_device_id(device_id)
        if device:
            device.is_active = False
            await device.save()
        
        # Publish unregistration confirmation
        response_topic = f"iot/devices/{device_id}/unregister/response"
        response = {
            "status": "unregistered",
            "device_id": device_id,
            "timestamp": time.time()
        }
        client.publish(response_topic, json.dumps(response))
        
        return {"status": "unregistered", "device_id": device_id}
    
    @staticmethod
    async def _check_sensor_alerts(device_id: str, sensor_type: str, value: float):
        """Check if sensor value triggers any alerts"""
        # This would integrate with your alerting system
        # Example: check if temperature is too high
        if sensor_type == "temperature" and value > 80:
            alert_data = {
                "device_id": device_id,
                "sensor_type": sensor_type,
                "value": value,
                "threshold": 80,
                "severity": "high",
                "timestamp": time.time()
            }
            await redis_manager.lpush("alerts:high_priority", json.dumps(alert_data))
```

## Device Models

```python
# app/models/device.py (enhanced)
from core.model import Model
from sqlalchemy import Column, String, Boolean, DateTime, Text, Float
from sqlalchemy.sql import func
import json

class Device(Model):
    __tablename__ = "devices"
    
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    device_type = Column(String(100), nullable=False)
    firmware_version = Column(String(50))
    hardware_version = Column(String(50))
    location = Column(String(255))
    capabilities = Column(Text)  # JSON string
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    @classmethod
    async def find_by_device_id(cls, device_id: str):
        """Find device by device_id"""
        # Implementation depends on your database setup
        pass
    
    def get_capabilities(self):
        """Get device capabilities as list"""
        if self.capabilities:
            return json.loads(self.capabilities)
        return []
```

## Device Status Monitoring

```python
# app/middleware/device_monitor.py
from core.middleware import Middleware
from core.redis_manager import redis_manager
import time

class DeviceMonitorMiddleware(Middleware):
    async def handle(self, context, next_handler):
        device_id = context.get('path_params', {}).get('device_id')
        
        if device_id:
            # Check if device is registered
            device_info = await redis_manager.get_json(f"device:{device_id}")
            if not device_info:
                raise ValueError(f"Device {device_id} is not registered")
            
            # Check if device is online
            last_seen = await redis_manager.get(f"device:{device_id}:last_seen")
            if last_seen:
                time_since_last_seen = time.time() - float(last_seen)
                if time_since_last_seen > 600:  # 10 minutes
                    # Mark device as offline
                    await redis_manager.set(f"device:{device_id}:status", "offline", ex=3600)
        
        return await next_handler(context)
```

## Usage Examples

### Device Registration
```python
# Device sends registration message to: iot/devices/register/device_001
{
    "name": "Temperature Sensor 001",
    "type": "temperature_sensor",
    "firmware_version": "1.2.3",
    "hardware_version": "2.1",
    "location": "Building A, Room 101",
    "capabilities": ["temperature", "humidity", "battery_monitoring"]
}
```

### Sending Sensor Data
```python
# Device sends data to: iot/devices/data/device_001/temperature
{
    "value": 23.5,
    "unit": "celsius",
    "quality": "good",
    "timestamp": 1694678400
}
```

### Sending Commands
```python
# Server sends command to: iot/devices/control/device_001/command
{
    "command": "set_reporting_interval",
    "parameters": {
        "interval": 300
    }
}
```

## Best Practices

1. **Authentication**: Always validate device tokens before processing messages
2. **Rate Limiting**: Implement rate limiting to prevent device flooding
3. **Data Validation**: Validate all incoming sensor data
4. **Error Handling**: Provide clear error messages and recovery procedures
5. **Monitoring**: Track device health and connectivity status
6. **Security**: Use encrypted connections and secure authentication

## Integration with Monitoring Systems

```python
# app/services/device_monitoring.py
import asyncio
from core.redis_manager import redis_manager
import time

class DeviceMonitoringService:
    @staticmethod
    async def check_offline_devices():
        """Check for devices that have gone offline"""
        current_time = time.time()
        # Implementation to check device status
        pass
    
    @staticmethod
    async def generate_health_report():
        """Generate device health report"""
        # Implementation to generate reports
        pass

# Schedule monitoring tasks
async def start_monitoring():
    while True:
        await DeviceMonitoringService.check_offline_devices()
        await asyncio.sleep(60)  # Check every minute
```

This IoT device management system provides a robust foundation for managing IoT devices with real-time communication, monitoring, and control capabilities.
