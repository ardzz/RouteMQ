# Sensor Data Collection

This example shows a small telemetry service: sensors publish MQTT messages, RouteMQ accepts them through a controller, and a Redis-backed queue worker handles storage or alerting work outside the MQTT path.

## Install

```bash
uvx --from "routemq[cli]" routemq new sensor-demo
cd sensor-demo
uv add "routemq[redis]"
```

You can use pip instead:

```bash
pip install "routemq[cli,redis]"
routemq new sensor-demo
cd sensor-demo
```

## Local services

Use Mosquitto for MQTT and Redis for the queue:

```yaml
# docker-compose.yml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

```bash
docker compose up -d
```

Configure RouteMQ:

```dotenv
MQTT_BROKER=localhost
MQTT_PORT=1883

ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
QUEUE_CONNECTION=redis
```

## Router

```python
# app/routers/sensors.py
from routemq.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()

router.on(
    "sensors/{device_id}/telemetry",
    SensorController.ingest,
    qos=1,
    shared=True,
    worker_count=3,
)
```

`shared=True` subscribes with `$share/<group>/sensors/+/telemetry`, so RouteMQ can spread high-volume sensor traffic across worker processes.

## Controller

```python
# app/controllers/sensor_controller.py
from routemq.controller import Controller
from routemq.queue import dispatch
from app.jobs.store_telemetry_job import StoreTelemetryJob


class SensorController(Controller):
    @staticmethod
    async def ingest(device_id, payload, client):
        job = StoreTelemetryJob()
        job.device_id = device_id
        job.payload = payload
        await dispatch(job)

        return {"accepted": True, "device_id": device_id}
```

The controller does the minimum work needed to acknowledge the message. The queue worker handles the slower part.

## Job

```python
# app/jobs/store_telemetry_job.py
from routemq.job import Job
from routemq.redis_manager import redis_manager


@Job.register
class StoreTelemetryJob(Job):
    queue = "telemetry"
    max_tries = 5
    retry_after = 5

    def __init__(self):
        super().__init__()
        self.device_id = None
        self.payload = {}

    async def handle(self):
        key = f"sensor:{self.device_id}:latest"
        await redis_manager.set_json(key, self.payload, ex=3600)

        temperature = self.payload.get("temperature")
        if temperature is not None and temperature >= 30:
            print(f"high temperature from {self.device_id}: {temperature}")
```

`@Job.register` matters. Workers reject unregistered jobs during deserialization unless you disable the allow-list for migration work.

## Run it

Start the app:

```bash
uv run routemq run
```

Start the queue worker in another terminal:

```bash
uv run routemq queue-work --queue telemetry --connection redis --sleep 1
```

Publish a reading:

```bash
mosquitto_pub -h localhost -t sensors/pump-7/telemetry -m '{"temperature":31.2,"rpm":1450}'
```

Check Redis:

```bash
redis-cli get sensor:pump-7:latest
```

## Where to go next

- Add validation middleware before dispatching jobs.
- Store long-term telemetry in ClickHouse with `routemq[clickhouse]`.
- Expose `/metrics` with `routemq[prometheus]` and `METRICS_HTTP_ENABLED=true`.
