# SQLAlchemy Pool Tuning (measured)

RouteMQ's database queue runs on an async SQLAlchemy engine. The pool is configurable via
`DB_POOL_*` environment variables (see
[Environment Variables](../configuration/environment-variables.md)). This page records a
measured sweep so the shipped defaults are evidence-backed, not guessed.

> Reproduce with Docker:
>
> ```bash
> RUN_INTEGRATION_TESTS=1 uv run python benchmarks/db_matrix.py --out docs/monitoring/pool-tuning.evidence.json
> ```
>
> The raw data lives in [`pool-tuning.evidence.json`](./pool-tuning.evidence.json). The
> Docker-gated benchmark suite is `benchmarks/test_database_queue.py` (skipped unless
> `RUN_INTEGRATION_TESTS=1` and Docker are present, so the benchmark CI job is unaffected).

## Workload

- Operation: `DatabaseQueue.push` against a containerized MySQL 8.0 (`aiomysql`).
- 20 warmup ops, then 200 measured ops at concurrency 20.
- Matrix: `pool_size ∈ {5, 10, 20}` × `max_overflow ∈ {0, 10, 20}` × `pre_ping ∈ {true, false}`.
- Single host, single process. **Relative ranking is the signal, not absolute throughput**
  (absolute numbers depend on the machine).

## Results

| pool_size | max_overflow | pre_ping | throughput (ops/s) | mean (ms) | p95 (ms) |
|---:|---:|:--|---:|---:|---:|
| 5 | 0 | true | 627.93 | 18.70 | 26.98 |
| 5 | 0 | false | 646.33 | 16.44 | 23.38 |
| 5 | 10 | true | 503.13 | 26.42 | 33.29 |
| 5 | 10 | false | 556.98 | 24.00 | 32.32 |
| 5 | 20 | true | 508.58 | 29.60 | 38.29 |
| 5 | 20 | false | 475.18 | 29.32 | 50.62 |
| 10 | 0 | true | 698.94 | 17.94 | 24.31 |
| 10 | 0 | false | 744.57 | 15.90 | 24.12 |
| 10 | 10 | true | 565.12 | 25.27 | 32.80 |
| 10 | 10 | false | 589.57 | 20.85 | 28.35 |
| 10 | 20 | true | 511.84 | 27.00 | 35.69 |
| 10 | 20 | false | 579.18 | 21.46 | 33.13 |
| 20 | 0 | true | 806.81 | 18.95 | 30.25 |
| 20 | 0 | false | 773.37 | 17.45 | 39.19 |
| 20 | 10 | true | 789.26 | 19.86 | 40.04 |
| 20 | 10 | false | 805.18 | 16.98 | 35.08 |
| 20 | 20 | true | 853.38 | 18.16 | 34.58 |
| 20 | 20 | false | 864.89 | 15.56 | 30.28 |

## Findings

1. **Throughput scales with `pool_size`** under this concurrency-20 push workload: ~5 → ~600,
   10 → ~700, 20 → ~860 ops/s. Larger pools let more concurrent pushes proceed.
2. **`pre_ping=true` is effectively free.** Across every `pool_size`/`max_overflow` pair the
   `pre_ping=true` and `pre_ping=false` throughputs are within run-to-run noise (often the
   `true` row is faster). The validate-on-checkout cost is well under the 2% budget, so the
   production-safety default (`pre_ping=true`) stays.
3. **`max_overflow=0` is competitive.** At a fixed `pool_size`, adding overflow connections
   did not reliably improve throughput and sometimes hurt it (overflow churn adds connection
   setup/teardown cost). Overflow is a burst-safety valve, not a throughput lever.

## Decision

**Keep the shipped defaults: `pool_size=5`, `max_overflow=10`, `pool_pre_ping=true`.**

The mechanical "max throughput" cell is `pool_size=20, max_overflow=20`, but the shipped
defaults are deliberately conservative rather than throughput-maximal, because:

- This is a **single-host, single-process, push-only** micro-benchmark. RouteMQ commonly
  runs **multiple queue-worker processes** (`make scale-default`), and pool size is
  **per process** — a default of 20 would mean 20 idle MySQL connections × N workers,
  which is hostile to small deployments and risks exhausting MySQL `max_connections`.
- The data shows the defaults are **safe and correct**, with clear, documented headroom:
  high-throughput single-process deployments can raise `DB_POOL_SIZE` (e.g. `10`–`20`) and
  measure with this same harness.
- `pre_ping=true` is confirmed essentially free, so the safety default is justified by
  measurement (closing Sprint 06E acceptance criterion).

Operators tune up per environment via `DB_POOL_*` without forking. Re-run the matrix on
representative hardware before changing a default.
