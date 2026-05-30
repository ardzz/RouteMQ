# Time-Series Database (TSDB) Integration

RouteMQ can land MQTT telemetry into a time-series database for analytics. User code writes through the public `routemq.telemetry` API. Backend-specific adapters live under `routemq.tsdb` and currently support ClickHouse, TimescaleDB, InfluxDB, and Apache IoTDB.

The public write API is backend-neutral. Query APIs are not unified, so read paths still use the native database client or HTTP API for the backend you choose.

## Installation

```bash
uv add "routemq[clickhouse]"
```

This installs `clickhouse-connect[async]` for the ClickHouse adapter. TimescaleDB uses an async SQLAlchemy URL with the driver you install for PostgreSQL. InfluxDB and IoTDB adapters write to the HTTP endpoint set in `TELEMETRY_URL`.

## Configuration

Telemetry is disabled by default. Enable it with `ENABLE_TELEMETRY=true`, or set `TELEMETRY_CONNECTION` / `TELEMETRY_URL`:

```dotenv
ENABLE_TELEMETRY=true
TELEMETRY_CONNECTION=clickhouse
TELEMETRY_URL=http://default:@localhost:8123/default
TELEMETRY_QUEUE_MAX_SIZE=10000
TELEMETRY_QUEUE_FULL_STRATEGY=block
TELEMETRY_BATCH_SIZE=1000
TELEMETRY_FLUSH_INTERVAL=1.0
TELEMETRY_FLUSH_TIMEOUT=10.0
TELEMETRY_MAX_RETRIES=3
TELEMETRY_RETRY_BACKOFF=exponential
TELEMETRY_ASYNC_INSERT=true
```

| Variable | Default | Purpose |
|---|---|---|
| `ENABLE_TELEMETRY` | `false` | Master switch. Explicit `false` disables telemetry, even when legacy TSDB variables are present. |
| `TELEMETRY_CONNECTION` | `clickhouse` | Adapter selector: `clickhouse`, `timescaledb`, `influxdb`, or `iotdb`. |
| `TELEMETRY_URL` | built from `TSDB_*` fields | Backend URL passed to the adapter. |
| `TELEMETRY_QUEUE_MAX_SIZE` | `10000` | In-memory queue capacity. Falls back to `TSDB_BUFFER_MAXSIZE` when set. |
| `TELEMETRY_QUEUE_FULL_STRATEGY` | `block` | Queue-full behavior: `block`, `fail`, `drop_newest`, or `drop_oldest`. |
| `TELEMETRY_BATCH_SIZE` | `1000` | Queue depth that triggers a size-based flush. Falls back to `TSDB_BATCH_SIZE` when set. |
| `TELEMETRY_FLUSH_INTERVAL` | `1.0` | Seconds between background flush attempts. Falls back to `TSDB_FLUSH_INTERVAL` when set. |
| `TELEMETRY_FLUSH_TIMEOUT` | `10.0` | Timeout for one adapter write attempt. |
| `TELEMETRY_MAX_RETRIES` | `3` | Retry attempts after the first adapter write fails. |
| `TELEMETRY_RETRY_BACKOFF` | `exponential` | Retry delay mode: `none`, `constant`, or `exponential`. |
| `TELEMETRY_ASYNC_INSERT` | `true` | ClickHouse-only server-side async insert setting. Falls back to `TSDB_ASYNC_INSERT` when set. |

Legacy `ENABLE_TSDB` and `TSDB_*` configuration still works for ClickHouse. If `ENABLE_TELEMETRY` is not set, `ENABLE_TSDB=true` enables telemetry and `TSDB_HOST`, `TSDB_PORT`, `TSDB_DATABASE`, `TSDB_USER`, and `TSDB_PASSWORD` build the ClickHouse URL. New `TELEMETRY_*` values take precedence where both forms are present.

## Storage adapters

Select the adapter with `TELEMETRY_CONNECTION`:

| Connection | `TELEMETRY_URL` | Notes |
|---|---|---|
| `clickhouse` | `http://user:password@host:8123/database` | Default adapter. Writes to `telemetry_observations` unless you create and pass a custom adapter. |
| `timescaledb` | Async SQLAlchemy URL, for example `postgresql+asyncpg://user:password@host:5432/database` | Writes through SQLAlchemy to `telemetry_observations` by default. |
| `influxdb` | Full `/api/v2/write` URL, or a base URL with optional `bucket` and `org` query values | Base URLs are expanded to `/api/v2/write?bucket=...&org=...&precision=ns`. Defaults are `bucket=telemetry` and `org=routemq`. |
| `iotdb` | HTTP endpoint that accepts the JSON payload produced by the adapter | Posts mapped records to the configured URL. |

## Writing telemetry

Import the public API from `routemq.telemetry`:

```python
from routemq.telemetry import Measurement, TelemetryPoint, telemetry


class PumpController:
    @staticmethod
    async def handle_telemetry(topic_params, payload, client):
        point = TelemetryPoint(
            device_id=topic_params["pump_id"],
            observed_at=payload.get("ts"),
            measurements={
                "flow_lpm": Measurement.from_value({"value": payload["flow"], "unit": "L/min"}),
                "pressure_bar": Measurement.from_value({"value": payload["pressure"], "unit": "bar"}),
                "running": Measurement.from_value(payload.get("running", True)),
            },
            tags={"site": payload.get("site", "default")},
            attributes={"source": "mqtt"},
        )
        await telemetry.write(point)
```

