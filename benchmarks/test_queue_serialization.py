from __future__ import annotations

from collections.abc import Callable

import pytest

from routemq.job import Job
from routemq.observability import reset_context, set_context, start_span

from .conftest import BenchmarkJob


@pytest.mark.benchmark(group='queue-serialization')
def bench_job_serialize(benchmark, make_job: Callable[..., BenchmarkJob]) -> None:
    job = make_job(10)

    benchmark(job.serialize)


@pytest.mark.benchmark(group='queue-serialization')
def bench_job_serialize_large(benchmark, make_job: Callable[..., BenchmarkJob]) -> None:
    job = make_job(100)

    benchmark(job.serialize)


@pytest.mark.benchmark(group='queue-serialization')
def bench_job_unserialize(benchmark, make_job: Callable[..., BenchmarkJob]) -> None:
    payload = make_job(10).serialize()

    benchmark(lambda: Job.unserialize(payload))


@pytest.mark.benchmark(group='queue-serialization')
def bench_job_unserialize_large(benchmark, make_job: Callable[..., BenchmarkJob]) -> None:
    payload = make_job(100).serialize()

    benchmark(lambda: Job.unserialize(payload))


@pytest.mark.benchmark(group='queue-observability')
def bench_capture_observability_context_empty(benchmark, make_job: Callable[..., BenchmarkJob]) -> None:
    job = make_job(10)

    benchmark(job.capture_observability_context)


@pytest.mark.benchmark(group='queue-observability')
def bench_capture_observability_context_populated(benchmark, make_job: Callable[..., BenchmarkJob]) -> None:
    job = make_job(10)
    token = set_context(
        {'trace_id': 'a' * 32, 'span_id': 'b' * 16, 'trace_flags': '01'},
        correlation_id='benchmark-correlation-id',
    )
    try:
        with start_span('benchmark.parent', {'queue': 'default'}, kind='producer'):
            benchmark(lambda: job.capture_observability_context({'queue': 'default'}))
    finally:
        reset_context(token)
