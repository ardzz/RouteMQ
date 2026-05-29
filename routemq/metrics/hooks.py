"""Default RouteMQ trace/span hooks that translate lifecycle events into metrics.

The hooks bridge ``routemq.observability`` events to ``MetricsRegistry``
without coupling the framework to any specific telemetry backend. Lifecycle
event names map 1:1 to counter families; ``router.dispatch`` and ``queue.job``
span durations populate latency histograms.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from routemq.metrics.registry import DEFAULT_HISTOGRAM_BUCKETS, MetricsRegistry
from routemq.observability import (
    SpanSnapshot,
    register_span_hook,
    register_trace_hook,
)

_MAX_LABEL_VALUE_LENGTH = 200
_HIGH_CARDINALITY_KEYS: frozenset[str] = frozenset(
    {
        'correlation_id',
        'trace_id',
        'span_id',
        'parent_span_id',
        'trace_flags',
        'mqtt_topic',
        'actual_topic',
        'topic',
        'payload',
        'client',
    }
)


@dataclass(frozen=True)
class DefaultHooksHandle:
    """Handle returned by :func:`install_default_hooks` for unregistration."""

    unregister: Callable[[], None]


def install_default_hooks(
    registry: MetricsRegistry,
    *,
    namespace: str = 'routemq',
    histogram_buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS,
) -> DefaultHooksHandle:
    """Register lifecycle + span hooks that maintain the built-in metric set.

    Counters and histograms are created lazily on first event so callers that
    skip a particular lifecycle (for example MQTT-only apps) do not pay for
    queue families they never use. The returned handle's ``unregister``
    callable removes both hooks, primarily for tests.
    """

    builder = _DefaultHooksBuilder(registry, namespace=namespace, histogram_buckets=histogram_buckets)
    unregister_trace = register_trace_hook(builder.on_lifecycle)
    unregister_span = register_span_hook(builder.on_span)

    def unregister() -> None:
        try:
            unregister_trace()
        finally:
            unregister_span()

    return DefaultHooksHandle(unregister=unregister)


class _DefaultHooksBuilder:
    def __init__(
        self,
        registry: MetricsRegistry,
        *,
        namespace: str,
        histogram_buckets: tuple[float, ...],
    ) -> None:
        self._registry = registry
        self._namespace = namespace.strip('_') or 'routemq'
        self._histogram_buckets = histogram_buckets

    def on_lifecycle(self, name: str, attributes: dict[str, Any]) -> None:
        recipe = _LIFECYCLE_COUNTERS.get(name)
        if recipe is None:
            return
        counter = self._registry.counter(
            self._qualify(recipe.metric),
            help=recipe.help,
            label_names=recipe.label_names,
        )
        counter.inc(1.0, labels=self._sanitize_labels(recipe.label_names, attributes))

    def on_span(self, snapshot: SpanSnapshot) -> None:
        recipe = _SPAN_HISTOGRAMS.get(snapshot.name)
        if recipe is None:
            return
        histogram = self._registry.histogram(
            self._qualify(recipe.metric),
            help=recipe.help,
            label_names=recipe.label_names,
            bucket_bounds=self._histogram_buckets,
        )
        duration_seconds = max(snapshot.duration_ms, 0.0) / 1000.0
        histogram.observe(duration_seconds, labels=self._sanitize_labels(recipe.label_names, snapshot.attributes))

    def _qualify(self, metric: str) -> str:
        return f'{self._namespace}_{metric}'

    def _sanitize_labels(
        self,
        label_names: tuple[str, ...],
        attributes: Mapping[str, Any] | None,
    ) -> dict[str, str]:
        if not label_names:
            return {}
        source: dict[str, Any] = {}
        if attributes:
            source.update(_strip_high_cardinality(attributes))
        sanitized: dict[str, str] = {}
        for name in label_names:
            value = source.get(name, '')
            text = '' if value is None else str(value)
            if len(text) > _MAX_LABEL_VALUE_LENGTH:
                text = text[:_MAX_LABEL_VALUE_LENGTH]
            sanitized[name] = text
        return sanitized


def _strip_high_cardinality(attributes: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in attributes.items() if key not in _HIGH_CARDINALITY_KEYS}
    template = attributes.get('messaging.destination.template')
    route_pattern = attributes.get('route_pattern') or attributes.get('routemq.route.pattern')
    if 'route' not in cleaned:
        if isinstance(template, str) and template:
            cleaned['route'] = template
        elif isinstance(route_pattern, str) and route_pattern:
            cleaned['route'] = route_pattern
    if 'queue' not in cleaned:
        destination = attributes.get('messaging.destination')
        if isinstance(destination, str) and destination:
            cleaned['queue'] = destination
    if 'job_class' not in cleaned:
        job_name = attributes.get('routemq.job.name')
        if isinstance(job_name, str) and job_name:
            cleaned['job_class'] = job_name
    if 'measurement' not in cleaned:
        collection = attributes.get('db.collection.name')
        if isinstance(collection, str) and collection:
            cleaned['measurement'] = collection
    return cleaned


@dataclass(frozen=True)
class _CounterRecipe:
    metric: str
    help: str
    label_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class _HistogramRecipe:
    metric: str
    help: str
    label_names: tuple[str, ...] = ()


_LIFECYCLE_COUNTERS: dict[str, _CounterRecipe] = {
    'mqtt.connect.retry': _CounterRecipe(
        metric='mqtt_connect_retries_total',
        help='MQTT connection retries attempted by the client.',
        label_names=('process',),
    ),
    'mqtt.connect.succeeded': _CounterRecipe(
        metric='mqtt_connect_succeeded_total',
        help='Successful MQTT connection events.',
        label_names=('process',),
    ),
    'mqtt.message.received': _CounterRecipe(
        metric='mqtt_messages_received_total',
        help='MQTT messages received before router dispatch.',
        label_names=('process',),
    ),
    'mqtt.message.succeeded': _CounterRecipe(
        metric='mqtt_messages_succeeded_total',
        help='MQTT messages handled successfully end-to-end.',
        label_names=('process',),
    ),
    'mqtt.message.failed': _CounterRecipe(
        metric='mqtt_messages_failed_total',
        help='MQTT messages that raised during dispatch.',
        label_names=('process', 'error'),
    ),
    'router.dispatch.started': _CounterRecipe(
        metric='router_dispatch_started_total',
        help='Router dispatch attempts started.',
        label_names=('route',),
    ),
    'router.dispatch.succeeded': _CounterRecipe(
        metric='router_dispatch_succeeded_total',
        help='Router dispatch attempts completed without error.',
        label_names=('route',),
    ),
    'router.dispatch.failed': _CounterRecipe(
        metric='router_dispatch_failed_total',
        help='Router dispatch attempts that raised.',
        label_names=('route', 'error'),
    ),
    'router.dispatch.missed': _CounterRecipe(
        metric='router_dispatch_missed_total',
        help='Router dispatch attempts with no matching route.',
    ),
    'queue.enqueue.started': _CounterRecipe(
        metric='queue_enqueue_started_total',
        help='Queue enqueue attempts started.',
        label_names=('queue', 'job_class'),
    ),
    'queue.enqueue.succeeded': _CounterRecipe(
        metric='queue_enqueue_succeeded_total',
        help='Queue enqueue attempts completed.',
        label_names=('queue', 'job_class'),
    ),
    'queue.enqueue.failed': _CounterRecipe(
        metric='queue_enqueue_failed_total',
        help='Queue enqueue attempts that raised.',
        label_names=('queue', 'job_class', 'error'),
    ),
    'queue.job.started': _CounterRecipe(
        metric='queue_job_started_total',
        help='Queue jobs whose handlers were invoked.',
        label_names=('queue', 'job_class'),
    ),
    'queue.job.succeeded': _CounterRecipe(
        metric='queue_job_succeeded_total',
        help='Queue jobs that finished without error.',
        label_names=('queue', 'job_class'),
    ),
    'queue.job.timed_out': _CounterRecipe(
        metric='queue_job_timed_out_total',
        help='Queue jobs killed by timeout.',
        label_names=('queue', 'job_class'),
    ),
    'queue.job.retried': _CounterRecipe(
        metric='queue_job_retried_total',
        help='Queue jobs released back to the queue for retry.',
        label_names=('queue', 'job_class'),
    ),
    'queue.job.failed': _CounterRecipe(
        metric='queue_job_failed_total',
        help='Queue jobs that exhausted retries and moved to failed storage.',
        label_names=('queue', 'job_class', 'error'),
    ),
    'queue.job.dead_lettered': _CounterRecipe(
        metric='queue_job_dead_lettered_total',
        help='Queue jobs moved straight to the failed queue without further retry.',
        label_names=('queue', 'job_class', 'reason'),
    ),
    'tsdb.write.batches': _CounterRecipe(
        metric='tsdb_write_batches_total',
        help='TSDB batched inserts completed successfully.',
        label_names=('measurement',),
    ),
    'tsdb.write.errors': _CounterRecipe(
        metric='tsdb_write_errors_total',
        help='TSDB batched inserts that exhausted retries and dropped their batch.',
        label_names=('measurement', 'error'),
    ),
}


_SPAN_HISTOGRAMS: dict[str, _HistogramRecipe] = {
    'router.dispatch': _HistogramRecipe(
        metric='router_dispatch_duration_seconds',
        help='Wall-clock duration of router dispatch spans, in seconds.',
        label_names=('route',),
    ),
    'queue.job': _HistogramRecipe(
        metric='queue_job_duration_seconds',
        help='Wall-clock duration of queue job spans, in seconds.',
        label_names=('queue', 'job_class'),
    ),
    'tsdb.write.flush': _HistogramRecipe(
        metric='tsdb_flush_duration_seconds',
        help='Wall-clock duration of TSDB batched flush spans, in seconds.',
        label_names=('measurement',),
    ),
}
