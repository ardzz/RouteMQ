<img alt="logo.png" height="200" src="logo.png" width="200"/>

# RouteMQ Framework

A flexible MQTT routing framework with middleware support, dynamic router loading, and horizontal scaling capabilities, inspired by web frameworks.

## Features

- **Dynamic Router Loading**: Automatically discover and load routes from multiple files
- **Route-based MQTT topic handling**: Define routes using a clean, expressive syntax
- **Middleware support**: Process messages through middleware chains
- **Parameter extraction**: Extract variables from MQTT topics using Laravel-style syntax
- **Shared Subscriptions**: Horizontal scaling with worker processes for high-throughput routes
- **Optional MySQL integration**: Use with or without a database
- **Group-based routing**: Group routes with shared prefixes and middleware
- **Context manager for route groups**: Use Python's `with` statement for cleaner route definitions
- **Environment-based configuration**: Flexible configuration through .env files
- **Comprehensive logging**: Built-in logging with configurable levels

## Installation

Clone this repository:

```bash
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ
pip install -e .
```

## Quick Start

1. Initialize a new project:

```bash
python main.py --init
```

2. Edit the `.env` file with your MQTT broker details:

```env
# MQTT Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=your_username  # Optional
MQTT_PASSWORD=your_password  # Optional
MQTT_CLIENT_ID=mqtt-framework-main  # Optional
MQTT_GROUP_NAME=mqtt_framework_group  # For shared subscriptions

# Database Configuration (Optional)
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

3. Run the application:

```bash
python main.py --run
```

## Dynamic Router Loading

The framework automatically discovers and loads routes from multiple files in the `app/routers/` directory. This allows you to organize your routes by functionality or domain.

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

### Creating Router Files

Each router file should follow this pattern:

```python
# app/routers/devices.py
from core.router import Router
from app.controllers.device_controller import DeviceController
from app.middleware.logging_middleware import LoggingMiddleware

router = Router()

# Device control routes
with router.group(prefix="devices", middleware=[LoggingMiddleware()]) as devices:
    devices.on("control/{device_id}", DeviceController.handle_control, qos=1, shared=True, worker_count=2)
    devices.on("status/{device_id}", DeviceController.handle_status, qos=0)
    devices.on("config/{device_id}/update", DeviceController.handle_config, qos=1)
```

```python
# app/routers/sensors.py
from core.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()

# Sensor data routes
with router.group(prefix="sensors") as sensors:
    sensors.on("temperature/{sensor_id}", SensorController.handle_temperature, qos=1)
    sensors.on("humidity/{sensor_id}", SensorController.handle_humidity, qos=1)
    sensors.on("batch/{location_id}", SensorController.handle_batch, qos=2, shared=True, worker_count=3)
```

## Route Definition

### Basic Routes

```python
# Simple route
router.on("sensors/temperature", Controller.handle_temperature, qos=1)

# Route with parameters
router.on("devices/{device_id}/status", Controller.handle_device_status)

# Route with multiple parameters
router.on("locations/{location_id}/sensors/{sensor_id}/data", Controller.handle_sensor_data)
```

### Route Options

- **`qos`**: MQTT Quality of Service (0, 1, or 2)
- **`shared`**: Enable shared subscription for horizontal scaling
- **`worker_count`**: Number of worker processes for shared routes

```python
router.on("high-volume/{topic}", Controller.handle_bulk, 
          qos=2, shared=True, worker_count=5)
```

### Route Groups

Group routes with common prefixes and middleware:

```python
from app.middleware.auth import AuthMiddleware
from app.middleware.logging_middleware import LoggingMiddleware

# Group with prefix and middleware
with router.group(prefix="admin", middleware=[AuthMiddleware(), LoggingMiddleware()]) as admin:
    admin.on("devices/{device_id}/configure", AdminController.configure_device)
    admin.on("users/{user_id}/permissions", AdminController.manage_permissions)
    
    # Nested groups
    with admin.group(prefix="reports") as reports:
        reports.on("daily/{date}", AdminController.daily_report)
        reports.on("monthly/{month}", AdminController.monthly_report)
```

## Shared Subscriptions & Worker Processes

For high-throughput routes, enable shared subscriptions to distribute message processing across multiple worker processes:

```python
# This route will be handled by 3 worker processes
router.on("high-volume/data/{sensor_id}", Controller.handle_data, 
          qos=1, shared=True, worker_count=3)
