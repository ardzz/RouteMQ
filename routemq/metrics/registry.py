"""In-memory MetricsRegistry used by RouteMQ's stdlib OpenMetrics writer.

The registry intentionally exposes only counter and histogram primitives. Gauge,
Info, and Enum types are deferred to the optional ``routemq[prometheus]`` adapter
because their multiprocess semantics require the official client library.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

LabelKey = tuple[tuple[str, str], ...]


DEFAULT_HISTOGRAM_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _to_label_key(label_names: Sequence[str], labels: Mapping[str, Any] | None) -> LabelKey:
    if not label_names:
        return ()
    values = labels or {}
    return tuple((name, str(values.get(name, ''))) for name in label_names)


@dataclass(frozen=True)
class Sample:
    """One emitted line of an exposition: (name suffix, labels, value)."""

    name_suffix: str
    label_key: LabelKey
    value: float


@dataclass
class Counter:
    """Monotonic counter family.

    Counters are always non-negative and grow monotonically. The registry guards
    concurrent ``inc`` calls with a per-counter lock.
    """

    name: str
    help: str
    label_names: tuple[str, ...] = ()
    _values: dict[LabelKey, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, amount: float = 1.0, labels: Mapping[str, Any] | None = None) -> None:
        if amount < 0:
            raise ValueError(f'Counter {self.name!r} cannot decrease (got {amount})')
        key = _to_label_key(self.label_names, labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + float(amount)

    def collect(self) -> Iterable[Sample]:
        with self._lock:
            snapshot = dict(self._values)
        for key, value in snapshot.items():
            yield Sample(name_suffix='_total', label_key=key, value=value)


@dataclass
class HistogramObservation:
    """Bucket counts plus sum/count for a single labelset."""

    buckets: dict[float, float] = field(default_factory=dict)
    sum: float = 0.0
    count: float = 0.0


@dataclass
class Histogram:
    """Histogram family with cumulative bucket counts plus sum and count.

    Buckets are cumulative (``le=x`` includes every observation with value
    ``<= x``); the ``+Inf`` bucket is implicit and always equals ``count``.
    """

    name: str
    help: str
    bucket_bounds: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS
    label_names: tuple[str, ...] = ()
    _values: dict[LabelKey, HistogramObservation] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float, labels: Mapping[str, Any] | None = None) -> None:
        if value != value:
            raise ValueError(f'Histogram {self.name!r} cannot observe NaN')
        numeric = float(value)
        key = _to_label_key(self.label_names, labels)
        with self._lock:
            observation = self._values.get(key)
            if observation is None:
                observation = HistogramObservation(
                    buckets={bound: 0.0 for bound in self.bucket_bounds},
                )
                self._values[key] = observation
            for bound in self.bucket_bounds:
                if numeric <= bound:
                    observation.buckets[bound] = observation.buckets.get(bound, 0.0) + 1.0
            observation.sum += numeric
            observation.count += 1.0

    def collect(self) -> Iterable[Sample]:
        with self._lock:
            snapshot = {
                key: HistogramObservation(dict(obs.buckets), obs.sum, obs.count) for key, obs in self._values.items()
            }
        for key, observation in snapshot.items():
            for bound in self.bucket_bounds:
                yield Sample(
                    name_suffix='_bucket',
                    label_key=key + (('le', _format_bucket_bound(bound)),),
                    value=observation.buckets.get(bound, 0.0),
                )
            yield Sample(
                name_suffix='_bucket',
                label_key=key + (('le', '+Inf'),),
                value=observation.count,
            )
            yield Sample(name_suffix='_sum', label_key=key, value=observation.sum)
            yield Sample(name_suffix='_count', label_key=key, value=observation.count)


def _format_bucket_bound(bound: float) -> str:
    """Format a bucket upper bound for OpenMetrics text exposition.

    The OpenMetrics spec requires that bucket boundaries serialize without
    trailing zeros while still distinguishing integer-like values from their
    decimal counterparts.
    """

    if bound == float('inf'):
        return '+Inf'
    formatted = f'{bound:.6g}'
    if '.' not in formatted and 'e' not in formatted and 'E' not in formatted:
        formatted = f'{formatted}.0'
    return formatted


class MetricsRegistry:
    """Thread-safe registry of counter and histogram families."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(
        self,
        name: str,
        help: str,
        label_names: Sequence[str] = (),
    ) -> Counter:
        return self._get_or_create_counter(name, help, tuple(label_names))

    def histogram(
        self,
        name: str,
        help: str,
        label_names: Sequence[str] = (),
        bucket_bounds: Sequence[float] | None = None,
    ) -> Histogram:
        bounds = tuple(bucket_bounds) if bucket_bounds is not None else DEFAULT_HISTOGRAM_BUCKETS
        return self._get_or_create_histogram(name, help, tuple(label_names), bounds)

    def _get_or_create_counter(self, name: str, help: str, label_names: tuple[str, ...]) -> Counter:
        with self._lock:
            existing = self._counters.get(name)
            if existing is not None:
                if existing.label_names != label_names:
                    raise ValueError(f'Counter {name!r} already registered with labels {existing.label_names!r}')
                return existing
            if name in self._histograms:
                raise ValueError(f'Metric name {name!r} already registered as histogram')
            counter = Counter(name=name, help=help, label_names=label_names)
            self._counters[name] = counter
            return counter

    def _get_or_create_histogram(
        self,
        name: str,
        help: str,
        label_names: tuple[str, ...],
        bucket_bounds: tuple[float, ...],
    ) -> Histogram:
        with self._lock:
            existing = self._histograms.get(name)
            if existing is not None:
                if existing.label_names != label_names:
                    raise ValueError(f'Histogram {name!r} already registered with labels {existing.label_names!r}')
                if existing.bucket_bounds != bucket_bounds:
                    raise ValueError(f'Histogram {name!r} already registered with buckets {existing.bucket_bounds!r}')
                return existing
            if name in self._counters:
                raise ValueError(f'Metric name {name!r} already registered as counter')
            histogram = Histogram(
                name=name,
                help=help,
                bucket_bounds=bucket_bounds,
                label_names=label_names,
            )
            self._histograms[name] = histogram
            return histogram

    def collect(self) -> Iterable[tuple[str, str, str, Iterable[Sample]]]:
        with self._lock:
            counters = list(self._counters.values())
            histograms = list(self._histograms.values())
        for counter in counters:
            yield counter.name, 'counter', counter.help, counter.collect()
        for histogram in histograms:
            yield histogram.name, 'histogram', histogram.help, histogram.collect()
