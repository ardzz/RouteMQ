from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable


def measure_ns(fn: Callable[[], object], *, iterations: int = 1000, rounds: int = 5) -> dict[str, float]:
    samples: list[int] = []
    for _ in range(rounds):
        started = time.perf_counter_ns()
        for _ in range(iterations):
            fn()
        samples.append((time.perf_counter_ns() - started) // iterations)
    return {
        'min_ns': min(samples),
        'median_ns': statistics.median(samples),
        'mean_ns': statistics.mean(samples),
    }


def print_result(name: str, result: dict[str, float]) -> None:
    print(f'{name}: min={result["min_ns"]:.0f}ns median={result["median_ns"]:.0f}ns mean={result["mean_ns"]:.0f}ns')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run a RouteMQ stdlib benchmark.')
    parser.add_argument('--iterations', type=int, default=1000, help='iterations per benchmark round')
    parser.add_argument('--rounds', type=int, default=5, help='number of benchmark rounds')
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error('--iterations must be >= 1')
    if args.rounds < 1:
        parser.error('--rounds must be >= 1')
    return args