```

**Benefits:**
- **Horizontal Scaling**: Distribute load across multiple processes
- **High Availability**: If one worker fails, others continue processing
- **Load Balancing**: MQTT broker distributes messages among workers

## Creating Controllers

Controllers handle the business logic for each route. Create your controllers in `app/controllers/`:

```python
from core.controller import Controller

class DeviceController(Controller):
    @staticmethod
    async def handle_control(device_id, payload, client):
        """Handle device control commands"""
        command = payload.get('command')
        
        # Log the command
        print(f"Controlling device {device_id}: {command}")
        
        # Process the command
        if command == 'restart':
            # Restart device logic
            result = await DeviceController.restart_device(device_id)
        elif command == 'shutdown':
            # Shutdown device logic
            result = await DeviceController.shutdown_device(device_id)
        else:
            result = {"error": "Unknown command"}
        
        # Publish response
        response_topic = f"devices/{device_id}/control/response"
        client.publish(response_topic, json.dumps(result))
        
        return result
    
    @staticmethod
    async def handle_status(device_id, payload, client):
        """Handle device status updates"""
        status = payload.get('status')
        timestamp = payload.get('timestamp', time.time())
        
        # Store status in database (if enabled)
        if hasattr(DeviceController, 'db_enabled') and DeviceController.db_enabled:
            from app.models.device_status import DeviceStatus
            status_record = DeviceStatus(
                device_id=device_id,
                status=status,
                timestamp=timestamp
            )
            await status_record.save()
        
        return {"status": "processed"}

class SensorController(Controller):
    @staticmethod
    async def handle_temperature(sensor_id, payload, client):
        """Handle temperature sensor data"""
        temperature = payload.get('value')
        unit = payload.get('unit', 'celsius')
        
        # Validate temperature range
        if unit == 'celsius' and (temperature < -50 or temperature > 100):
            print(f"Warning: Unusual temperature reading from {sensor_id}: {temperature}°C")
        
        # Store in database
        from app.models.sensor_reading import SensorReading
        reading = SensorReading(
            sensor_id=sensor_id,
            sensor_type='temperature',
            value=temperature,
            unit=unit,
            timestamp=time.time()
        )
        await reading.save()
        
        return {"status": "processed", "sensor_id": sensor_id}
```

## Creating Middleware

Middleware can process messages before they reach the handler. Create your middleware in `app/middleware/`:

```python
from core.middleware import Middleware
import time
import json

class LoggingMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Log incoming messages"""
        start_time = time.time()
        topic = context['topic']
        
        self.logger.info(f"Processing message on topic: {topic}")
        
        # Call the next handler in the chain
        result = await next_handler(context)
        
        # Log processing time
        processing_time = time.time() - start_time
        self.logger.info(f"Message processed in {processing_time:.3f}s")
        
        return result

class AuthMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Authenticate messages with API key"""
        payload = context['payload']
        
        # Check for API key
        api_key = payload.get('api_key')
        if not api_key:
            self.logger.warning(f"Missing API key for topic: {context['topic']}")
            return {"error": "API key required"}
        
        # Validate API key
        if not self.is_valid_api_key(api_key):
            self.logger.warning(f"Invalid API key: {api_key}")
            return {"error": "Invalid API key"}
        
        # Remove API key from payload before processing
        context['payload'] = {k: v for k, v in payload.items() if k != 'api_key'}
        
        return await next_handler(context)
    
    def is_valid_api_key(self, api_key: str) -> bool:
        """Validate API key (implement your logic here)"""
        valid_keys = ["your-secret-key", "another-valid-key"]
        return api_key in valid_keys

class RateLimitMiddleware(Middleware):
    def __init__(self):
        super().__init__()
        self.request_counts = {}
        self.window_size = 60  # 1 minute window
        self.max_requests = 100  # Max requests per window
    
    async def handle(self, context, next_handler):
        """Rate limit requests by topic"""
        topic = context['topic']
        current_time = time.time()
        
        # Clean old entries
        self.request_counts = {
            k: v for k, v in self.request_counts.items() 
            if current_time - v['first_request'] < self.window_size
        }
        
        # Check rate limit
        if topic not in self.request_counts:
            self.request_counts[topic] = {
                'count': 1,
                'first_request': current_time
            }
        else:
            self.request_counts[topic]['count'] += 1
            
            if self.request_counts[topic]['count'] > self.max_requests:
                self.logger.warning(f"Rate limit exceeded for topic: {topic}")
                return {"error": "Rate limit exceeded"}
        
        return await next_handler(context)
