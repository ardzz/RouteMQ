# Time-Series Database (TSDB) Integration

RouteMQ can land MQTT telemetry into a time-series database for analytics. The first
supported backend is **ClickHouse**, shipped via the optional `routemq[clickhouse]` extra.

> The driver contract is intentionally internal and unstable while only one backend
> exists. See [ADR-0010](../adr/0010-tsdb-driver-registry.md) for the design rationale and
> roadmap (TimescaleDB, InfluxDB, and Apache IoTDB are future work).

## Installation

```bash
uv add "routemq[clickhouse]"
```

This installs `clickhouse-connect[async]` (which pulls `aiohttp`).

## Configuration

TSDB is disabled by default and gated by `ENABLE_TSDB`:

```dotenv
ENABLE_TSDB=true
TSDB_HOST=localhost
TSDB_PORT=8123
TSDB_DATABASE=default
TSDB_USER=default
TSDB_PASSWORD=
TSDB_BATCH_SIZE=10000
TSDB_FLUSH_INTERVAL=1.0
TSDB_BUFFER_MAXSIZE=50000
TSDB_ASYNC_INSERT=true
```

| Variable | Default | Purpose |
|---|---|---|
| `ENABLE_TSDB` | `false` | Master switch for the integration. |
| `TSDB_HOST` / `TSDB_PORT` | `localhost` / `8123` | ClickHouse HTTP endpoint. |
| `TSDB_DATABASE` | `default` | Target database. |
| `TSDB_USER` / `TSDB_PASSWORD` | `default` / empty | Credentials. |
| `TSDB_BATCH_SIZE` | `10000` | Rows that trigger a flush by size. |
| `TSDB_FLUSH_INTERVAL` | `1.0` | Seconds that trigger a flush by time. |
| `TSDB_BUFFER_MAXSIZE` | `50000` | Bounded buffer capacity (backpressure). |
| `TSDB_ASYNC_INSERT` | `true` | Enable ClickHouse server-side `async_insert`. |

## Schema ownership

Your application owns the table DDL. The framework only validates that the table exists
with the expected columns at startup and fails fast otherwise — it never creates or alters
tables. This keeps performance-critical `MergeTree` `ORDER BY` and partition choices in
your hands.

```sql
CREATE TABLE pump_telemetry
(
    ts            DateTime64(3),
    pump_id       LowCardinality(String),
    flow_lpm      Float32,
    pressure_bar  Float32,
    current_amp   Float32,
    vibration_mm  Float32
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (pump_id, ts);
```

## Writing telemetry

`write_points` enqueues rows into a bounded buffer; a background task flushes batches on
size or time using one batched async insert.

```python
from routemq.tsdb.tsdb_manager import tsdb_manager


class PumpController:
    @staticmethod
    async def handle_telemetry(topic_params, payload, client):
        await tsdb_manager.write_points(
            "pump_telemetry",
            [{
                "ts": payload["ts"],
                "pump_id": topic_params["pump_id"],
                "flow_lpm": payload["flow"],
                "pressure_bar": payload["pressure"],
                "current_amp": payload["current"],
                "vibration_mm": payload["vibration"],
            }],
        )
```

## Reading telemetry

Reads are not unified across backends. Use the native client escape hatch for queries:

```python
client = tsdb_manager.get_client()
result = await client.query(
    "SELECT pump_id, avg(pressure_bar) "
    "FROM pump_telemetry WHERE ts > now() - INTERVAL 1 HOUR GROUP BY pump_id"
)
```

## Durability

The write buffer lives in memory. On a hard crash, up to `TSDB_FLUSH_INTERVAL` seconds of
in-flight points may be lost. This trade favors write availability for high-volume sensor
telemetry. Failed inserts retry with exponential backoff and are dropped (with a logged
error and a `tsdb_write_errors_total` increment) only after retries are exhausted.

## Observability

Each batched flush emits a CLIENT span `tsdb.write.flush` with OpenTelemetry attributes
(`db.system`, `db.operation`, `db.collection.name`, `server.address`,
`db.operation.batch.size`, `tsdb.buffer.depth`) and the metrics described in
[Metrics](../monitoring/metrics.md).

## Docker

`docker-compose.dev.yml` and `docker-compose.yml` include an optional `clickhouse` service.
Set `ENABLE_TSDB=true` and `TSDB_HOST=clickhouse` to use it.
