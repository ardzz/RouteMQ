# Health Checks

RouteMQ includes a stdlib HTTP health server for liveness and readiness checks. The MQTT application and each
queue worker process can serve one.

## Enable the server

```env
HEALTH_HTTP_ENABLED=true
HEALTH_HTTP_HOST=127.0.0.1
HEALTH_HTTP_PORT=8080
```

The app starts the server during bootstrap when `HEALTH_HTTP_ENABLED=true`.

A queue worker started with `routemq queue-work` (or the `--queue-work` alias) starts its own server after
connection setup and before the worker loop begins. It stops the server when the loop returns or raises. The
worker server answers `/health` and `/ready` only; it has no `/metrics` endpoint.

Every process binds its own port. On a shared host, give each RouteMQ process that enables the server a different
`HEALTH_HTTP_PORT`. Containers each have their own loopback interface, so the app container and every worker
container can all use `127.0.0.1:8080`.

The root Docker image sets `HEALTH_HTTP_ENABLED=true`, `HEALTH_HTTP_HOST=127.0.0.1`, and `HEALTH_HTTP_PORT=8080`.
Both the app and the probe load `/app/.env` without overriding variables that are already set, so these image
values win over the same keys in a mounted `.env`. Override them in the container environment instead.

## Endpoints

| Endpoint | Meaning | Healthy response |
|---|---|---|
| `/health` | Process liveness | `200 {"alive": true, "status": "ok"}` |
| `/ready` | App: startup and MQTT readiness. Queue worker: worker loop and queue backend readiness | `200 {"status": "ready", ...}` |

### Application readiness

Readiness returns `503` while startup is incomplete, MQTT is disconnected, shutdown is in progress,
or the process has marked itself unhealthy. These flags are in-memory process state; a `/ready` request does
not call Redis, MySQL, or the broker.

### Queue worker readiness

A worker's `/ready` returns `200` only when all of these hold:

- The worker loop has started (`initialized: true`) and the worker state is `running`. A worker that is idle or
  processing a job is `running`; `draining`, `stopping`, and `dead` return `503`.
- The worker is not paused and has not been asked to stop.
- The backend check for the requested queue connection succeeds. Each request schedules the check on the
  worker's own asyncio loop and waits up to 3 seconds, so a blocked loop or a slow backend also returns `503`.

| Connection | Check |
|---|---|
| `redis` | `PING` on the worker's existing Redis client |
| `database` | `SELECT 1` on the configured engine, plus both `queue_jobs` and `queue_failed_jobs` present |

The requested connection is `--connection`, or `QUEUE_CONNECTION` when the flag is absent (default `redis`). Only
the built-in `redis` and `database` drivers have a check. A custom driver, or a replaced factory registered under
either built-in name, always returns `503`.

Readiness does not read the Redis worker heartbeat metadata, so an idle worker stays ready after that metadata
expires. If Redis is disabled or failed to initialize when a Redis worker starts, the worker can still fall back to
the database queue and process jobs from it, but its `/ready` keeps checking Redis and stays `503`. The probe does
not change which backend the worker uses.

```json
{"connection": "redis", "initialized": true, "paused": false, "queue": "default", "role": "queue-worker", "state": "running", "status": "ready"}
```

A `503` payload omits `connection`. When the backend check raised, it adds `error` with the exception class name.
A worker's `/health` returns `200` until the worker state is `dead`.

## Container probe

```bash
/opt/venv/bin/python -m routemq.healthcheck
```

The root image `HEALTHCHECK` and the root `docker-compose.yml` run this command for the app and for every queue
worker, because each process serves its own `/ready`. The probe:

- loads `.env` from the working directory with the same precedence as the app, then reads `HEALTH_HTTP_*`;
- requests `/ready` on the configured host and port, mapping a wildcard bind (`0.0.0.0` or `::`) to loopback;
- connects directly, ignoring HTTP proxy variables, with a 5-second timeout;
- exits `0` only for a `200` response whose JSON body has `"status": "ready"`.

A disabled server, a refused or timed-out connection, a non-`200` status, and a malformed body all exit `1`. The
probe has no settings of its own. If you set `HEALTH_HTTP_ENABLED=false` for a container, also disable its Docker
health check, or Docker marks it unhealthy.

## Docker and orchestration

For container platforms, point the liveness probe at `/health` and the readiness probe at `/ready`.
Keep the health host bound to `127.0.0.1` for local-only probes, or bind to `0.0.0.0` only when the
probe must come from outside the container network namespace.

Docker marks a container `unhealthy` after the configured retries, but it does not restart or replace it.
`restart: unless-stopped` restarts a container only when its process exits. Act on unhealthy status with an
orchestrator or external monitor.

## Limitations

App readiness reports RouteMQ process and MQTT readiness. It does not perform deep Redis, MySQL, or ClickHouse
checks, continuously or per request.

Queue worker readiness checks only the requested queue backend, and only when `/ready` is requested. It does not
check MQTT, ClickHouse, or the other queue backend.
