<img alt="logo.png" height="200" src="logo.png" width="200"/>

# RouteMQ Framework

A flexible MQTT routing framework with middleware support, dynamic router loading, Redis integration, and horizontal scaling capabilities, inspired by web frameworks.

## Features

- **Dynamic Router Loading**: Automatically discover and load routes from multiple files
- **Route-based MQTT topic handling**: Define routes using a clean, expressive syntax
- **Middleware support**: Process messages through middleware chains
- **Parameter extraction**: Extract variables from MQTT topics using Laravel-style syntax
- **Shared Subscriptions**: Horizontal scaling with worker processes for high-throughput routes
- **Redis Integration**: Optional Redis support for distributed caching and rate limiting
- **Advanced Rate Limiting**: Multiple rate limiting strategies with Redis backend
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

# Redis Configuration (Optional)
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password  # Optional
REDIS_USERNAME=your_redis_username  # Optional
REDIS_MAX_CONNECTIONS=10
REDIS_SOCKET_TIMEOUT=5.0

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

## Redis Integration

RouteMQ includes optional Redis integration for distributed caching, session management, and advanced rate limiting.

### Configuration

Enable Redis in your `.env` file:

```env
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password  # Optional
REDIS_USERNAME=your_username  # Optional
REDIS_MAX_CONNECTIONS=10
```

### Using Redis in Controllers

```python
from core.redis_manager import redis_manager
from core.controller import Controller

class SensorController(Controller):
    @staticmethod
    async def handle_temperature(sensor_id, payload, client):
        # Cache sensor data in Redis
        cache_key = f"sensor:{sensor_id}:latest"
        await redis_manager.set_json(cache_key, payload, ex=3600)  # Cache for 1 hour
        
        # Get cached historical data
        history_key = f"sensor:{sensor_id}:history"
        history = await redis_manager.get_json(history_key) or []
        
        return {"status": "processed", "cached": True}
```

### Redis Operations

The Redis manager provides comprehensive async operations:

```python
from core.redis_manager import redis_manager

# Basic operations
await redis_manager.set("key", "value", ex=60)  # Set with expiration
value = await redis_manager.get("key")
await redis_manager.delete("key")

# JSON operations
await redis_manager.set_json("config", {"setting": "value"}, ex=3600)
config = await redis_manager.get_json("config")

# Hash operations
await redis_manager.hset("user:123", "name", "John")
name = await redis_manager.hget("user:123", "name")

# Counters
count = await redis_manager.incr("page_views")
await redis_manager.expire("page_views", 86400)
```

## Rate Limiting Middleware

RouteMQ includes advanced rate limiting middleware with multiple strategies and Redis backend support.

### Basic Rate Limiting

```python
from app.middleware.rate_limit import RateLimitMiddleware

# Basic rate limiting - 100 requests per minute
rate_limit = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window"
)

# Apply to routes
router.on("api/{endpoint}", Controller.handle, middleware=[rate_limit])
```

### Rate Limiting Strategies

#### 1. Sliding Window (Most Accurate)
```python
sliding_window = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window"  # Uses Redis sorted sets for precision
)
```

#### 2. Fixed Window (Simple)
```python
fixed_window = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="fixed_window"  # Resets at window boundaries
)
```

#### 3. Token Bucket (Allows Bursts)
```python
token_bucket = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="token_bucket",
    burst_allowance=50  # Allow up to 150 requests in bursts
)
```

### Topic-Specific Rate Limiting

```python
from app.middleware.rate_limit import TopicRateLimitMiddleware

topic_rate_limit = TopicRateLimitMiddleware(
    topic_limits={
        "sensors/batch/*": {"max_requests": 1000, "window_seconds": 60},
        "sensors/temperature/*": {"max_requests": 100, "window_seconds": 60},
        "devices/control/*": {"max_requests": 10, "window_seconds": 60},
    },
    default_limit={"max_requests": 50, "window_seconds": 60}
)
```

### Client-Based Rate Limiting

```python
from app.middleware.rate_limit import ClientRateLimitMiddleware

client_rate_limit = ClientRateLimitMiddleware(
    max_requests=50,
    window_seconds=60,
    client_id_field="client_id",  # Extract from payload
    strategy="sliding_window"
)
```

### Advanced Rate Limiting Features