```

## Database Integration

### Configuration

Enable database support in your `.env` file:

```env
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password
```

### Creating Models

Create your models in `app/models/`:

```python
from sqlalchemy import Column, Integer, String, Float, DateTime
from core.model import Base
import time

class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(50), nullable=False)
    sensor_type = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(10))
    timestamp = Column(Float, nullable=False)
    
    def __repr__(self):
        return f"<SensorReading(sensor_id='{self.sensor_id}', value={self.value})>"

class DeviceStatus(Base):
    __tablename__ = "device_status"
    
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    timestamp = Column(Float, nullable=False)
    metadata = Column(String(500))  # JSON string for additional data
    
    def __repr__(self):
        return f"<DeviceStatus(device_id='{self.device_id}', status='{self.status}')>"
```

### Using Models in Controllers

```python
from app.models.sensor_reading import SensorReading

class SensorController(Controller):
    @staticmethod
    async def handle_temperature(sensor_id, payload, client):
        # Create new reading
        reading = SensorReading(
            sensor_id=sensor_id,
            sensor_type='temperature',
            value=payload['value'],
            unit=payload.get('unit', 'celsius'),
            timestamp=time.time()
        )
        
        # Save to database
        await reading.save()
        
        # Query recent readings
        recent_readings = await SensorReading.query().filter(
            SensorReading.sensor_id == sensor_id
        ).order_by(SensorReading.timestamp.desc()).limit(10).all()
        
        return {"status": "processed", "recent_count": len(recent_readings)}
```

## Testing

Run the test suite:

```bash
python run_tests.py
```

Create your own tests in the `tests/` directory:

```python
import unittest
from unittest.mock import Mock, AsyncMock
from app.controllers.sensor_controller import SensorController

class TestSensorController(unittest.TestCase):
    async def test_handle_temperature(self):
        # Mock client
        client = Mock()
        client.publish = Mock()
        
        # Test data
        sensor_id = "temp_001"
        payload = {"value": 25.5, "unit": "celsius"}
        
        # Call controller
        result = await SensorController.handle_temperature(sensor_id, payload, client)
        
        # Assertions
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["sensor_id"], sensor_id)
```

## Advanced Configuration

### Custom Router Directory

You can specify a custom router directory when initializing the application:

```python
from bootstrap.app import Application

# Use custom router directory
app = Application(router_directory="custom.routers")
app.connect()
app.run()
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | localhost | MQTT broker hostname |
| `MQTT_PORT` | 1883 | MQTT broker port |
| `MQTT_USERNAME` | None | MQTT username (optional) |
| `MQTT_PASSWORD` | None | MQTT password (optional) |
| `MQTT_CLIENT_ID` | mqtt-framework-main | MQTT client ID prefix |
| `MQTT_GROUP_NAME` | mqtt_framework_group | Shared subscription group name |
| `ENABLE_MYSQL` | true | Enable/disable MySQL integration |
| `DB_HOST` | localhost | Database hostname |
| `DB_PORT` | 3306 | Database port |
| `DB_NAME` | mqtt_framework | Database name |
| `DB_USER` | root | Database username |
| `DB_PASS` | (empty) | Database password |
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | %(asctime)s - %(name)s - %(levelname)s - %(message)s | Log message format |

## Docker Support

Run with Docker:

```bash
# Build the image
docker build -t routemq .

# Run with docker-compose
docker-compose up
```

The `docker-compose.yml` includes MQTT broker and MySQL database services.

## Performance Tips

1. **Use Shared Subscriptions**: For high-throughput topics, enable shared subscriptions with multiple workers
2. **Optimize QoS**: Use QoS 0 for non-critical messages, QoS 1 for important messages, QoS 2 only when necessary
3. **Database Connection Pooling**: Configure appropriate database connection pool sizes
4. **Middleware Ordering**: Place lightweight middleware before heavy ones
5. **Async Operations**: Use async/await for all I/O operations

## Troubleshooting

### Common Issues

1. **Routes not loading**: Check that router files have a `router` variable
2. **Worker processes not starting**: Ensure shared routes are properly configured
3. **Database connection issues**: Verify database credentials and network connectivity
4. **MQTT connection failed**: Check broker address, port, and credentials

### Debug Mode

Enable debug logging:

```env
LOG_LEVEL=DEBUG
```

This will show detailed information about route discovery, message processing, and worker management.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License
