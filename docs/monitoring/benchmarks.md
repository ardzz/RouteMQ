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

The tracked baseline lives at `benchmarks/baselines/master.json`. The `master` branch benchmark
workflow updates it only through a baseline-only pull request, described under the regression gate
below. `make bench-save` writes a local run to the same path:

```bash
make bench-save
```

Use that output for local comparison only. Absolute timings from a laptop and a GitHub-hosted runner
differ, so local output cannot calibrate the CI gate. Before adopting any baseline data, confirm it
came from an environment comparable to the hosted runner and that its source commit and run are
recorded.

Branch-specific benchmark JSON files should not be committed. Only `master.json` is tracked.

## Regression gate

The benchmark workflow runs on pull requests targeting `master`, pushes to `master`, and manual
dispatches. Documentation-only changes are ignored by the trigger path filter.

Pull requests compare their fresh benchmark JSON against `benchmarks/baselines/master.json` as
committed on `origin/master`, never against a copy on the PR branch. Baseline PRs follow the same
rule. The initial gate fails only when mean runtime regresses by more than 20 percent for a benchmark
with a matching baseline entry. That threshold is deliberately broad while CI variance is observed.

Protected `master` requires status checks on each new commit. A successful push-to-`master` run
proposes its result through a PR instead of pushing an unchecked commit. The workflow commits
the fresh JSON on the `benchmarks/master-baseline`
branch with the measured `master` commit as its parent, then opens or updates one baseline-only PR
whose body names the measured commit SHA and links the workflow run. The branch push uses an explicit
lease, so a concurrent update to that branch fails the run instead of being overwritten.
`RELEASE_TOKEN`, a personal access token, publishes the branch and PR so the normal required CI runs
on them. The workflow never pushes to `master`, adds no CI skip directive, and does not merge the PR;
a maintainer reviews and merges it like any other change.

The workflow publishes nothing when:

- `master` moved past the measured commit before publication, because a newer run supersedes it;
- the push range changes only `benchmarks/baselines/master.json`, such as a merged baseline PR.
  Benchmarks and CI still run; only another proposal is skipped;
- the fresh JSON matches the committed baseline.

Manual dispatches only measure. They neither compare against the baseline nor propose a new one.

## Reading results

Focus on relative changes against the same benchmark name rather than absolute nanoseconds from one
machine. CI runners are noisy; a local laptop and GitHub runner should not be compared directly.

When a benchmark regresses:

1. reproduce with `make bench`;
2. inspect the benchmark group shown in the workflow output;
3. compare the changed hot path to the closest previous commit;
4. tune in a dedicated follow-up rather than mixing measurement and optimization in one change.
