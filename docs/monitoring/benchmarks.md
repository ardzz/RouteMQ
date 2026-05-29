# Benchmark Harness

RouteMQ keeps performance checks separate from the default unittest suite. Benchmarks run with
`pytest-benchmark` under `benchmarks/` and measure framework hot paths that are useful before tuning:

- router compilation, route matching, misses, and middleware chain depth;
- job serialization, deserialization, and queue observability context capture;
- queue worker pop/process/retry paths with an in-memory fake driver;
- observability context snapshots and span hook fanout.

## Running benchmarks locally

```bash
make bench
```

The target runs:

```bash
uv run pytest benchmarks/ --benchmark-only
```

This is intentionally separate from `uv run python run_tests.py`, which only runs the regular
unittest suite and does not collect benchmark files.

## Baselines

The tracked baseline lives at `benchmarks/baselines/master.json` and is refreshed from the `master`
branch benchmark workflow. To regenerate it locally:

```bash
make bench-save
```

Branch-specific benchmark JSON files should not be committed. Only `master.json` is tracked.

## Regression gate

The benchmark workflow runs on pull requests targeting `master`, pushes to `master`, and manual
dispatches. Documentation-only changes are ignored by the trigger path filter.

Pull requests compare their fresh benchmark JSON against `benchmarks/baselines/master.json`. The
initial gate fails only when mean runtime regresses by more than 20 percent for a benchmark with a
matching baseline entry. That threshold is deliberately broad while CI variance is observed.

Pushes to `master` replace the baseline with the fresh benchmark run and commit it back with the
repository release token so future pull requests compare against the newest mainline result.

## Reading results

Focus on relative changes against the same benchmark name rather than absolute nanoseconds from one
machine. CI runners are noisy; a local laptop and GitHub runner should not be compared directly.

When a benchmark regresses:

1. reproduce with `make bench`;
2. inspect the benchmark group shown in the workflow output;
3. compare the changed hot path to the closest previous commit;
4. tune in a dedicated follow-up rather than mixing measurement and optimization in one change.
