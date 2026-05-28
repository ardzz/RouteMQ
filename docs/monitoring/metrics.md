# Metrics Collection

RouteMQ exposes backend-neutral observability hooks instead of requiring a specific metrics stack.

## Register hooks

```python
from routemq.observability import register_metric_hook, register_trace_hook

def metric_hook(name: str, value: float, attributes: dict) -> None:
    print(name, value, attributes)

def trace_hook(name: str, attributes: dict) -> None:
    print(name, attributes)

unregister_metric = register_metric_hook(metric_hook)
unregister_trace = register_trace_hook(trace_hook)
```

Hooks receive framework lifecycle events, job events, route dispatch events, and any custom events
emitted by applications. Hook failures are logged and ignored so telemetry outages do not interrupt
message handling.

## Correlation context

RouteMQ stores correlation IDs and attributes in `contextvars`. Jobs serialize observability metadata
so worker-side handling can preserve the same correlation context.

## Exporters

Prometheus and OpenTelemetry exporters are not bundled. If you need one, register a metric or trace
hook that forwards events to your preferred client library.
