from app.controllers.example_controller import ExampleController
from app.middleware.example_middleware import LoggingMiddleware
from routemq.router import Router

router = Router()

# Define routes using the with syntax for better readability
with router.group(prefix='devices') as devices:
    # Apply logging middleware to this route
    devices.on('message/{device_id}', ExampleController.handle_message, middleware=[LoggingMiddleware()], qos=1)
