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

`HealthServer(status, host="127.0.0.1", port=8080, metrics_renderer=None, metrics_path="/metrics")`
accepts any `HealthPayloadSource`, a `typing.Protocol` in `routemq.health`: an object whose `health_payload()` and
`readiness_payload()` methods each return `(status_code, payload_dict)`. RouteMQ ships two sources, the app's
`HealthStatus` and `routemq.queue.queue_worker.QueueWorker`. The server calls the matching method on every
`GET /health` or `GET /ready` from its HTTP thread and returns the payload as JSON, so a source must be safe to call
from that thread.

Use `health_server_from_env(status)` to construct the server from `HEALTH_HTTP_*` settings; it returns `None`
when `HEALTH_HTTP_ENABLED` is false. Pass `metrics_renderer=callable` to add `GET /metrics`; the callable
receives the request `Accept` header and returns `(content_type, body_bytes)`. When no renderer is configured,
`/metrics` behaves like any unknown path and returns `404 {"status": "not_found"}`.

```python
from routemq.health import health_server_from_env

def metrics_renderer(accept: str | None) -> tuple[str, bytes]:
    return "text/plain; version=0.0.4; charset=utf-8", b"# HELP example h\n"

server = health_server_from_env(status, metrics_renderer=metrics_renderer)
```

### Queue worker source

`routemq queue-work` passes its `QueueWorker` to `health_server_from_env()` after connection setup, starts the
server before `QueueWorker.work()`, and stops it in a `finally` block when the loop returns or raises. It passes no
metrics renderer, so a worker's `/metrics` returns `404`.

`QueueWorker.readiness_payload()` blocks the request thread while `QueueManager.validate_connection()` runs for
the requested connection on the worker's own event loop, for at most 3 seconds. `validate_connection(connection=None)`
returns `"redis"` after a `PING` on the existing Redis client, or `"database"` after `SELECT 1` and a check for the
`queue_jobs` and `queue_failed_jobs` tables. It raises when the check fails, and raises `RuntimeError` for any
connection that is not the built-in `redis` or `database` driver. It never applies the Redis-to-database fallback
that `get_driver()` uses. [Health Checks](../monitoring/health-checks.md#queue-worker-readiness) lists the
readiness conditions and payload fields.

### Container probe

`python -m routemq.healthcheck` exits `0` only when the local `/ready` endpoint configured by `HEALTH_HTTP_*`
answers `200` with `"status": "ready"`, and `1` otherwise. `routemq.healthcheck.probe_ready()` returns the same
result as a `bool`, and `main()` returns the exit code. See
[Health Checks](../monitoring/health-checks.md#container-probe) for how it loads settings and picks the address.

## MetricsRegistry

```python
from routemq.metrics import MetricsRegistry
from routemq.metrics.exposition import negotiate_content_type, render
from routemq.metrics.hooks import install_default_hooks

registry = MetricsRegistry()
registry.counter(
    "routemq_custom_events_total",
    help="Custom app events.",
    label_names=("kind",),
).inc(labels={"kind": "demo"})
registry.histogram(
    "routemq_custom_duration_seconds",
    help="Custom durations.",
).observe(0.25)

handle = install_default_hooks(registry)
content_type = negotiate_content_type("application/openmetrics-text")
payload = render(registry, content_type=content_type)
handle.unregister()
```

`MetricsRegistry.counter(name, help, label_names=())` returns a monotonic counter. Call
`Counter.inc(amount=1.0, labels=None)` to increment it; negative increments raise `ValueError`.

`MetricsRegistry.histogram(name, help, label_names=(), bucket_bounds=None)` returns a fixed-bucket
histogram. Call `Histogram.observe(value, labels=None)` to record seconds or other numeric values. The
default buckets are `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]` seconds.

`install_default_hooks(registry, namespace="routemq", histogram_buckets=...)` registers RouteMQ's
built-in lifecycle and span hooks. The returned handle has `unregister()` for tests and controlled
shutdown. Default hooks sanitize labels with the internal high-cardinality stripping rules before they
reach the registry.

### Optional Prometheus adapter

```python
from routemq.metrics import MetricsRegistry
from routemq.metrics.prometheus import PrometheusAdapter, mark_worker_dead

registry = MetricsRegistry()
adapter = PrometheusAdapter(namespace="routemq")
handle = adapter.install_default_hooks(registry)
content_type, body = adapter.render("application/openmetrics-text")
mark_worker_dead(12345)
handle.unregister()
```

`PrometheusAdapter` requires the optional `routemq[prometheus]` extra only when rendering or touching
official-client features. If the extra is missing, methods that need it raise
`RuntimeError('routemq[prometheus] extra is not installed. Install with: pip install "routemq[prometheus]"')`.
`is_multiprocess_enabled()` returns `True` when `prometheus_client` is importable and the constructor
`multiproc_dir` or `PROMETHEUS_MULTIPROC_DIR` points to an existing directory. `mark_worker_dead(pid)`
is safe to call unconditionally; it no-ops when the extra or multiprocess directory is absent.

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
