import os
import unittest
from unittest.mock import patch

from routemq import observability
from routemq.metrics import MetricsRegistry
from routemq.metrics.hooks import install_default_hooks


class DefaultHooksTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._tracing_env = patch.dict(os.environ, {'ENABLE_TRACING': 'true'})
        self._tracing_env.start()
        self.registry = MetricsRegistry()
        self.handle = install_default_hooks(self.registry)

    def tearDown(self) -> None:
        self.handle.unregister()
        self._tracing_env.stop()
        observability.clear_hooks()
        super().tearDown()

    def _counter_samples(self, name: str) -> dict[tuple[tuple[str, str], ...], float]:
        for metric_name, _type, _help, samples in self.registry.collect():
            if metric_name == name:
                return {sample.label_key: sample.value for sample in samples}
        return {}

    def _histogram_count(self, name: str, labels: dict[str, str]) -> float:
        for metric_name, metric_type, _help, samples in self.registry.collect():
            if metric_name != name or metric_type != 'histogram':
                continue
            expected = tuple(sorted(labels.items()))
            for sample in samples:
                if sample.name_suffix != '_count':
                    continue
                if tuple(sorted(sample.label_key)) == expected:
                    return sample.value
        return 0.0


class LifecycleCounterTests(DefaultHooksTestCase):
    def test_mqtt_message_received_counter_increments(self) -> None:
        observability.lifecycle('mqtt.message.received', {'process': 'main'})
        observability.lifecycle('mqtt.message.received', {'process': 'worker'})
        observability.lifecycle('mqtt.message.received', {'process': 'main'})

        samples = self._counter_samples('routemq_mqtt_messages_received_total')
        self.assertEqual(samples[(('process', 'main'),)], 2.0)
        self.assertEqual(samples[(('process', 'worker'),)], 1.0)

    def test_router_dispatch_failed_carries_error_label(self) -> None:
        observability.lifecycle(
            'router.dispatch.failed',
            {'route_pattern': 'devices/{id}/status', 'error': 'ValueError'},
        )
        samples = self._counter_samples('routemq_router_dispatch_failed_total')
        key = (('route', 'devices/{id}/status'), ('error', 'ValueError'))
        self.assertEqual(samples[key], 1.0)

    def test_router_dispatch_missed_has_no_labels(self) -> None:
        observability.lifecycle('router.dispatch.missed', {'route_found': False})
        samples = self._counter_samples('routemq_router_dispatch_missed_total')
        self.assertEqual(samples[()], 1.0)

    def test_high_cardinality_keys_are_stripped(self) -> None:
        observability.lifecycle(
            'router.dispatch.started',
            {
                'route_pattern': 'devices/{id}/status',
                'mqtt_topic': 'devices/123/status',
                'correlation_id': 'abc',
                'trace_id': 'def',
            },
        )
        samples = self._counter_samples('routemq_router_dispatch_started_total')
        self.assertEqual(samples[(('route', 'devices/{id}/status'),)], 1.0)
        for key in samples:
            self.assertNotIn('mqtt_topic', dict(key))
            self.assertNotIn('correlation_id', dict(key))

    def test_unknown_lifecycle_event_is_ignored(self) -> None:
        observability.lifecycle('unknown.custom.event', {'whatever': True})
        self.assertEqual(list(self.registry.collect()), [])

    def test_label_value_truncates_at_max_length(self) -> None:
        long_route = 'x' * 500
        observability.lifecycle(
            'router.dispatch.started',
            {'route_pattern': long_route},
        )
        samples = self._counter_samples('routemq_router_dispatch_started_total')
        only_key = next(iter(samples))
        only_label_value = dict(only_key)['route']
        self.assertEqual(len(only_label_value), 200)


class SpanHistogramTests(DefaultHooksTestCase):
    def test_router_dispatch_span_populates_histogram(self) -> None:
        with observability.start_span(
            'router.dispatch',
            {'messaging.destination.template': 'devices/{id}/status'},
        ):
            pass
        count = self._histogram_count(
            'routemq_router_dispatch_duration_seconds',
            {'route': 'devices/{id}/status'},
        )
        self.assertEqual(count, 1.0)

    def test_queue_job_span_uses_queue_and_job_class(self) -> None:
        with observability.start_span(
            'queue.job',
            {'messaging.destination': 'emails', 'routemq.job.name': 'SendEmail'},
        ):
            pass
        count = self._histogram_count(
            'routemq_queue_job_duration_seconds',
            {'queue': 'emails', 'job_class': 'SendEmail'},
        )
        self.assertEqual(count, 1.0)

    def test_unknown_span_is_ignored(self) -> None:
        with observability.start_span('custom.unrelated'):
            pass
        self.assertEqual(list(self.registry.collect()), [])

    def test_unregister_removes_hooks(self) -> None:
        self.handle.unregister()
        observability.lifecycle('mqtt.message.received', {'process': 'main'})
        self.assertEqual(list(self.registry.collect()), [])


if __name__ == '__main__':
    unittest.main()
