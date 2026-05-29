"""Standalone SQLAlchemy pool-tuning matrix sweep for the database queue driver.

Not a pytest test (no ``test_`` prefix) so the benchmark CI job never collects it. Run
locally with Docker to produce reproducible pool-tuning evidence:

    RUN_INTEGRATION_TESTS=1 uv run python benchmarks/db_matrix.py --out docs/monitoring/pool-tuning.evidence.json

Each matrix cell reconfigures ``Model`` with a pool permutation, drives a fixed
push/round-trip workload against one shared containerized MySQL, and records throughput
and latency percentiles. The relative ranking across cells is the comparison signal, not
the absolute numbers (which depend on the host).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from importlib import import_module
from typing import Any

from routemq.model import Model

POOL_SIZES = (5, 10, 20)
MAX_OVERFLOWS = (0, 10, 20)
PRE_PINGS = (True, False)

WARMUP_OPS = 20
MEASURE_OPS = 200
CONCURRENCY = 20

_PAYLOAD = '{"class_path": "bench.Job", "instance_dict": {}, "attempts": 0}'


async def _measure_cell(driver: Any, queue: str) -> dict[str, float]:
    for _ in range(WARMUP_OPS):
        await driver.push(_PAYLOAD, queue=queue)

    latencies: list[float] = []
    start = time.perf_counter()

    async def _timed_push() -> None:
        op_start = time.perf_counter()
        await driver.push(_PAYLOAD, queue=queue)
        latencies.append(time.perf_counter() - op_start)

    for batch_start in range(0, MEASURE_OPS, CONCURRENCY):
        batch = min(CONCURRENCY, MEASURE_OPS - batch_start)
        await asyncio.gather(*(_timed_push() for _ in range(batch)))

    elapsed = time.perf_counter() - start
    ordered = sorted(latencies)
    return {
        'throughput_ops_per_s': round(MEASURE_OPS / elapsed, 2),
        'mean_latency_ms': round(statistics.fmean(latencies) * 1000, 4),
        'p95_latency_ms': round(ordered[int(len(ordered) * 0.95) - 1] * 1000, 4),
        'max_latency_ms': round(max(latencies) * 1000, 4),
    }


async def _run_cell(url: str, pool_size: int, max_overflow: int, pre_ping: bool, cell_index: int) -> dict[str, Any]:
    Model._is_enabled = True
    Model.configure(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pre_ping,
    )
    import_module('routemq.queue.models')
    database_queue_cls = import_module('routemq.queue.database_queue').DatabaseQueue

    await Model.create_tables()
    driver = database_queue_cls()
    queue = f'matrix-{cell_index}'
    try:
        stats = await _measure_cell(driver, queue)
    finally:
        await Model.cleanup()

    return {
        'pool_size': pool_size,
        'max_overflow': max_overflow,
        'pre_ping': pre_ping,
        **stats,
    }


def _select_default(cells: list[dict[str, Any]]) -> dict[str, Any]:
    best = max(cell['throughput_ops_per_s'] for cell in cells)
    threshold = best * 0.95
    eligible = [cell for cell in cells if cell['throughput_ops_per_s'] >= threshold]
    eligible.sort(key=lambda cell: (cell['pool_size'], cell['max_overflow'], not cell['pre_ping']))
    chosen = eligible[0]
    return {
        'rule': 'smallest pool_size within 5% of max throughput; tie-break lower max_overflow then pre_ping=true',
        'max_throughput_ops_per_s': best,
        'threshold_ops_per_s': round(threshold, 2),
        'pool_size': chosen['pool_size'],
        'max_overflow': chosen['max_overflow'],
        'pre_ping': chosen['pre_ping'],
        'throughput_ops_per_s': chosen['throughput_ops_per_s'],
    }


def _run_matrix() -> dict[str, Any]:
    os = import_module('os')
    if os.environ.get('RUN_INTEGRATION_TESTS', '').lower() not in {'1', 'true', 'yes', 'on'}:
        raise SystemExit('Set RUN_INTEGRATION_TESTS=1 (and ensure Docker is running) to sweep the pool matrix.')

    os.environ['ENABLE_MYSQL'] = 'true'
    mysql_container_cls = import_module('testcontainers.mysql').MySqlContainer
    container = mysql_container_cls('mysql:8.0', dialect='aiomysql')
    container.start()
    cells: list[dict[str, Any]] = []
    try:
        url = container.get_connection_url()
        index = 0
        for pool_size in POOL_SIZES:
            for max_overflow in MAX_OVERFLOWS:
                for pre_ping in PRE_PINGS:
                    cells.append(asyncio.run(_run_cell(url, pool_size, max_overflow, pre_ping, index)))
                    index += 1
    finally:
        container.stop()

    return {
        'workload': {
            'measure_ops': MEASURE_OPS,
            'warmup_ops': WARMUP_OPS,
            'concurrency': CONCURRENCY,
            'operation': 'database_queue.push',
        },
        'cells': cells,
        'recommended_default': _select_default(cells),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Sweep SQLAlchemy pool settings against the database queue.')
    parser.add_argument('--out', default='docs/monitoring/pool-tuning.evidence.json')
    args = parser.parse_args()

    evidence = _run_matrix()
    with open(args.out, 'w', encoding='utf-8') as handle:
        json.dump(evidence, handle, indent=2)
        handle.write('\n')
    print(f'Wrote {len(evidence["cells"])} matrix cells to {args.out}')
    print(f'Recommended default: {evidence["recommended_default"]}')


if __name__ == '__main__':
    main()
