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

On push-to-master, propose the refreshed baseline instead of pushing to protected `master`. The workflow
commits the fresh JSON on `benchmarks/master-baseline` with the measured `master` commit as its parent,
then opens or updates a baseline-only pull request whose body names the measured SHA and workflow run.
A `RELEASE_TOKEN` personal access token publishes the branch and pull request so required CI runs on
them; the workflow adds no CI skip directive and never merges the pull request. It skips superseded
measurements and does not propose again for push ranges that change only the baseline. Pull requests,
including baseline pull requests, compare against the baseline committed on `origin/master`. Keep
`benchmarks/` excluded from coverage so performance probes do not dilute test coverage accounting.

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
- Each baseline refresh needs a personal access token so its branch and pull request trigger required CI,
  and waits for a maintainer to review and merge the baseline pull request.
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
