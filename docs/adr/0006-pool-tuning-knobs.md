# ADR-0006: Database Pool Tuning Knobs

**Status:** Accepted
**Date:** 2026-05-29
**Sprint:** Sprint 06E

## Context

RouteMQ's `Model.configure` path called SQLAlchemy `create_async_engine` without exposing pool keyword
arguments. That kept the default path simple, but operators had no supported way to tune connection pool
behavior for different broker loads, queue worker counts, MySQL limits, or deployment topologies.

The framework needed a configuration seam that preserved the existing default behavior while allowing
deployments to express standard SQLAlchemy pool controls through environment variables. The setting
surface also had to stay typed and centralized rather than scattering raw environment parsing across the
bootstrap and model layers.

## Decision

Expose environment-driven `DB_POOL_*` knobs through a typed `DatabasePoolSettings` parser and thread the
result through `bootstrap/app.py` into `Model.configure`.

The parser owns coercion, defaults, and omission rules. The model layer receives explicit pool keyword
arguments instead of reading environment variables directly. Defaults align with SQLAlchemy async-engine
behavior, with two safer framework defaults: `pool_recycle=1800` and `pool_pre_ping=true`.

This keeps database pool tuning an application bootstrap concern while preserving `Model.configure` as the
single engine construction point.

## Consequences

### Positive

- Existing deployments get no required configuration change.
- Operators can tune standard SQLAlchemy pool controls without forking bootstrap code.
- Pool configuration is parsed once through a typed settings object, so future validation and docs changes
  have one owner.
- Queue-heavy deployments can avoid connection churn while still keeping stale connections guarded by
  `pool_pre_ping` and `pool_recycle`.

### Negative

- The defaults are conservative, not benchmark-derived for every workload.
- Operators can still misconfigure pool sizes relative to database limits; documentation and future
  benchmarks must guide safe values.
- The framework now exposes another operational surface that must remain backward compatible while RouteMQ
  approaches 1.0.

## Status

Accepted in Sprint 06E via PR #68. Bench-matrix-driven default revision is deferred until enough runtime
data exists to justify changing defaults.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Hard-coded defaults | Would keep simple deployments simple but leave production operators without standard tuning controls. |
| Custom pool implementation | Reimplements SQLAlchemy behavior and adds maintenance risk without solving a unique RouteMQ problem. |
| Read-only `NullPool` | Avoids pool sizing questions but kills connection reuse for the queue driver and high-throughput handlers. |

## Related

- PR #68: Sprint 06E pool tuning knobs and deferred benchmark matrix follow-up.
