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

## Prometheus / OpenMetrics endpoint

Set `METRICS_HTTP_ENABLED=true` to expose `GET /metrics` from the health HTTP server. The endpoint is
off by default, so existing MQTT-only deployments do not gain a new HTTP surface until operators opt in.
RouteMQ always records the built-in framework metrics in its stdlib `MetricsRegistry`; installing the
optional `routemq[prometheus]` extra adds the official Prometheus client runtime collector and
multiprocess support.

| Mode | What `/metrics` returns | Workers visible? |
|---|---|---|
| Stdlib default | Counters + lifecycle counters from the main process only | No |
| `routemq[prometheus]` with `PROMETHEUS_MULTIPROC_DIR` set | Merged metrics from main + every worker process | Yes |
| `routemq[prometheus]` without `PROMETHEUS_MULTIPROC_DIR` | Main-process metrics only (same as stdlib but with richer types) | No |

Built-in metrics:

| Metric | Type | Labels | Source |
|---|---|---|---|
| `routemq_mqtt_messages_received_total` | counter | `process` (`main`/`worker`) | `mqtt.message.received` lifecycle |
| `routemq_mqtt_messages_succeeded_total` | counter | `process` | `mqtt.message.succeeded` |
| `routemq_mqtt_messages_failed_total` | counter | `process`, `error` (class name) | `mqtt.message.failed` |
| `routemq_mqtt_connect_retries_total` | counter | `process` | `mqtt.connect.retry` |
| `routemq_mqtt_connect_succeeded_total` | counter | `process` | `mqtt.connect.succeeded` |
| `routemq_router_dispatch_started_total` | counter | `route` (route pattern) | `router.dispatch.started` |
| `routemq_router_dispatch_succeeded_total` | counter | `route` | `router.dispatch.succeeded` |
| `routemq_router_dispatch_failed_total` | counter | `route`, `error` | `router.dispatch.failed` |
| `routemq_router_dispatch_missed_total` | counter | (none) | `router.dispatch.missed` |
| `routemq_router_dispatch_duration_seconds` | histogram | `route` | span duration from `router.dispatch` |
| `routemq_queue_enqueue_started_total` | counter | `queue`, `job_class` | `queue.enqueue.started` |
| `routemq_queue_enqueue_succeeded_total` | counter | `queue`, `job_class` | `queue.enqueue.succeeded` |
| `routemq_queue_enqueue_failed_total` | counter | `queue`, `job_class`, `error` | `queue.enqueue.failed` |
| `routemq_queue_job_started_total` | counter | `queue`, `job_class` | `queue.job.started` |
| `routemq_queue_job_succeeded_total` | counter | `queue`, `job_class` | `queue.job.succeeded` |
| `routemq_queue_job_failed_total` | counter | `queue`, `job_class`, `error` | `queue.job.failed` |
| `routemq_queue_job_retried_total` | counter | `queue`, `job_class` | `queue.job.retried` |
| `routemq_queue_job_timed_out_total` | counter | `queue`, `job_class` | `queue.job.timed_out` |
| `routemq_queue_job_dead_lettered_total` | counter | `queue`, `job_class`, `reason` | `queue.job.dead_lettered` |
| `routemq_queue_job_duration_seconds` | histogram | `queue`, `job_class` | span duration from `queue.job` |

Label cardinality rule: label by route pattern, never by concrete topic. `devices/{id}/status` is a
safe `route` label; `devices/123/status` is not. RouteMQ's default hooks strip high-cardinality
observability attributes such as concrete MQTT topics, correlation IDs, trace IDs, span IDs, payloads,
and clients before creating metric labels.

The endpoint negotiates output format from `Accept`. Requests that advertise
`application/openmetrics-text` receive `application/openmetrics-text; version=1.0.0; charset=utf-8`
with the `# EOF` trailer. Other requests receive Prometheus text format as
`text/plain; version=0.0.4; charset=utf-8`.

```bash
curl -s http://127.0.0.1:8080/metrics | head -50
curl -s -H 'Accept: application/openmetrics-text' http://127.0.0.1:8080/metrics | head -50
```

### Cross-process cleanup

When `PROMETHEUS_MULTIPROC_DIR` is set, the official Prometheus client writes per-process files. RouteMQ
calls `routemq.metrics.prometheus.mark_worker_dead(pid)` during graceful worker shutdown, which wraps
`prometheus_client.multiprocess.mark_process_dead(pid)` when the optional extra is installed. Operators
should still place `PROMETHEUS_MULTIPROC_DIR` on a tmpfs-like directory and prune it on app startup after
hard crashes or host restarts.

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

The `/metrics` endpoint covers Prometheus/OpenMetrics pull scraping. OpenTelemetry, push gateway,
remote-write, and vendor-specific exporters remain external integrations; register a metric, trace, or
span hook that forwards events to the client library you prefer.
