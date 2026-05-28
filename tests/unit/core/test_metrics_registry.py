import threading
import unittest

from routemq.metrics import Counter, Histogram, MetricsRegistry


class CounterTests(unittest.TestCase):
    def test_increment_default_value(self) -> None:
        counter = Counter(name='example', help='example counter')
        counter.inc()
        samples = list(counter.collect())
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].value, 1.0)
        self.assertEqual(samples[0].name_suffix, '_total')
        self.assertEqual(samples[0].label_key, ())

    def test_increment_with_labels(self) -> None:
        counter = Counter(name='example', help='example', label_names=('queue',))
        counter.inc(2.0, labels={'queue': 'default'})
        counter.inc(0.5, labels={'queue': 'default'})
        counter.inc(1.0, labels={'queue': 'emails'})
        samples = {sample.label_key: sample.value for sample in counter.collect()}
        self.assertEqual(samples[(('queue', 'default'),)], 2.5)
        self.assertEqual(samples[(('queue', 'emails'),)], 1.0)

    def test_increment_rejects_negative(self) -> None:
        counter = Counter(name='example', help='example')
        with self.assertRaises(ValueError):
            counter.inc(-1)

    def test_increment_is_thread_safe(self) -> None:
        counter = Counter(name='example', help='example')

        def worker() -> None:
            for _ in range(1000):
                counter.inc()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        samples = list(counter.collect())
        self.assertEqual(samples[0].value, 8000.0)


class HistogramTests(unittest.TestCase):
    def test_observation_increments_buckets_sum_and_count(self) -> None:
        histogram = Histogram(name='latency', help='latency', bucket_bounds=(0.1, 0.5, 1.0))
        histogram.observe(0.05)
        histogram.observe(0.4)
        histogram.observe(2.0)
        samples = list(histogram.collect())

        buckets = {sample.label_key: sample.value for sample in samples if sample.name_suffix == '_bucket'}
        self.assertEqual(buckets[(('le', '0.1'),)], 1.0)
        self.assertEqual(buckets[(('le', '0.5'),)], 2.0)
        self.assertEqual(buckets[(('le', '1.0'),)], 2.0)
        self.assertEqual(buckets[(('le', '+Inf'),)], 3.0)

        sum_sample = next(sample for sample in samples if sample.name_suffix == '_sum')
        count_sample = next(sample for sample in samples if sample.name_suffix == '_count')
        self.assertAlmostEqual(sum_sample.value, 2.45)
        self.assertEqual(count_sample.value, 3.0)

    def test_infinite_bucket_bound_formats_as_plus_inf(self) -> None:
        histogram = Histogram(name='latency', help='latency', bucket_bounds=(float('inf'),))
        histogram.observe(99.0)

        buckets = {sample.label_key: sample.value for sample in histogram.collect() if sample.name_suffix == '_bucket'}

        self.assertEqual(buckets[(('le', '+Inf'),)], 1.0)

    def test_histogram_rejects_nan(self) -> None:
        histogram = Histogram(name='latency', help='latency')
        with self.assertRaises(ValueError):
            histogram.observe(float('nan'))

    def test_histogram_segregates_by_labels(self) -> None:
        histogram = Histogram(name='latency', help='latency', label_names=('route',))
        histogram.observe(0.05, labels={'route': 'a'})
        histogram.observe(0.5, labels={'route': 'b'})

        samples = list(histogram.collect())
        a_count = next(
            sample for sample in samples if sample.name_suffix == '_count' and ('route', 'a') in sample.label_key
        )
        b_count = next(
            sample for sample in samples if sample.name_suffix == '_count' and ('route', 'b') in sample.label_key
        )
        self.assertEqual(a_count.value, 1.0)
        self.assertEqual(b_count.value, 1.0)


class RegistryTests(unittest.TestCase):
    def test_counter_is_idempotent(self) -> None:
        registry = MetricsRegistry()
        first = registry.counter('example', help='h')
        second = registry.counter('example', help='h')
        self.assertIs(first, second)

    def test_counter_rejects_mismatched_labels(self) -> None:
        registry = MetricsRegistry()
        registry.counter('example', help='h', label_names=('queue',))
        with self.assertRaises(ValueError):
            registry.counter('example', help='h', label_names=('queue', 'class'))

    def test_histogram_rejects_mismatched_buckets(self) -> None:
        registry = MetricsRegistry()
        registry.histogram('latency', help='h', bucket_bounds=(0.1,))
        with self.assertRaises(ValueError):
            registry.histogram('latency', help='h', bucket_bounds=(0.5,))

    def test_histogram_rejects_mismatched_labels(self) -> None:
        registry = MetricsRegistry()
        registry.histogram('latency', help='h', label_names=('route',))
        with self.assertRaises(ValueError):
            registry.histogram('latency', help='h', label_names=('route', 'status'))

    def test_metric_name_is_unique_across_types(self) -> None:
        registry = MetricsRegistry()
        registry.counter('shared', help='h')
        with self.assertRaises(ValueError):
            registry.histogram('shared', help='h')

    def test_counter_rejects_name_already_registered_as_histogram(self) -> None:
        registry = MetricsRegistry()
        registry.histogram('shared', help='h')
        with self.assertRaises(ValueError):
            registry.counter('shared', help='h')

    def test_collect_yields_counters_then_histograms(self) -> None:
        registry = MetricsRegistry()
        registry.counter('alpha', help='h').inc()
        registry.histogram('beta', help='h').observe(0.1)
        names = [entry[0] for entry in registry.collect()]
        self.assertEqual(names, ['alpha', 'beta'])


if __name__ == '__main__':
    unittest.main()
