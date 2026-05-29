# Quick Start

This quickstart starts from the PyPI package, creates the normal `app/` layout, adds one controller and one router, then runs the MQTT app.

## 1. Install and scaffold

```bash
uvx --from "routemq[cli]" routemq new sensor-demo
cd sensor-demo
```

You can use pip instead:

```bash
pip install "routemq[cli]"
routemq new sensor-demo
cd sensor-demo
```

## 2. Add a controller and router

Create the controller:

```python
# app/controllers/device_controller.py
from routemq.controller import Controller

class DeviceController(Controller):
    @staticmethod
    async def status(device_id, payload, client):
        print(f"device {device_id}: {payload}")
        return {"ok": True}
```

Create the router:

```python
# app/routers/devices.py
from routemq.router import Router
from app.controllers.device_controller import DeviceController

router = Router()
router.on("devices/{device_id}/status", DeviceController.status, qos=1)
```

The app imports every `router` exported from `app/routers/*.py`.

## 3. Configure the broker

For a public smoke test:

```dotenv
MQTT_BROKER=test.mosquitto.org
MQTT_PORT=1883
ENABLE_MYSQL=false
ENABLE_REDIS=false
```

For local Mosquitto, set `MQTT_BROKER=localhost`.

## 4. Run and publish

```bash
uv run routemq run
```

In another terminal:

```bash
mosquitto_pub -h test.mosquitto.org -t devices/42/status -m '{"temp":21}'
```

You should see:

```text
device 42: {'temp': 21}
```

## 15-line version

These are the two files without comments:

```python
from routemq.controller import Controller
class DeviceController(Controller):
    @staticmethod
    async def status(device_id, payload, client):
        print(f"device {device_id}: {payload}")
        return {"ok": True}
from routemq.router import Router
from app.controllers.device_controller import DeviceController
router = Router()
router.on("devices/{device_id}/status", DeviceController.status, qos=1)
```

Run it with `uv run routemq run`, or `routemq run` when the package is installed in the active environment.

## Next steps

- [Your First Route](first-route.md) - Add parameters, middleware, and route groups.
- [Queue System](../queue/README.md) - Move slow work to background workers.
- [Sensor Data Collection](../examples/sensor-data.md) - Build a Redis-backed telemetry example.
