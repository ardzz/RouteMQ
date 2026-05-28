"""Retry and bounded exponential backoff helpers for RouteMQ.

The helpers are intentionally stdlib-only and pure where practical so tests can
inject seeded RNGs and fake sleep functions without relying on wall-clock time.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar


T = TypeVar('T')

SleepFn = Callable[[float], None]
RngFn = Callable[[], float]


@dataclass(frozen=True)
class BackoffConfig:
    """Configuration for bounded exponential backoff delays."""

    min_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.0

    def __post_init__(self) -> None:
        if self.min_delay < 0:
            raise ValueError('min_delay must be >= 0')
        if self.max_delay < self.min_delay:
            raise ValueError('max_delay must be >= min_delay')
        if self.jitter < 0:
            raise ValueError('jitter must be >= 0')


@dataclass(frozen=True)
class RetryConfig(BackoffConfig):
    """Configuration for retrying a synchronous operation."""

    max_attempts: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.max_attempts < 1:
            raise ValueError('max_attempts must be >= 1')


def bounded_exponential_backoff(attempt: int, config: BackoffConfig, rng: RngFn | None = None) -> float:
    """Return a bounded exponential delay for a 1-based retry attempt.

    ``attempt=1`` returns ``min_delay`` before jitter. The exponential value is
    capped at ``max_delay``. ``jitter=0`` is deterministic. ``jitter>=1`` applies
    full jitter (uniform ``[0, capped_delay]``). Values between 0 and 1 keep at
    least ``(1 - jitter)`` of the capped delay.
    """

    if attempt < 1:
        raise ValueError('attempt must be >= 1')

    delay = min(config.max_delay, config.min_delay * (2 ** (attempt - 1)))
    if delay <= 0 or config.jitter <= 0:
        return delay

    random_value = (rng or random.random)()
    if random_value < 0 or random_value > 1:
        raise ValueError('rng must return a float between 0 and 1')

    jitter = min(config.jitter, 1.0)
    lower_bound = delay * (1.0 - jitter)
    return lower_bound + ((delay - lower_bound) * random_value)


def retry_sync(
    operation: Callable[[], T],
    *,
    config: RetryConfig,
    retryable: Callable[[BaseException], bool],
    sleep: SleepFn = time.sleep,
    rng: RngFn | None = None,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Run ``operation`` with bounded retry sleeps for retryable failures.

    ``max_attempts`` includes the first attempt. ``on_retry`` receives the
    failed attempt number, exception, and planned sleep duration.
    """

    attempt = 1
    while True:
        try:
            return operation()
        except BaseException as exc:
            if attempt >= config.max_attempts or not retryable(exc):
                raise
            delay = bounded_exponential_backoff(attempt, config, rng)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep(delay)
            attempt += 1
