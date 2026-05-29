# RouteMQ Benchmarks

Benchmarks use `pytest-benchmark` and live outside the default unittest discovery path.

## Commands

```bash
make bench          # run all benchmarks
make bench-save     # write benchmarks/baselines/master.json
make bench-compare  # compare against the tracked baseline
```

Direct invocation:

```bash
uv run pytest benchmarks/ --benchmark-only
uv run pytest benchmarks/test_router.py --benchmark-only
```

## Layout

- `conftest.py` supplies shared async benchmarking, router, job, and fake queue driver factories.
- `test_router.py` covers route compilation and dispatch costs.
- `test_queue_serialization.py` covers job payload conversion and context capture.
- `test_queue_worker.py` covers real pop/process cycles with an in-memory fake driver.
- `test_observability.py` covers context snapshots and span hook fanout.
- `baselines/master.json` is the only committed baseline.

Benchmark files are excluded from coverage reports so measurement helpers do not affect the project
coverage floor.
