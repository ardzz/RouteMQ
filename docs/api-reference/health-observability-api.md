# Health and Observability API

RouteMQ exposes health/readiness primitives and stdlib-only observability hooks.

## HealthStatus

```python
from routemq.health import HealthStatus

status = HealthStatus()
```

`HealthStatus.health_payload()` returns liveness status. `HealthStatus.readiness_payload()` returns
readiness status based on process liveness, startup completion, MQTT connectivity, and shutdown state.

## HealthServer

```python
from routemq.health import HealthServer, HealthStatus

status = HealthStatus(startup_complete=True, mqtt_connected=True)
server = HealthServer(status, host="127.0.0.1", port=8080)
server.start()
server.stop()
```

Use `health_server_from_env(status)` to construct the server from `HEALTH_HTTP_*` settings.

## Observability hooks

```python
from routemq.observability import register_metric_hook, register_trace_hook

unregister_metric = register_metric_hook(lambda name, value, attrs: None)
unregister_trace = register_trace_hook(lambda name, attrs: None)
```

Hooks receive copies of event attributes. Exceptions raised by hooks are logged at debug level and do
not interrupt framework execution.

## Correlation helpers

```python
from routemq.observability import get_correlation_id, set_context, snapshot_context

token = set_context({"topic": "devices/1/status"})
correlation_id = get_correlation_id()
context = snapshot_context()
```

Use these helpers when bridging RouteMQ events into external logging, metrics, or tracing libraries.
