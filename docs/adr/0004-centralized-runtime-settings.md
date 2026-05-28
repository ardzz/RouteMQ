# ADR-0004: Centralized Runtime Settings — Typed Loaders, Lazy Reads

**Status:** Accepted
**Date:** 2026-05-28
**Sprint:** SPRINT-07

## Context

RouteMQ historically read environment variables directly at each call site. That kept early framework code simple, but it spread parsing rules across MQTT helpers, health checks, queue workers, and future runtime integrations.

Sprint 07 needs a safer extension path for configuration without changing runtime behavior for existing applications.

## Decision

Add `routemq/settings.py` as a dependency-light runtime settings layer:

1. **Use stdlib dataclasses** — settings groups are frozen dataclasses with explicit fields.
2. **Keep environment reads lazy** — loaders read `os.environ` only when called, not at module import time.
3. **Allow injected mappings in tests** — loaders accept `Mapping[str, str]` so unit tests avoid mutating global environment state when possible.
4. **Preserve existing parsing behavior** — boolean truth values remain `1`, `true`, `yes`, and `on`; invalid retry and health numeric values fall back to defaults; invalid `MQTT_PORT` still raises `ValueError`.
5. **Migrate low-risk runtime readers first** — MQTT helpers, health HTTP settings, and queue retry backoff use the centralized loaders.
6. **Avoid import-time singleton migrations for now** — Redis, database, queue manager, and application bootstrap configuration stay on direct env reads until each area has a targeted migration.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Keep direct `os.getenv` calls everywhere | Parsing behavior remains duplicated and hard to test consistently. |
| Adopt `pydantic-settings` immediately | It adds a dependency and validation semantics before the framework has settled its public configuration contract. |
| Migrate every env reader in one sweep | Import-time and singleton-backed modules need extra sequencing to avoid boot regressions. |
| Cache settings globally | Tests and long-running processes need predictable lazy reads after env changes. |

## Consequences

### Positive

- Runtime configuration parsing now has one tested home for migrated settings.
- New env-backed runtime features can share the same parser helpers.
- Tests can cover parsing rules without live Redis, MySQL, or MQTT services.
- Import-time env reads are less likely to spread into new framework modules.

### Negative

- The framework temporarily has both centralized and legacy env readers.
- Call sites that need legacy dataclass shapes still adapt from the new settings objects.
- Future broad migrations require separate compatibility checks for singleton lifecycles.

## References

- Source: `routemq/settings.py`
- MQTT migration: `routemq/mqtt_utils.py`
- Health migration: `routemq/health.py`
- Queue retry migration: `routemq/queue/queue_worker.py`
- Tests: `tests/unit/core/test_settings.py`
