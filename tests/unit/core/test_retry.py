import random
import unittest

from routemq.retry import BackoffConfig, RetryConfig, bounded_exponential_backoff, retry_sync


class RetryBackoffTests(unittest.TestCase):
    def test_bounded_exponential_backoff_clamps_to_max_delay(self) -> None:
        config = BackoffConfig(min_delay=2, max_delay=10, jitter=0)

        self.assertEqual(bounded_exponential_backoff(1, config), 2)
        self.assertEqual(bounded_exponential_backoff(2, config), 4)
        self.assertEqual(bounded_exponential_backoff(4, config), 10)

    def test_full_jitter_uses_injected_rng(self) -> None:
        config = BackoffConfig(min_delay=8, max_delay=30, jitter=1)

        self.assertEqual(bounded_exponential_backoff(1, config, rng=lambda: 0.25), 2)

    def test_fractional_jitter_keeps_lower_bound(self) -> None:
        config = BackoffConfig(min_delay=10, max_delay=30, jitter=0.2)

        self.assertEqual(bounded_exponential_backoff(1, config, rng=lambda: 0), 8)
        self.assertEqual(bounded_exponential_backoff(1, config, rng=lambda: 1), 10)

    def test_seeded_rng_is_deterministic(self) -> None:
        config = BackoffConfig(min_delay=5, max_delay=30, jitter=1)
        rng_a = random.Random(7)
        rng_b = random.Random(7)

        self.assertEqual(
            bounded_exponential_backoff(3, config, rng=rng_a.random),
            bounded_exponential_backoff(3, config, rng=rng_b.random),
        )

    def test_invalid_attempt_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            bounded_exponential_backoff(0, BackoffConfig())


class RetrySyncTests(unittest.TestCase):
    def test_retry_sync_sleeps_between_retryable_failures(self) -> None:
        calls = 0
        sleeps: list[float] = []

        def operation() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ConnectionRefusedError('down')
            return 'ok'

        result = retry_sync(
            operation,
            config=RetryConfig(max_attempts=3, min_delay=1, max_delay=5, jitter=0),
            retryable=lambda exc: isinstance(exc, ConnectionRefusedError),
            sleep=sleeps.append,
        )

        self.assertEqual(result, 'ok')
        self.assertEqual(sleeps, [1, 2])

    def test_retry_sync_reraises_non_retryable_without_sleep(self) -> None:
        sleeps: list[float] = []

        with self.assertRaises(ValueError):
            retry_sync(
                lambda: (_ for _ in ()).throw(ValueError('bad')),
                config=RetryConfig(max_attempts=3),
                retryable=lambda exc: isinstance(exc, ConnectionError),
                sleep=sleeps.append,
            )

        self.assertEqual(sleeps, [])


if __name__ == '__main__':
    unittest.main()
