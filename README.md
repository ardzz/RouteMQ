<p align="center">
  <img alt="RouteMQ" src="logo.png" width="200" height="200">
</p>

<h1 align="center">RouteMQ</h1>

<p align="center">
  <em>Laravel-style MQTT routing for Python: controllers, middleware, jobs, and shared-subscription scaling without callback spaghetti.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/routemq/"><img alt="PyPI" src="https://img.shields.io/pypi/v/routemq.svg"></a>
  <a href="https://pypi.org/project/routemq/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/routemq.svg"></a>
  <a href="https://github.com/ardzz/RouteMQ/blob/master/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/ardzz/RouteMQ"><img alt="OpenSSF Scorecard" src="https://api.scorecard.dev/projects/github.com/ardzz/RouteMQ/badge"></a>
  <img alt="Status: Beta" src="https://img.shields.io/badge/status-beta-orange.svg">
</p>

> **Status: Beta.** Use RouteMQ in test/staging while we harden the v1 surface. The framework is fully tested (581 unit tests) and supply-chain hardened, but APIs may shift before 1.0.

---

**Documentation:** [docs/](./docs) · **Source:** [github.com/ardzz/RouteMQ](https://github.com/ardzz/RouteMQ) · **PyPI:** [routemq](https://pypi.org/project/routemq/)

RouteMQ is a Python 3.12+ MQTT application framework that turns topics into async controller methods through middleware chains, with optional background jobs and shared-subscription workers.

RouteMQ gives you:

- **Route topics like web routes.** Declare `devices/{id}/status` once; receive `id` as a typed handler argument.
- **Controllers and middleware.** Keep handlers in `app/controllers`; layer auth, logging, rate limiting, and validation as reusable middleware.
- **Async by default.** Use async Redis, SQLAlchemy for MySQL or PostgreSQL, telemetry adapters, and job dispatch naturally inside handlers. RouteMQ bridges `paho-mqtt`'s sync callbacks for you.
- **Shared-subscription scaling.** Flip `shared=True` on a high-volume route; RouteMQ spawns worker processes against `$share/<group>/<topic>` without you wiring multiple clients.
- **Background jobs.** Laravel-style `Job` classes with retries, delays, timeouts, and Redis or database-backed queue backends.
- **Built-in observability.** Optional `/health`, `/ready`, and `/metrics` HTTP endpoints, lifecycle counters, latency histograms, and OpenTelemetry-shaped spans. No mandatory vendor backend.
- **Optional integrations.** Redis, PostgreSQL, ClickHouse telemetry, and a Prometheus client adapter. MySQL support ships with the base runtime.
- **Supply-chain hardened.** OpenSSF Scorecard, SLSA L3 provenance, signed CycloneDX SBOMs, Bandit, pip-audit, and Dependabot on every release.

## Quick Start

Install the mode you need:

| Install | Use it for |
|---|---|
| `routemq` | Runtime engine: routing, middleware, jobs, MySQL database queue, app boot. |
| `routemq[cli]` | Runtime plus the `routemq new` scaffolder. Start here for a new project. |
| `routemq[redis]` | Runtime plus Redis support for queues, cache, rate limits, and shared state. |
| `routemq[all]` | CLI, Redis, PostgreSQL, Prometheus, and ClickHouse extras in one install. |

```bash
uv add "routemq[cli]"          # add to an existing uv project
pip install "routemq[cli]"     # install into the active Python environment
```

Create a project and one route:

```bash
uvx --from "routemq[cli]" routemq new sensor-demo
# or, after pip install "routemq[cli]": routemq new sensor-demo
cd sensor-demo
```

```python
# app/controllers/device_controller.py
from routemq.controller import Controller

class DeviceController(Controller):
    @staticmethod
    async def status(device_id, payload, client):
        print(f"device {device_id}: {payload}")
        return {"ok": True}

# app/routers/devices.py
from routemq.router import Router
from app.controllers.device_controller import DeviceController

router = Router()
router.on("devices/{device_id}/status", DeviceController.status, qos=1)
```

Point `.env` at a broker and run the app:

```dotenv
MQTT_BROKER=test.mosquitto.org
MQTT_PORT=1883
```

```bash
uv run routemq run
mosquitto_pub -h test.mosquitto.org -t devices/42/status -m '{"temp":21}'
```

RouteMQ imports `app.routers.*`, subscribes to `devices/+/status`, and calls `DeviceController.status(device_id="42", payload={"temp": 21}, ...)`.

## When should I use RouteMQ?

| If you need... | Use |
|---|---|
| Low-level MQTT protocol control, custom session/QoS handling | [`paho-mqtt`](https://github.com/eclipse-paho/paho.mqtt.python) |
| **A web-framework-style structure for an MQTT-first app** | **RouteMQ** |
| Multi-broker streaming across Kafka, RabbitMQ, NATS, Redis, MQTT | [FastStream](https://github.com/ag2ai/faststream) |
| General distributed task queues independent of a broker protocol | [Celery](https://github.com/celery/celery) |

RouteMQ sits on top of `paho-mqtt`. You keep proven protocol behavior and add structure, async handlers, and scaling.

## Routes, middleware, and scaling in one snippet

The minimal example above scales up cleanly:

```python
from routemq.router import Router
from app.middleware.rate_limit import RateLimit
from app.controllers.device_controller import DeviceController

router = Router()

with router.group(prefix="devices", middleware=[RateLimit(60)]) as devices:
    devices.on(
        "{device_id}/status",
        DeviceController.handle_status,
        qos=1,
        shared=True,
        worker_count=3,
    )
```

- The `{device_id}` token compiles to a regex with a named group and to a `+` wildcard for the MQTT subscription.
- `shared=True` switches the subscription to `$share/<group>/devices/+/status` and spawns three worker processes.
- `RateLimit(60)` runs as middleware before the handler. Auth, logging, and validation work the same way.

## Background jobs

Push slow work out of the MQTT handler. Register concrete jobs so workers can deserialize them safely:

```python
# app/jobs/send_alert_job.py
from routemq.job import Job


@Job.register
class SendAlertJob(Job):
    queue = "alerts"
    max_tries = 3
    retry_after = 10

    def __init__(self):
        super().__init__()
        self.device_id = None
        self.payload = {}

    async def handle(self):
        print(f"alert for {self.device_id}: {self.payload}")
```

Dispatch the job from a controller or handler:

```python
from routemq.queue import dispatch
from app.jobs.send_alert_job import SendAlertJob


async def handler(device_id, payload, client):
    if payload.get("status") == "critical":
        job = SendAlertJob()
        job.device_id = device_id
        job.payload = payload
        await dispatch(job)
    return {"ok": True}
```

Run a worker:

```bash
routemq queue-work --queue alerts --connection redis
```

Queue backends: Redis with `routemq[redis]`, or MySQL with base `routemq` when `ENABLE_MYSQL=true`.

## Real-world sensor telemetry

A sensor pipeline usually has three parts: MQTT routing, queued processing, and a local stack with a broker plus Redis.

```python
# app/routers/sensors.py
from routemq.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()
router.on("sensors/{device_id}/telemetry", SensorController.ingest, qos=1)
```

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

```python
# app/jobs/store_telemetry_job.py
from routemq.job import Job


@Job.register
class StoreTelemetryJob(Job):
    queue = "telemetry"
    max_tries = 5

    def __init__(self):
        super().__init__()
        self.device_id = None
        self.payload = {}

    async def handle(self):
        temperature = self.payload.get("temperature")
        print(f"store {self.device_id}: temperature={temperature}")
```

Run it against a local broker and Redis queue:

```yaml
# docker-compose.yml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports: ["1883:1883"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

```dotenv
MQTT_BROKER=localhost
MQTT_PORT=1883
ENABLE_REDIS=true
QUEUE_CONNECTION=redis
```

```bash
docker compose up -d
uv run routemq run
uv run routemq queue-work --queue telemetry --connection redis
mosquitto_pub -h localhost -t sensors/pump-7/telemetry -m '{"temperature":31.2}'
```

## Observability

RouteMQ ships health, readiness, and OpenMetrics endpoints, off by default. Set `METRICS_HTTP_ENABLED=true` to expose them:

```bash
curl http://localhost:8080/health     # liveness
curl http://localhost:8080/ready      # MQTT readiness
curl http://localhost:8080/metrics    # OpenMetrics / Prometheus text
```

Built-in metric families include `mqtt_messages_*`, `router_dispatch_*`, `queue_job_*`, queue-depth gauges, `telemetry_*`, legacy `tsdb_write_*`, and latency histograms. Spans follow OpenTelemetry-shaped semantics (`db.system`, `db.operation`, `messaging.system`, `kind=client|consumer|producer|internal`).

For details: [Metrics](./docs/monitoring/metrics.md) · [Health checks](./docs/monitoring/health-checks.md) · [Pool tuning evidence](./docs/monitoring/pool-tuning.md)

## Optional extras

```bash
uv add routemq                 # base runtime
uv add "routemq[cli]"          # scaffolder and rich terminal prompts
uv add "routemq[redis]"        # Redis queue + rate limiting backend
uv add "routemq[postgres]"     # PostgreSQL async driver
uv add "routemq[clickhouse]"   # ClickHouse telemetry adapter
uv add "routemq[prometheus]"   # multiprocess-safe Prometheus client adapter
uv add "routemq[all]"          # everything above plus CLI

# pip works too:
pip install routemq
pip install "routemq[cli]"
pip install "routemq[redis]"
pip install "routemq[all]"
```

## Docker

The scaffolder can drop a `docker-compose.yml` with Redis, MySQL, the app, and queue workers:

```bash
uvx --from "routemq[cli]" routemq new my-app --with-docker --with-redis --with-mysql --with-queue
cd my-app
docker compose up -d
docker compose up -d --scale queue-worker-default=5
```

For a local MQTT broker, add Mosquitto to the same compose file:

```yaml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
```

Then set `MQTT_BROKER=mosquitto` for containers, or `MQTT_BROKER=localhost` when running RouteMQ on your host.

## Documentation

- **[Getting Started](./docs/getting-started/README.md)**, installation, first route, environment
- **[Architecture](./docs/architecture.md)**, message flow diagram and runtime components
- **[Configuration](./docs/configuration/README.md)**, every environment variable, with defaults
- **[Routing](./docs/routing/README.md)** · **[Controllers](./docs/controllers/README.md)** · **[Middleware](./docs/middleware/README.md)**
- **[Queue System](./docs/queue/README.md)**, jobs, workers, drivers
- **[Rate Limiting](./docs/rate-limiting/README.md)**, strategies and Redis backend
- **[Redis](./docs/redis/README.md)** · **[Database](./docs/database/README.md)** · **[Telemetry / TSDB](./docs/tsdb/README.md)**
- **[Monitoring](./docs/monitoring/README.md)**, metrics, health, traces
- **[Docker Deployment](./docs/docker-deployment.md)** · **[Testing](./docs/testing/README.md)**
- **[Examples](./docs/examples/README.md)** · **[API Reference](./docs/api-reference/README.md)** · **[FAQ](./docs/faq.md)**
- **[Release Conformance](./docs/release-conformance.md)**, SLSA, Scorecard, SBOM, SemVer

## Project Health

- **[Security Policy](./SECURITY.md)**, private vulnerability reporting and supported versions
- **[Contributing](./CONTRIBUTING.md)**, issues, PRs, tests, coding standards
- **[Code of Conduct](./CODE_OF_CONDUCT.md)**
- **[Changelog](./CHANGELOG.md)**
- **[Issue Tracker](https://github.com/ardzz/RouteMQ/issues)**

## Hacking on the framework

```bash
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ
uv sync --all-extras --dev
uv run python run_tests.py     # 581 tests, ~3 seconds
```

See [TEMPLATE.md](./TEMPLATE.md) if you want to fork the framework rather than depend on the published wheel.

## License

MIT, see [LICENSE](./LICENSE).
