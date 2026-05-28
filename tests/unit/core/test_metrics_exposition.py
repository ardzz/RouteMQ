import unittest

from routemq.metrics import MetricsRegistry
from routemq.metrics.exposition import (
    OPENMETRICS_CONTENT_TYPE,
    PROMETHEUS_CONTENT_TYPE,
    negotiate_content_type,
    render,
)


class NegotiateContentTypeTests(unittest.TestCase):
    def test_missing_accept_returns_prometheus(self) -> None:
        self.assertEqual(negotiate_content_type(None), PROMETHEUS_CONTENT_TYPE)
        self.assertEqual(negotiate_content_type(''), PROMETHEUS_CONTENT_TYPE)

    def test_plain_accept_returns_prometheus(self) -> None:
        self.assertEqual(negotiate_content_type('*/*'), PROMETHEUS_CONTENT_TYPE)
        self.assertEqual(negotiate_content_type('text/plain'), PROMETHEUS_CONTENT_TYPE)

    def test_openmetrics_accept_returns_openmetrics(self) -> None:
        self.assertEqual(
            negotiate_content_type('application/openmetrics-text;version=1.0.0'),
            OPENMETRICS_CONTENT_TYPE,
        )
        self.assertEqual(
            negotiate_content_type('text/plain, application/openmetrics-text'),
            OPENMETRICS_CONTENT_TYPE,
        )


class RenderPrometheusTests(unittest.TestCase):
    def test_counter_emits_help_type_and_value(self) -> None:
        registry = MetricsRegistry()
        counter = registry.counter('routemq_test_counter', help='example counter')
        counter.inc(3)
        output = render(registry).decode('utf-8')
        self.assertIn('# HELP routemq_test_counter example counter\n', output)
        self.assertIn('# TYPE routemq_test_counter counter\n', output)
        self.assertIn('routemq_test_counter_total 3\n', output)

    def test_counter_with_labels_escapes_values(self) -> None:
        registry = MetricsRegistry()
        counter = registry.counter('routemq_test_labelled', help='h', label_names=('route',))
        counter.inc(labels={'route': 'devices/{id}/status'})
        counter.inc(labels={'route': 'broken"\nroute'})
        output = render(registry).decode('utf-8')
        self.assertIn('routemq_test_labelled_total{route="devices/{id}/status"} 1', output)
        self.assertIn('routemq_test_labelled_total{route="broken\\"\\nroute"} 1', output)

    def test_histogram_emits_buckets_sum_and_count(self) -> None:
        registry = MetricsRegistry()
        histogram = registry.histogram(
            'routemq_test_duration_seconds',
            help='durations',
            bucket_bounds=(0.1, 0.5, 1.0),
        )
        histogram.observe(0.4)
        histogram.observe(0.9)
        output = render(registry).decode('utf-8')
        self.assertIn('# TYPE routemq_test_duration_seconds histogram\n', output)
        self.assertIn('routemq_test_duration_seconds_bucket{le="0.1"} 0\n', output)
        self.assertIn('routemq_test_duration_seconds_bucket{le="0.5"} 1\n', output)
        self.assertIn('routemq_test_duration_seconds_bucket{le="1.0"} 2\n', output)
        self.assertIn('routemq_test_duration_seconds_bucket{le="+Inf"} 2\n', output)
        self.assertIn('routemq_test_duration_seconds_count 2\n', output)
        self.assertIn('routemq_test_duration_seconds_sum 1.3\n', output)


class RenderOpenMetricsTests(unittest.TestCase):
    def test_openmetrics_adds_eof_trailer(self) -> None:
        registry = MetricsRegistry()
        registry.counter('routemq_test_counter', help='h').inc()
        output = render(registry, content_type=OPENMETRICS_CONTENT_TYPE).decode('utf-8')
        self.assertTrue(output.endswith('# EOF\n'))

    def test_openmetrics_value_keeps_float_format(self) -> None:
        registry = MetricsRegistry()
        registry.counter('routemq_test_counter', help='h').inc(2.5)
        output = render(registry, content_type=OPENMETRICS_CONTENT_TYPE).decode('utf-8')
        self.assertIn('routemq_test_counter_total 2.5\n', output)


class RenderStaticLabelsTests(unittest.TestCase):
    def test_static_labels_are_merged_into_every_sample(self) -> None:
        registry = MetricsRegistry()
        counter = registry.counter('routemq_test_counter', help='h', label_names=('queue',))
        counter.inc(labels={'queue': 'default'})
        histogram = registry.histogram('routemq_test_duration_seconds', help='h')
        histogram.observe(0.1)
        output = render(
            registry,
            static_labels={'service': 'routemq-app', 'env': 'prod'},
        ).decode('utf-8')
        self.assertIn('routemq_test_counter_total{service="routemq-app",env="prod",queue="default"} 1', output)
        self.assertIn('routemq_test_duration_seconds_bucket{service="routemq-app",env="prod",le="0.1"}', output)
        self.assertIn('routemq_test_duration_seconds_count{service="routemq-app",env="prod"} 1', output)

    def test_unsupported_content_type_rejects(self) -> None:
        with self.assertRaises(ValueError):
            render(MetricsRegistry(), content_type='application/json')


if __name__ == '__main__':
    unittest.main()
