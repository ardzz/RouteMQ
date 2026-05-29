# ADR-0010: TSDB Integration — Internal Driver Contract, ClickHouse First

**Status:** Accepted
**Date:** 2026-05-29
**Sprint:** SPRINT-08

## Context

RouteMQ ingests MQTT telemetry but has no first-class path to persist it into a
time-series database (TSDB). Applications such as pump/sensor monitoring need to land
high-volume telemetry for later analytics.

Four backends were evaluated: TimescaleDB, InfluxDB, ClickHouse, and Apache IoTDB. Their
data models diverge significantly (relational hypertables, tag/field line protocol,
columnar `MergeTree`, time-series paths), so a single public driver contract spanning all
four risks a leaky abstraction. The existing queue driver registry (ADR-0002) provides a
proven extensibility template, but committing a public TSDB driver contract before a
second backend exists would lock in an unproven shape.

## Decision

Ship a single backend behind a small, **internal and unstable** driver contract; defer
the public registry.

1. **ClickHouse first** — purpose-built for high-ingest telemetry analytics. Shipped via
   the optional `routemq[clickhouse]` extra (`clickhouse-connect[async]`).
2. **Backend-specific extra, not a generic umbrella** — `routemq[clickhouse]`, never
   `routemq[tsdb]`, matching ecosystem precedent.
3. **Internal driver contract** — `TSDBDriver` is an `abc.ABC` mirroring `QueueDriver`,
   but it is **not** a public, SemVer-stable API yet. It may change without a major bump
   until a second backend validates it.
4. **Write-path contract + native query escape hatch** — drivers expose `connect`,
   `close`, `ensure_schema`, `write_points`, `flush`, `health`, and a native `client`
   property. Reads are not unified; applications query through the native client.
5. **Application owns DDL** — `ensure_schema` validates that a table exists with the
   expected columns and fails fast; it never creates or alters tables.
6. **In-process buffered writes** — `TSDBManager` (a singleton mirroring `RedisManager`)
   buffers points in a bounded `asyncio.Queue` and flushes batches on size or time, using
   ClickHouse `async_insert` as a server-side safety net.
7. **Public `routemq.tsdb_drivers` entry-point registry is deferred** — to be extracted
   (using the ADR-0002 machinery) once a second backend lands.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Build the public `routemq.tsdb_drivers` registry now | Commits a SemVer-stable driver contract across four divergent data models before any second backend has validated it. |
| Generic `routemq[tsdb]` umbrella extra | Pulls heavy backend clients users do not want; ecosystem precedent favors `pkg[backend]`. |
| Unified structured query API across backends | Aggregation/downsampling/time-bucketing semantics differ enough to force a lowest-common-denominator or backend-specific escape hatches anyway. |
| Framework-generated DDL | `MergeTree` `ORDER BY`/partition choices dominate performance and cannot be chosen well for an unknown workload. |
| Durable per-point queue for writes | Sensor telemetry favors write-availability over guaranteed delivery; per-point queue overhead is heavy and still needs in-worker batching. |
| Ship Apache IoTDB in v1 | Its Python client is a sync-only Thrift session that would block the asyncio event loop; deferred until an `asyncio.to_thread` wrapper exists. |

## Consequences

### Positive

- ClickHouse telemetry persistence ships without committing a premature public contract.
- The internal contract can evolve freely until a second backend proves it.
- `TSDBManager` reuses the established optional-service lifecycle (`ENABLE_TSDB`, singleton,
  `initialize`/`disconnect`/`is_enabled`).
- Observability reuses the existing `kind='client'` span seam and metrics-hook recipes.

### Negative

- No public plugin path for third-party TSDB backends yet.
- Apache IoTDB and InfluxDB/TimescaleDB remain roadmap items.
- Buffer depth is exposed only as a span attribute and log line; a true Prometheus gauge
  is deferred (the stdlib registry supports only counters and histograms).
- In-process buffering can drop sub-second in-flight data on a hard crash (documented).

## References

- Contract: `routemq/tsdb/tsdb_driver.py`
- Driver: `routemq/tsdb/clickhouse_driver.py`
- Lifecycle: `routemq/tsdb/tsdb_manager.py`
- Template: `docs/adr/0002-queue-driver-registry.md`
- ClickHouse async inserts: https://clickhouse.com/docs/cloud/bestpractices/asynchronous-inserts
- OpenTelemetry database spans: https://opentelemetry.io/docs/specs/semconv/database/database-spans/
