# ADR-0007: Benchmark Harness and Regression Gate

**Status:** Accepted
**Date:** 2026-05-29
**Sprint:** Sprint 06D

## Context

RouteMQ had a small standard-library benchmark harness under `benchmarks/` using `time.perf_counter_ns`.
That was useful for local timing checks but not enough for release-candidate conformance. It did not cover
async benchmarks, did not run in CI as a gate, and did not compare pull requests against a committed
baseline.

The framework needed performance evidence that could catch regressions before merge while remaining
separate from the canonical `unittest` flow used by `run_tests.py`.

## Decision

Migrate benchmarking to `pytest-benchmark` and `pytest-async-benchmark` as development dependencies.

Add a dedicated `bench` CI job that runs on pull requests and on pushes to `master`. The job compares PR
results against the committed `benchmarks/baselines/master.json` baseline and fails on a 20% mean
regression gate.

On push-to-master, refresh the baseline through a `RELEASE_TOKEN` personal access token using the same
downstream-workflow pattern as the release tag push. Keep `benchmarks/` excluded from coverage so
performance probes do not dilute test coverage accounting.

Benchmark discovery remains explicit: `pytest benchmarks/ --benchmark-only` collects the benchmark suite,
while the normal `python run_tests.py` path continues to use `unittest.discover` and does not collect
benchmark tests.

## Consequences

### Positive

- Every pull request carries a performance delta signal.
- The baseline is a small committed JSON artifact, reviewable like other conformance evidence.
- Async framework paths can be measured with the same CI affordances as synchronous paths.
- Developers get repeatable local commands via `make bench`, `make bench-compare`, and `make bench-save`.

### Negative

- CI now has a dedicated performance job with normal runtime variability.
- Baseline refresh requires a token that can trigger downstream workflows after protected-branch merges.
- A 20% mean gate catches large regressions but does not replace deeper profiling or long-term trend
  analysis.

## Status

Accepted in Sprint 06D via PR #67.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| `asv` / Airspeed Velocity | Strong for long-term multi-commit history, but heavier than this sprint needed; deferred for a future performance-history sprint. |
| `richbench` | Lightweight and developer-friendly, but did not provide the CI gating and comparison path needed here. |
| Keep the stdlib harness | No async benchmark support and no first-class regression gate. |

## Related

- PR #67: Sprint 06D benchmark harness, baseline, and CI regression gate.
