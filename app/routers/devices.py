from core.router import Router
from app.controllers.example_controller import ExampleController
from app.middleware.logging_middleware import LoggingMiddleware

router = Router()

# Device control routes
with router.group(prefix="devices", middleware=[LoggingMiddleware()]) as devices:
    devices.on("control/{device_id}", ExampleController.handle_message, qos=1, shared=True, worker_count=2)
    devices.on("status/{device_id}", ExampleController.handle_message, qos=0)
    devices.on("config/{device_id}/update", ExampleController.handle_message, qos=1, shared=True, worker_count=1)
