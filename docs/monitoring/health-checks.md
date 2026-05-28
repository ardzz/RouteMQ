# Health Checks

RouteMQ includes a stdlib HTTP health server for application liveness and readiness checks.

## Enable the server

```env
HEALTH_HTTP_ENABLED=true
HEALTH_HTTP_HOST=127.0.0.1
HEALTH_HTTP_PORT=8080
```

The app starts the server during bootstrap when `HEALTH_HTTP_ENABLED=true`.

## Endpoints

| Endpoint | Meaning | Healthy response |
|---|---|---|
| `/health` | Process liveness | `200 {"alive": true, "status": "ok"}` |
| `/ready` | Startup and MQTT readiness | `200 {"status": "ready", ...}` |

Readiness returns `503` while startup is incomplete, MQTT is disconnected, shutdown is in progress,
or the process has marked itself unhealthy.

## Docker and orchestration

For container platforms, point the liveness probe at `/health` and the readiness probe at `/ready`.
Keep the health host bound to `127.0.0.1` for local-only probes, or bind to `0.0.0.0` only when the
probe must come from outside the container network namespace.

## Limitations

The built-in health server reports RouteMQ process and MQTT readiness. It does not currently perform
deep Redis, MySQL, or broker dependency checks.
