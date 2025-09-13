# Your First Route

Learn how to create your first MQTT route in RouteMQ.

## Creating a Simple Route

### 1. Create a Router File

Create a new file `app/routers/my_first_router.py`:

```python
from core.router import Router
from core.controller import Controller

router = Router()

class MyController(Controller):
    @staticmethod
    async def handle_hello(name, payload, client):
        """Handle hello messages"""
        message = payload.get('message', 'Hello')
        response = f"{message}, {name}!"
        
        print(f"Received: {response}")
        return {"response": response, "status": "success"}

# Define your route
router.on("hello/{name}", MyController.handle_hello, qos=1)
```

### 2. Test Your Route

Start the application:

```bash
uv run python main.py --run
```

Publish a test message to your route using an MQTT client:

```bash
# Using mosquitto_pub (if installed)
mosquitto_pub -h localhost -t "hello/world" -m '{"message": "Hi there"}'
```

You should see the output: "Received: Hi there, world!"

## Route with Parameters

Routes can extract parameters from MQTT topics using `{parameter}` syntax:

```python
# Route: sensors/{sensor_id}/temperature
router.on("sensors/{sensor_id}/temperature", SensorController.handle_temperature)

# Route: devices/{device_id}/control/{action}
router.on("devices/{device_id}/control/{action}", DeviceController.handle_control)
```

## Adding Middleware

Add middleware to process messages before they reach your handler:

```python
from app.middleware.logging_middleware import LoggingMiddleware

# Route with middleware
router.on("api/{endpoint}", 
          ApiController.handle_request, 
          middleware=[LoggingMiddleware()])
```

## Route Groups

Organize related routes using groups:

```python
# Group routes with common prefix and middleware
with router.group(prefix="sensors", middleware=[LoggingMiddleware()]) as sensors:
    sensors.on("temperature/{sensor_id}", SensorController.handle_temperature)
    sensors.on("humidity/{sensor_id}", SensorController.handle_humidity)
    sensors.on("pressure/{sensor_id}", SensorController.handle_pressure)
```

## Next Steps

- [Routing Guide](../routing/README.md) - Learn advanced routing features
- [Controllers](../controllers/README.md) - Create sophisticated message handlers
- [Middleware](../middleware/README.md) - Add custom middleware
