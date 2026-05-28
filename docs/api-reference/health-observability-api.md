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
from routemq.observability import (
    register_metric_hook,
    register_span_hook,
    register_trace_hook,
)

unregister_metric = register_metric_hook(lambda name, value, attrs: None)
unregister_trace = register_trace_hook(lambda name, attrs: None)
unregister_span = register_span_hook(lambda snapshot: None)
```

Hooks receive copies of event attributes (or, for span hooks, an immutable `SpanSnapshot` copy).
Exceptions raised by hooks are logged at debug level and do not interrupt framework execution.

## Correlation helpers

```python
from routemq.observability import get_correlation_id, set_context, snapshot_context

token = set_context({"topic": "devices/1/status"})
correlation_id = get_correlation_id()
context = snapshot_context()
```

Use these helpers when bridging RouteMQ events into external logging, metrics, or tracing libraries.

## Tracing spans

RouteMQ ships a stdlib-only tracing seam that emits W3C-shaped 32-hex `trace_id` and 16-hex `span_id`
values without requiring an OpenTelemetry SDK. Spans are automatically created for `mqtt.receive`
(main and worker processes), `router.dispatch`, `router.middleware`, `router.handler`,
`queue.enqueue`, and `queue.job`. Queue jobs inherit the producer trace context through the job
payload so the consumer span links back to the enqueue span.

```python
from routemq.observability import current_span, register_span_hook, start_span

def export(snapshot):
    print(snapshot.name, snapshot.trace_id, snapshot.span_id, snapshot.duration_ms)

unregister = register_span_hook(export)

with start_span("custom.work", {"job.kind": "report"}) as span:
    if span is not None:
        span.set_attribute("user.id", "u-1")
        span.add_event("checkpoint")
    # ...
```

`start_span()` returns `None` to the `as` target when `ENABLE_TRACING=false`, so user code must
tolerate `None` if it disables tracing. `current_span()` returns the active span (or `None`).
`snapshot_context()` includes the active span's `trace_id`, `span_id`, `trace_flags`, and
`parent_span_id`, which RouteMQ's JSON logs surface automatically.

## Structured logging helpers

```python
from routemq.logging_config import RouteMQJsonFormatter, configure_logging, json_logging_enabled

settings = configure_logging()
is_json = json_logging_enabled()
formatter = RouteMQJsonFormatter(field_profile="otel")
```

`configure_logging()` reads the `LOG_*` environment variables documented in
[Logging Configuration](../configuration/logging.md). JSON logs surface `trace_id`, `span_id`,
`trace_flags`, and `parent_span_id` automatically when a span is active.