`TelemetryPoint` describes one observation from one device:

| Field | Purpose |
|---|---|
| `device_id` | Required device identifier. It is trimmed and stored as a string. |
| `observed_at` | Observation time as a timezone-aware `datetime`, ISO string, or `None`. `None` uses the current UTC time. |
| `measurements` | Required mapping of measurement name to a scalar, `Measurement`, or mapping accepted by `Measurement.from_value`. |
| `tags` | Low-cardinality string tags, coerced to `str` keys and values. |
| `attributes` | Extra context copied into adapter payloads. |
| `metadata` | Extra metadata copied into adapter payloads. |
| `ingested_at` | Optional ingest time as a `datetime`, ISO string, or `None`. |

`Measurement.from_value` accepts:

* An existing `Measurement`.
* A scalar value: `str`, `int`, `float`, `bool`, or `None`.
* A mapping with `value`, plus optional `unit`, `quality`, `data_type` or `type`, and `flags`.

## Runtime lifecycle

The global `telemetry` manager owns the in-memory queue and background flush task.

| Call | Behavior |
|---|---|
| `await telemetry.start(adapter=..., settings=...)` | Starts the background flush task when settings are enabled. Returns `False` when telemetry is disabled. |
| `await telemetry.write(point)` | Enqueues one `TelemetryPoint`, then flushes ready batches when queue depth reaches `TELEMETRY_BATCH_SIZE`. |
| `await telemetry.write_many(points)` | Enqueues multiple points with the same queue behavior as `write`. |
| `await telemetry.flush()` | Drains up to one batch and writes it through the adapter with timeout and retry handling. |
| `await telemetry.close()` | Shutdown path for custom runners. It cancels the background task, flushes remaining queued points, and closes the adapter. |

Queue-full handling is controlled by `TELEMETRY_QUEUE_FULL_STRATEGY`:

* `block` waits until the queue has room.
* `fail` raises `TelemetryQueueFull`.
* `drop_newest` drops the incoming point.
* `drop_oldest` removes one queued point, then enqueues the new point.

`write` and `write_many` return a `WriteResult` with accepted count, written count from any immediate flush, and per-point failures. Adapter failures retry according to `TELEMETRY_MAX_RETRIES` and `TELEMETRY_RETRY_BACKOFF`. Non-retriable failures, or failures left after retries, are returned in the result.

## Schema ownership

Your application owns database objects. RouteMQ writes to the configured table, bucket, endpoint, or device path, but it does not create or alter backend schema.

The adapters map a `TelemetryPoint` like this:

| Adapter | Mapping |
|---|---|
| ClickHouse | One row per measurement in `telemetry_observations` by default. Columns are `observed_at`, `ingested_at`, `device_id`, `measurement`, typed value columns, `unit`, `quality`, `tags`, `attributes`, and `metadata`. The adapter validates that the table and expected columns exist. |
| TimescaleDB | One row per measurement in `telemetry_observations` by default. The adapter writes `observed_at`, `ingested_at`, `device_id`, `measurement`, typed value columns, `unit`, `quality`, `tags`, `attributes`, and `metadata` through SQLAlchemy. |
| InfluxDB | One line-protocol record per point. `device_id` and point tags become tags, measurements become fields, and attributes or metadata become fields prefixed with `attribute.` and `metadata.`. |
| IoTDB | One JSON record per point posted to the configured URL. The mapping uses `root.routemq.<device_id>` with the device id sanitized for the path, millisecond timestamps, measurements, attributes, and metadata. |

## Reading telemetry

Reads are not unified across backends. Use the native client or backend API for queries. The telemetry API only covers writes and lifecycle.

## Durability

The queue lives in memory. On a hard crash, queued points can be lost. On graceful shutdown, `telemetry.close()` flushes the remaining queue before closing the adapter.

Failed writes retry with the configured timeout, retry count, and backoff. Points still failing after retries are reported as failures. Dropped points are counted by the queue-full strategy that caused the drop.

## Observability

Each flush creates a CLIENT span named `telemetry.flush` with `telemetry.batch.size`. The runtime also emits lifecycle events for accepted points, dropped points, queue depth, written batches, flushed points, and write errors. See [Metrics](../monitoring/metrics.md) for the exported metric families.

## Docker

`docker-compose.dev.yml` and `docker-compose.yml` include an optional `clickhouse` service. For the new API, set `ENABLE_TELEMETRY=true`, `TELEMETRY_CONNECTION=clickhouse`, and `TELEMETRY_URL=http://default:@clickhouse:8123/default`.

The legacy ClickHouse form still routes through telemetry when telemetry is not explicitly disabled:

```dotenv
ENABLE_TSDB=true
TSDB_HOST=clickhouse
TSDB_PORT=8123
TSDB_DATABASE=default
```
