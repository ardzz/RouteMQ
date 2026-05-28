from __future__ import annotations

from typing import Any

import pytest

from routemq.observability import (
    clear_hooks,
    register_span_hook,
    reset_context,
    set_context,
    snapshot_context,
    start_span,
)


def _set_and_reset_context() -> None:
    token = set_context({'trace_id': 'a' * 32, 'span_id': 'b' * 16}, correlation_id='benchmark-correlation')
    reset_context(token)


def _start_span_once() -> None:
    with start_span('benchmark.span', {'component': 'benchmark'}):
        pass


@pytest.mark.benchmark(group='observability-context')
def bench_snapshot_context_no_span(benchmark) -> None:
    benchmark(snapshot_context)


@pytest.mark.benchmark(group='observability-context')
def bench_snapshot_context_with_span(benchmark) -> None:
    token = set_context({'route': 'devices/{device_id}/status'}, correlation_id='benchmark-correlation')
    try:
        with start_span('benchmark.parent', {'component': 'benchmark'}):
            benchmark(snapshot_context)
    finally:
        reset_context(token)


@pytest.mark.benchmark(group='observability-context')
def bench_set_and_reset_context(benchmark) -> None:
    benchmark(_set_and_reset_context)


@pytest.mark.benchmark(group='observability-span')
def bench_start_span_noop(benchmark, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ENABLE_TRACING', 'false')

    benchmark(_start_span_once)


@pytest.mark.benchmark(group='observability-span')
def bench_start_span_with_hook(benchmark, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('ENABLE_TRACING', raising=False)
    seen: list[str] = []
    unregister = register_span_hook(lambda snapshot: seen.append(snapshot.name))
    try:
        benchmark(_start_span_once)
    finally:
        unregister()
        clear_hooks()


@pytest.mark.benchmark(group='observability-span')
def bench_start_span_with_10_hooks(benchmark, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('ENABLE_TRACING', raising=False)
    seen: list[Any] = []
    unregister_callbacks = [
        register_span_hook(lambda snapshot, bucket=seen: bucket.append(snapshot.span_id)) for _ in range(10)
    ]
    try:
        benchmark(_start_span_once)
    finally:
        for unregister in unregister_callbacks:
            unregister()
        clear_hooks()
