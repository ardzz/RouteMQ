# Metrics Collection

RouteMQ exposes backend-neutral observability hooks instead of requiring a specific metrics stack.

## Register hooks

```python
from routemq.observability import (
    register_metric_hook,
    register_span_hook,
    register_trace_hook,
)

def metric_hook(name: str, value: float, attributes: dict) -> None:
    print(name, value, attributes)

def trace_hook(name: str, attributes: dict) -> None:
    print(name, attributes)

def span_hook(snapshot) -> None:
    print(snapshot.name, snapshot.trace_id, snapshot.duration_ms)

unregister_metric = register_metric_hook(metric_hook)
unregister_trace = register_trace_hook(trace_hook)
unregister_span = register_span_hook(span_hook)
```

Hooks receive framework lifecycle events, job events, route dispatch events, and any custom events
emitted by applications. Hook failures are logged and ignored so telemetry outages do not interrupt
message handling.

## Tracing spans

RouteMQ creates W3C-shaped spans (32-hex `trace_id`, 16-hex `span_id`) for MQTT receive, router
dispatch, middleware, handlers, queue enqueue, and queue jobs without requiring an OpenTelemetry
SDK. Spans nest correctly, propagate from producer to consumer through the queue payload, and stay
visible in JSON logs via the `trace_id`, `span_id`, `trace_flags`, and `parent_span_id` fields.

Set `ENABLE_TRACING=false` to make `start_span()` a no-op for low-overhead deployments. See
[Health and Observability API](../api-reference/health-observability-api.md#tracing-spans) for the
full API and a sample span hook.

## Correlation context

RouteMQ stores correlation IDs and attributes in `contextvars`. Jobs serialize observability metadata
so worker-side handling can preserve the same correlation context.

The same context is included in JSON logs when `LOG_INCLUDE_CONTEXT=true`, which lets log-only
deployments correlate MQTT topics, routes, workers, queues, jobs, and future trace/span IDs.

## Lifecycle logs

When `LOG_LIFECYCLE_EVENTS=true`, RouteMQ mirrors known lifecycle events to the `RouteMQ.Lifecycle`
logger. This gives operators a logs-first view of MQTT message handling, router dispatch, enqueue, and
job execution without requiring a metrics exporter.

## Exporters

Prometheus and OpenTelemetry exporters are not bundled. If you need one, register a metric or trace
hook that forwards events to your preferred client library.
