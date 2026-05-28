# ADR-0002: Queue Driver Registry — Built-ins + Entry Points

**Status:** Accepted
**Date:** 2026-05-28
**Sprint:** SPRINT-07

## Context

RouteMQ originally selected queue backends with a hardcoded `redis` or `database` branch in `QueueManager`. That was enough for built-in Redis and MySQL support, but it blocked third-party queue backends without editing framework internals.

Sprint 07 requires an extensibility path that keeps the built-ins stable while allowing applications or packages to register new queue drivers.

## Decision

Adopt a small queue driver registry in `QueueManager`:

1. **Built-in drivers stay first-class** — `redis` maps to `RedisQueue`; `database` maps to `DatabaseQueue`.
2. **Runtime registration is supported** — applications can call `QueueManager.register_driver(name, factory)`.
3. **Package plugins use entry points** — third-party distributions declare drivers under `[project.entry-points."routemq.queue_drivers"]`.
4. **Driver names are connection names** — `QUEUE_CONNECTION=<name>`, `QueueManager.get_driver(<name>)`, and worker `--connection <name>` use the same name.
5. **Drivers must inherit `QueueDriver`** — every backend implements the same async `push`, `pop`, `release`, `delete`, `failed`, and `size` contract.
6. **Built-ins cannot be overridden by entry points** — entry-point names that collide with existing registrations are skipped.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Keep hardcoded `if connection == ...` branches | Every new backend would require framework edits and releases. |
| Load all `routemq.queue_drivers` eagerly at import time | Import-time plugin loading makes tests slower and can trigger user package side effects too early. |
| Allow arbitrary callable objects without validation | Misconfigured plugins would fail later in workers with harder-to-debug errors. |
| Allow entry points to override built-ins | Built-in `redis` and `database` behavior should remain deterministic. |

## Consequences

### Positive

- Third-party queue backends can ship independently.
- Built-in drivers keep the existing connection names.
- Unit tests can register fake drivers without Redis/MySQL.
- Plugin discovery follows standard Python packaging metadata.

### Negative

- Plugin authors must package drivers correctly with `pyproject.toml` entry points.
- Entry-point loading adds a small first-use cost.
- Custom drivers must match RouteMQ worker semantics, including retry and failed-job behavior.

## References

- Source: `routemq/queue/queue_manager.py`
- Contract: `routemq/queue/queue_driver.py`
- Metadata: `pyproject.toml`
- Python `importlib.metadata.entry_points` documentation
- PyPA entry-points specification