```python
advanced_rate_limit = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window",
    whitelist=["admin/*", "emergency/*"],  # Bypass rate limiting
    custom_error_message="Too many requests. Please slow down.",
    fallback_enabled=True  # Use memory if Redis is down
)
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
- **`middleware`**: List of middleware to apply to this route

```python
router.on("high-volume/{topic}", Controller.handle_bulk, 
          qos=2, shared=True, worker_count=5, middleware=[rate_limit])
```

### Route Groups

Group routes with common prefixes and middleware:

```python
from app.middleware.auth import AuthMiddleware
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

# Group with prefix and middleware
auth_middleware = AuthMiddleware()
rate_limit = RateLimitMiddleware(max_requests=50, window_seconds=60)

with router.group(prefix="admin", middleware=[auth_middleware, LoggingMiddleware(), rate_limit]) as admin:
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
from core.redis_manager import redis_manager
import json
import time

class DeviceController(Controller):
    @staticmethod
    async def handle_control(device_id, payload, client):
        """Handle device control commands with Redis caching"""
        command = payload.get('command')
        
        # Check rate limiting info from middleware
        rate_limit_info = payload.get('rate_limit', {})
        remaining_requests = rate_limit_info.get('remaining', 0)
        
        # Log the command with rate limit info
        print(f"Controlling device {device_id}: {command} (Rate limit remaining: {remaining_requests})")
        
        # Cache command history in Redis
        history_key = f"device:{device_id}:commands"
        command_entry = {
            "command": command,
            "timestamp": time.time(),
            "remaining_rate_limit": remaining_requests
        }
        
        # Add to command history (keep last 100 commands)
        if redis_manager.is_enabled():
            history = await redis_manager.get_json(history_key) or []
            history.append(command_entry)
            if len(history) > 100:
                history = history[-100:]
            await redis_manager.set_json(history_key, history, ex=86400)  # 24 hours
        
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
    async def handle_status(device_id, payload, client):
        """Handle device status updates with Redis caching"""
        status = payload.get('status')
        timestamp = payload.get('timestamp', time.time())
        
        # Cache current status in Redis
        status_key = f"device:{device_id}:status"
        status_data = {
            "status": status,
            "timestamp": timestamp,
            "last_updated": time.time()
        }
        
        if redis_manager.is_enabled():
            await redis_manager.set_json(status_key, status_data, ex=3600)  # 1 hour
        
        # Store in database (if enabled)
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
        """Handle temperature sensor data with Redis caching and rate limiting"""
        temperature = payload.get('value')
        unit = payload.get('unit', 'celsius')
        
        # Check rate limiting from context
        context = payload.get('context', {})
        rate_limit_info = context.get('rate_limit', {})
        
        # Validate temperature range
        if unit == 'celsius' and (temperature < -50 or temperature > 100):
            print(f"Warning: Unusual temperature reading from {sensor_id}: {temperature}°C")
        
        # Cache latest reading in Redis
        if redis_manager.is_enabled():
            cache_key = f"sensor:{sensor_id}:latest"
            reading_data = {
                "value": temperature,
                "unit": unit,
                "timestamp": time.time(),
                "rate_limit_remaining": rate_limit_info.get('remaining', 0)
            }
            await redis_manager.set_json(cache_key, reading_data, ex=3600)
            
            # Update rolling average (last 10 readings)
            avg_key = f"sensor:{sensor_id}:avg"
            readings = await redis_manager.get_json(avg_key) or []
            readings.append(temperature)
            if len(readings) > 10:
                readings = readings[-10:]
            await redis_manager.set_json(avg_key, readings, ex=3600)
        
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
        
        return {
            "status": "processed", 
            "sensor_id": sensor_id,
            "rate_limit": rate_limit_info
        }
```

## Creating Middleware

Middleware can process messages before they reach the handler. Create your middleware in `app/middleware/`:

```python
from core.middleware import Middleware
from core.redis_manager import redis_manager
import time
import json

class LoggingMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Log incoming messages with Redis integration"""
        start_time = time.time()
        topic = context['topic']
        
        self.logger.info(f"Processing message on topic: {topic}")
        
        # Increment message counter in Redis
        if redis_manager.is_enabled():
            await redis_manager.incr(f"stats:messages:{topic}")
            await redis_manager.incr("stats:messages:total")
        
        # Call the next handler in the chain
        result = await next_handler(context)
        
        # Log processing time
        processing_time = time.time() - start_time
        self.logger.info(f"Message processed in {processing_time:.3f}s")
        
        # Store processing time stats in Redis
        if redis_manager.is_enabled():
            stats_key = f"stats:processing_time:{topic}"
            await redis_manager.set_json(stats_key, {
                "last_processing_time": processing_time,
                "timestamp": time.time()
            }, ex=3600)
        
        return result

class AuthMiddleware(Middleware):
    async def handle(self, context, next_handler):
        """Authenticate messages with API key using Redis for caching"""
        payload = context['payload']
        
        # Check for API key
        api_key = payload.get('api_key')
        if not api_key:
            self.logger.warning(f"Missing API key for topic: {context['topic']}")
            return {"error": "API key required"}
        
        # Check Redis cache for API key validation
        cache_key = f"auth:api_key:{api_key}"
        cached_result = None
        
        if redis_manager.is_enabled():
            cached_result = await redis_manager.get(cache_key)
        
        if cached_result == "valid":
            is_valid = True
        elif cached_result == "invalid":
            is_valid = False
        else:
            # Validate API key (not cached)
            is_valid = self.is_valid_api_key(api_key)
            
            # Cache the result
            if redis_manager.is_enabled():
                cache_value = "valid" if is_valid else "invalid"
                await redis_manager.set(cache_key, cache_value, ex=300)  # Cache for 5 minutes
        
        if not is_valid:
            self.logger.warning(f"Invalid API key: {api_key}")
            return {"error": "Invalid API key"}
        
        # Remove API key from payload before processing
        context['payload'] = {k: v for k, v in payload.items() if k != 'api_key'}
        
        return await next_handler(context)
    
    def is_valid_api_key(self, api_key: str) -> bool:
        """Validate API key (implement your logic here)"""
        valid_keys = ["your-secret-key", "another-valid-key"]
        return api_key in valid_keys

class CachingMiddleware(Middleware):
    """Cache handler results in Redis"""
    
    def __init__(self, cache_duration: int = 300):
        super().__init__()
        self.cache_duration = cache_duration
    
    async def handle(self, context, next_handler):
        """Cache handler results"""
        # Generate cache key from topic and payload
        cache_key = self._generate_cache_key(context)
        
        # Try to get cached result
        if redis_manager.is_enabled():
            cached_result = await redis_manager.get_json(cache_key)
            if cached_result:
                self.logger.debug(f"Cache hit for key: {cache_key}")
                return cached_result
        
        # Execute handler
        result = await next_handler(context)
        
        # Cache the result
        if redis_manager.is_enabled() and result:
            await redis_manager.set_json(cache_key, result, ex=self.cache_duration)
            self.logger.debug(f"Cached result for key: {cache_key}")
        
        return result
    
    def _generate_cache_key(self, context) -> str:
        """Generate cache key from context"""
        topic = context.get('topic', '')
        payload_hash = hash(str(context.get('payload', '')))
        return f"cache:handler:{topic}:{payload_hash}"
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
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
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
    metadata = Column(Text)  # JSON string for additional data
    
    def __repr__(self):
        return f"<DeviceStatus(device_id='{self.device_id}', status='{self.status}')>"

class RateLimitLog(Base):
    __tablename__ = "rate_limit_logs"
    
    id = Column(Integer, primary_key=True)
    key = Column(String(255), nullable=False)
    requests_count = Column(Integer, nullable=False)
    window_start = Column(Float, nullable=False)
    blocked = Column(Integer, default=0)
    timestamp = Column(Float, nullable=False)
```

## Testing

Run the test suite:

```bash
python run_tests.py
```

Create your own tests in the `tests/` directory:

```python
import unittest
from unittest.mock import Mock, AsyncMock, patch
from app.controllers.sensor_controller import SensorController
from app.middleware.rate_limit import RateLimitMiddleware

class TestSensorController(unittest.TestCase):
    async def test_handle_temperature(self):
        # Mock client and Redis
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

class TestRateLimitMiddleware(unittest.TestCase):
    async def test_rate_limiting(self):
        # Create rate limiter
        rate_limiter = RateLimitMiddleware(max_requests=2, window_seconds=60)
        
        # Mock context and handler
        context = {"topic": "test/topic", "payload": {}}
        next_handler = AsyncMock(return_value={"success": True})
        
        # First two requests should pass
        result1 = await rate_limiter.handle(context, next_handler)
        self.assertEqual(result1["success"], True)
        
        result2 = await rate_limiter.handle(context, next_handler)
        self.assertEqual(result2["success"], True)
        
        # Third request should be rate limited
        result3 = await rate_limiter.handle(context, next_handler)
        self.assertIn("rate_limit_exceeded", result3.get("error", ""))
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
| `ENABLE_REDIS` | false | Enable/disable Redis integration |
| `REDIS_HOST` | localhost | Redis hostname |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_DB` | 0 | Redis database number |
| `REDIS_PASSWORD` | None | Redis password (optional) |
| `REDIS_USERNAME` | None | Redis username (optional) |
| `REDIS_MAX_CONNECTIONS` | 10 | Redis connection pool size |
| `REDIS_SOCKET_TIMEOUT` | 5.0 | Redis socket timeout |
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | %(asctime)s - %(name)s - %(levelname)s - %(message)s | Log message format |

## Docker Support

Run with Docker:

```bash
# Build the image
docker build -t routemq .

# Run with docker-compose (includes MQTT broker, MySQL, and Redis)
docker-compose up
```

Example `docker-compose.yml`:

```yaml
version: '3.8'

services:
  routemq:
    build: .
    depends_on:
      - mqtt
      - mysql
      - redis
    environment:
      - MQTT_BROKER=mqtt
      - ENABLE_MYSQL=true
      - DB_HOST=mysql
      - ENABLE_REDIS=true
      - REDIS_HOST=redis
    volumes:
      - ./app:/app/app
      - ./.env:/app/.env

  mqtt:
    image: eclipse-mosquitto:2.0
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./docker/mosquitto.conf:/mosquitto/config/mosquitto.conf

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: mqtt_framework
    ports:
      - "3306:3306"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
```

## Performance Tips

1. **Use Redis for Caching**: Cache frequently accessed data to reduce database load
2. **Implement Rate Limiting**: Protect your application from excessive traffic
3. **Use Shared Subscriptions**: For high-throughput topics, enable shared subscriptions with multiple workers
4. **Optimize QoS**: Use QoS 0 for non-critical messages, QoS 1 for important messages, QoS 2 only when necessary
5. **Database Connection Pooling**: Configure appropriate database connection pool sizes
6. **Middleware Ordering**: Place lightweight middleware before heavy ones
7. **Async Operations**: Use async/await for all I/O operations
8. **Redis Connection Pooling**: Configure Redis connection pool based on your workload

## Monitoring and Metrics

### Redis-Based Metrics

```python
from core.redis_manager import redis_manager

class MetricsMiddleware(Middleware):
    async def handle(self, context, next_handler):
        topic = context['topic']
        
        # Track message counts
        await redis_manager.incr(f"metrics:messages:{topic}")
        await redis_manager.incr("metrics:messages:total")
        
        # Track processing time
        start_time = time.time()
        result = await next_handler(context)
        processing_time = time.time() - start_time
        
        # Store processing time metrics
        await redis_manager.set_json(f"metrics:processing_time:{topic}", {
            "last": processing_time,
            "timestamp": time.time()
        }, ex=3600)
        
        return result
```

### Health Check Endpoint

```python
from core.redis_manager import redis_manager

class HealthController(Controller):
    @staticmethod
    async def health_check(payload, client):
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "services": {}
        }
        
        # Check Redis
        if redis_manager.is_enabled():
            try:
                await redis_manager.set("health_check", "ok", ex=10)
                health_status["services"]["redis"] = "healthy"
            except:
                health_status["services"]["redis"] = "unhealthy"
                health_status["status"] = "degraded"
        
        return health_status
```

## Troubleshooting

### Common Issues

1. **Routes not loading**: Check that router files have a `router` variable
2. **Worker processes not starting**: Ensure shared routes are properly configured
3. **Database connection issues**: Verify database credentials and network connectivity
4. **MQTT connection failed**: Check broker address, port, and credentials
5. **Redis connection failed**: Verify Redis server is running and credentials are correct
6. **Rate limiting not working**: Ensure Redis is enabled or fallback mode is configured

### Debug Mode

Enable debug logging:

```env
LOG_LEVEL=DEBUG
```

This will show detailed information about:
- Route discovery and loading
- Message processing and middleware execution
- Worker management
- Redis operations and connection status
- Rate limiting decisions

### Performance Monitoring

Monitor your application performance:

```bash
# Check Redis statistics
redis-cli info stats

# Monitor MQTT broker
mosquitto_sub -h localhost -t '$SYS/#' -v

# Check application logs
tail -f logs/app.log
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License
