<p align="center">
  <img alt="RouteMQ" src="logo.png" width="200" height="200">
</p>

<h1 align="center">RouteMQ</h1>

<p align="center">
  <em>Laravel-style MQTT routing for Python — controllers, middleware, jobs, and shared-subscription scaling, without the callback spaghetti.</em>
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

The key features are:

- **Route topics like web routes.** Declare `devices/{id}/status` once; receive `id` as a typed handler argument.
- **Controllers and middleware.** Keep handlers in `app/controllers`; layer auth, logging, rate limiting, and validation as reusable middleware.
- **Async by default.** Use async Redis, MySQL (SQLAlchemy), ClickHouse, and job dispatch naturally inside handlers — RouteMQ bridges `paho-mqtt`'s sync callbacks for you.
- **Shared-subscription scaling.** Flip `shared=True` on a high-volume route; RouteMQ spawns worker processes against `$share/<group>/<topic>` without you wiring multiple clients.
- **Background jobs.** Laravel-style `Job` classes with retries, delays, timeouts, and Redis or MySQL queue backends.
- **Built-in observability.** Optional `/health`, `/ready`, and `/metrics` HTTP endpoints, lifecycle counters, latency histograms, and OpenTelemetry-shaped spans — no mandatory vendor backend.
- **Optional integrations.** Redis, MySQL, ClickHouse for time-series telemetry, and a Prometheus client adapter — all opt-in extras.
- **Supply-chain hardened.** OpenSSF Scorecard, SLSA L3 provenance, signed CycloneDX SBOMs, Bandit, pip-audit, and Dependabot on every release.

## Quick Start

Install with [uv](https://docs.astral.sh/uv/) (recommended) or pip:

```bash
uv add "routemq[cli]"          # uv-managed project
# or
pip install "routemq[cli]"     # classic pip
```

Create `app.py`:

```python
from routemq.router import Router

router = Router()


async def device_status(device_id, payload, client):
    print(f"device {device_id} reported {payload}")
    return {"ok": True, "device_id": device_id}


router.on("devices/{device_id}/status", device_status, qos=1)
```

Configure broker connection in `.env`:

```dotenv
MQTT_BROKER=test.mosquitto.org
MQTT_PORT=1883
```

Run:

```bash
routemq run
```

Publish from anywhere — `mosquitto_pub -h test.mosquitto.org -t devices/42/status -m '{"temp": 21}'` — and `device_status(device_id="42", payload={"temp": 21}, ...)` fires.

For a full project layout (controllers, middleware, models, jobs, routers, optional Docker), use the scaffolder:

```bash
routemq new my-app
cd my-app && routemq run
```

## When should I use RouteMQ?

| If you need... | Use |
|---|---|
| Low-level MQTT protocol control, custom session/QoS handling | [`paho-mqtt`](https://github.com/eclipse-paho/paho.mqtt.python) |
| **A web-framework-style structure for an MQTT-first app** | **RouteMQ** |
| Multi-broker streaming across Kafka, RabbitMQ, NATS, Redis, MQTT | [FastStream](https://github.com/ag2ai/faststream) |
| General distributed task queues independent of a broker protocol | [Celery](https://github.com/celery/celery) |

RouteMQ sits on top of `paho-mqtt` — you keep proven protocol behavior, and add structure, async, and scaling.

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
- `RateLimit(60)` runs as middleware before the handler — auth, logging, validation work the same way.

## Background jobs

Push slow work out of the MQTT path:

```python
from routemq.job import Job
from routemq.queue.queue_manager import dispatch


class SendAlertJob(Job):
    max_tries = 3
    queue = "alerts"

    async def handle(self):
        # send the alert
        ...


async def handler(device_id, payload, client):
    if payload.get("status") == "critical":
        await dispatch(SendAlertJob(device_id=device_id))
    return {"ok": True}
```

Run a worker:

```bash
routemq queue-work --queue alerts
```

Queue backends: Redis (with `routemq[redis]`) or MySQL (`routemq` core, when `ENABLE_MYSQL=true`).

## Observability

RouteMQ ships health, readiness, and OpenMetrics endpoints, off by default. Set `METRICS_HTTP_ENABLED=true` to expose them:

```bash
curl http://localhost:8080/health     # liveness
curl http://localhost:8080/ready      # MQTT readiness
curl http://localhost:8080/metrics    # OpenMetrics / Prometheus text
```

Built-in metric families include `mqtt_messages_*`, `router_dispatch_*`, `queue_job_*`, `tsdb_write_*`, and latency histograms for each. Spans follow OpenTelemetry-shaped semantics (`db.system`, `db.operation`, `messaging.system`, `kind=client|consumer|producer|internal`).

For details: [Metrics](./docs/monitoring/metrics.md) · [Health checks](./docs/monitoring/health-checks.md) · [Pool tuning evidence](./docs/monitoring/pool-tuning.md)

## Optional extras

```bash
uv add "routemq[redis]"        # Redis queue + rate limiting backend
uv add "routemq[clickhouse]"   # ClickHouse time-series telemetry
uv add "routemq[prometheus]"   # multiprocess-safe Prometheus client adapter
uv add "routemq[all]"          # everything above plus CLI

# pip works too: pip install "routemq[redis]"
```

## Docker

The scaffolder can drop a complete `docker-compose.yml` with Redis, MySQL, the app, and queue workers:

```bash
routemq new my-app --with-docker --with-redis --with-mysql --with-queue
cd my-app
docker compose up -d
docker compose up -d --scale queue-worker-default=5
```

## Documentation

- **[Getting Started](./docs/getting-started/README.md)** — installation, first route, environment
- **[Architecture](./docs/architecture.md)** — message flow diagram and runtime components
- **[Configuration](./docs/configuration/README.md)** — every environment variable, with defaults
- **[Routing](./docs/routing/README.md)** · **[Controllers](./docs/controllers/README.md)** · **[Middleware](./docs/middleware/README.md)**
- **[Queue System](./docs/queue/README.md)** — jobs, workers, drivers
- **[Rate Limiting](./docs/rate-limiting/README.md)** — strategies and Redis backend
- **[Redis](./docs/redis/README.md)** · **[Database](./docs/database/README.md)** · **[TSDB / ClickHouse](./docs/tsdb/README.md)**
- **[Monitoring](./docs/monitoring/README.md)** — metrics, health, traces
- **[Docker Deployment](./docs/docker-deployment.md)** · **[Testing](./docs/testing/README.md)**
- **[Examples](./docs/examples/README.md)** · **[API Reference](./docs/api-reference/README.md)** · **[FAQ](./docs/faq.md)**
- **[Release Conformance](./docs/release-conformance.md)** — SLSA, Scorecard, SBOM, SemVer

## Project Health

- **[Security Policy](./SECURITY.md)** — private vulnerability reporting and supported versions
- **[Contributing](./CONTRIBUTING.md)** — issues, PRs, tests, coding standards
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

MIT — see [LICENSE](./LICENSE).
