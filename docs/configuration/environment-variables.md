# Environment Variables

Complete reference for all RouteMQ configuration options.

## MQTT Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | localhost | MQTT broker hostname |
| `MQTT_PORT` | 1883 | MQTT broker port |
| `MQTT_USERNAME` | None | MQTT username (optional) |
| `MQTT_PASSWORD` | None | MQTT password (optional) |
| `MQTT_CLIENT_ID` | mqtt-framework-main-&lt;pid&gt; | MQTT main client ID; also used as the worker client ID prefix when set |
| `MQTT_GROUP_NAME` | mqtt_framework_group | Shared subscription group name |

## MQTT TLS Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_TLS_ENABLED` | false | Enable TLS for MQTT client connections |
| `MQTT_TLS_CA_CERTS` | None | CA certificate bundle path passed to the MQTT client |
| `MQTT_TLS_CERTFILE` | None | Client certificate file path |
| `MQTT_TLS_KEYFILE` | None | Client private key file path |
| `MQTT_TLS_INSECURE` | false | Disable MQTT TLS certificate verification |

## MQTT Startup Retry Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_CONNECT_RETRIES` | 1 | Maximum MQTT startup connection attempts |
| `MQTT_RETRY_MIN_DELAY` | 1.0 | Minimum retry delay in seconds |
| `MQTT_RETRY_MAX_DELAY` | 30.0 | Maximum retry delay in seconds |
| `MQTT_RETRY_JITTER` | 0.0 | Random jitter factor added to MQTT retry delays |

## Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_MYSQL` | true | Enable/disable MySQL integration |
| `DB_HOST` | localhost | Database hostname |
| `DB_PORT` | 3306 | Database port |
| `DB_NAME` | mqtt_framework | Database name |
| `DB_USER` | root | Database username |
| `DB_PASS` | (empty) | Database password |

## Database Pool Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_POOL_SIZE` | 5 | SQLAlchemy steady-state async connection pool size |
| `DB_POOL_MAX_OVERFLOW` | 10 | Extra burst connections above `DB_POOL_SIZE` |
| `DB_POOL_TIMEOUT` | 30 | Seconds to wait for a free connection before raising |
| `DB_POOL_RECYCLE` | 1800 | Seconds before recycling connections; conservative production default adopted ahead of the matrix |
| `DB_POOL_PRE_PING` | true | Validate connections before checkout; conservative production default adopted ahead of the matrix |
| `DB_POOL_USE_LIFO` | false | Use LIFO checkout order instead of FIFO |
| `DB_POOL_CLASS` | default | Pool implementation: `default` or `null` (`NullPool`) |

### Pool defaults and deferred benchmark matrix

The Sprint 06E defaults are conservative production-safe values: SQLAlchemy's async engine defaults for
`DB_POOL_SIZE`, `DB_POOL_MAX_OVERFLOW`, and `DB_POOL_TIMEOUT`, plus `DB_POOL_RECYCLE=1800` and
`DB_POOL_PRE_PING=true` to reduce stale MySQL connection risk. The empirical database queue-driver matrix is
deferred until the Sprint 06D benchmark harness merges. A follow-up sprint will run that matrix and may confirm
or revise these defaults. Operators with measured workload knowledge can override every pool value through env
without changing application code.

## Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_REDIS` | false | Enable/disable Redis integration |
| `REDIS_HOST` | localhost | Redis hostname |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_DB` | 0 | Redis database number |
| `REDIS_PASSWORD` | None | Redis password (optional) |
| `REDIS_USERNAME` | None | Redis username (optional) |
| `REDIS_MAX_CONNECTIONS` | 10 | Redis connection pool size |
| `REDIS_SOCKET_TIMEOUT` | 5.0 | Redis socket timeout |

## Queue Retry Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `QUEUE_RETRY_BACKOFF_ENABLED` | false | Enable exponential retry backoff for failed queue jobs |
| `QUEUE_RETRY_MAX_DELAY` | 60.0 | Maximum queue retry delay in seconds when backoff is enabled |
| `QUEUE_RETRY_JITTER` | 0.0 | Random jitter factor added to queue retry delays |

## Health HTTP Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HEALTH_HTTP_ENABLED` | false | Start the optional HTTP health endpoint |
| `HEALTH_HTTP_HOST` | 127.0.0.1 | Bind host for the health HTTP endpoint |
| `HEALTH_HTTP_PORT` | 8080 | Bind port for the health HTTP endpoint |

## Metrics HTTP Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_HTTP_ENABLED` | false | Start the optional `/metrics` endpoint. Defaults to off for backwards compatibility. |
| `METRICS_HTTP_PATH` | /metrics | Path served by the metrics renderer. |
| `METRICS_HTTP_SEPARATE` | false | When true, start a dedicated HealthServer instance for metrics on `METRICS_HTTP_HOST:METRICS_HTTP_PORT`. |
| `METRICS_HTTP_HOST` | inherits `HEALTH_HTTP_HOST` (127.0.0.1) | Bind host for the dedicated metrics server. |
| `METRICS_HTTP_PORT` | inherits `HEALTH_HTTP_PORT` (8080) | Bind port for the dedicated metrics server; invalid values fall back to the inherited default. |
| `METRICS_NAMESPACE` | routemq | Prefix for built-in metric names. |
| `METRICS_HISTOGRAM_BUCKETS` | 0.005,0.01,0.025,0.05,0.1,0.25,0.5,1.0,2.5,5.0,10.0 | Comma-separated histogram bucket bounds in seconds. Invalid lists fall back to defaults. |
| `METRICS_DEFAULT_LABELS` | (empty) | Comma-separated static labels added to every built-in metric, formatted as `key=value,key=value`; invalid pairs are ignored. |
| `PROMETHEUS_MULTIPROC_DIR` | (unset) | Standard `prometheus_client` multiprocess directory. See the prometheus_client multiprocess documentation; set it to an existing directory to merge metrics from queue/shared-subscription workers. |

## Parsing Notes

- Boolean values are enabled only by `1`, `true`, `yes`, or `on` (case-insensitive). Other values are treated as `false`.
- Invalid `MQTT_PORT` values raise a startup error.
- Invalid retry, health HTTP, and metrics HTTP numeric values fall back to their defaults for compatibility.

## Timezone Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TIMEZONE` | Asia/Jakarta | Application timezone (IANA timezone format) |

The timezone setting affects:
- Log timestamps in file outputs
- System timezone in Docker containers
- Application-level datetime operations

**Supported timezone formats:**
- `UTC` - Coordinated Universal Time
- `Asia/Jakarta` - Jakarta, Indonesia
- `America/New_York` - Eastern Time (US)
- `Europe/London` - London, UK
- `Asia/Tokyo` - Tokyo, Japan
- `Australia/Sydney` - Sydney, Australia

For a complete list of supported timezones, see the [IANA Time Zone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).

## Logging Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_FORMATTER` | json | Formatter: `json` for NDJSON or `plain` for legacy text logs |
| `LOG_FIELD_PROFILE` | otel | JSON field profile: `otel`, `ecs`, `datadog`, `loki`, or `routemq` |
| `LOG_LEVEL` | INFO | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `LOG_TO_CONSOLE` | true | Enable console logging |
| `LOG_STREAM` | stdout | Console stream: `stdout` or `stderr` |
| `LOG_INCLUDE_CONTEXT` | true | Include RouteMQ observability context in JSON logs |
| `ENABLE_TRACING` | true | Enable RouteMQ tracing spans (`mqtt.receive`, `router.dispatch`, `queue.enqueue`, etc.). Disable with `false`/`0`/`no`/`off` to make `start_span()` a no-op. |
| `LOG_LIFECYCLE_EVENTS` | true | Mirror known MQTT/router/queue lifecycle events to logs |
| `LOG_LIFECYCLE_LEVEL` | INFO | Log level for mirrored lifecycle events |
| `LOG_TO_FILE` | false | Enable optional file logging |
| `LOG_FILE` | logs/app.log | File path when file logging is enabled |
| `LOG_ROTATION_TYPE` | size | File rotation type: `size` or `time` |
| `LOG_MAX_BYTES` | 10485760 | Maximum bytes before size-based rotation |
| `LOG_BACKUP_COUNT` | 5 | Number of rotated backups to keep |
| `LOG_ROTATION_WHEN` | midnight | Time rotation period when `LOG_ROTATION_TYPE=time` |
| `LOG_ROTATION_INTERVAL` | 1 | Time rotation interval |
| `LOG_DATE_FORMAT` | %Y-%m-%d | Time-rotated file suffix format |
| `LOG_FORMAT` | %(asctime)s - %(name)s - %(levelname)s - %(message)s | Legacy plain-text format; a custom value without `LOG_FORMATTER` selects plain logging for compatibility |

## Example .env File

```env
# MQTT Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password
MQTT_CLIENT_ID=mqtt-framework-main
MQTT_GROUP_NAME=mqtt_framework_group

# MQTT TLS Configuration
MQTT_TLS_ENABLED=false
MQTT_TLS_CA_CERTS=/path/to/ca.pem
MQTT_TLS_CERTFILE=/path/to/client.pem
MQTT_TLS_KEYFILE=/path/to/client.key
MQTT_TLS_INSECURE=false

# MQTT Startup Retry Configuration
MQTT_CONNECT_RETRIES=1
MQTT_RETRY_MIN_DELAY=1.0
MQTT_RETRY_MAX_DELAY=30.0
MQTT_RETRY_JITTER=0.0

# Database Configuration
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password

# Database Pool Configuration
# DB_POOL_SIZE=5
# DB_POOL_MAX_OVERFLOW=10
# DB_POOL_TIMEOUT=30
# DB_POOL_RECYCLE=1800
# DB_POOL_PRE_PING=true
# DB_POOL_USE_LIFO=false
# DB_POOL_CLASS=default

# Redis Configuration
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password
REDIS_USERNAME=your_redis_username
REDIS_MAX_CONNECTIONS=10
REDIS_SOCKET_TIMEOUT=5.0

# Queue Retry Configuration
QUEUE_RETRY_BACKOFF_ENABLED=false
QUEUE_RETRY_MAX_DELAY=60.0
QUEUE_RETRY_JITTER=0.0

# Health HTTP Configuration
HEALTH_HTTP_ENABLED=false
HEALTH_HTTP_HOST=127.0.0.1
HEALTH_HTTP_PORT=8080

# Metrics HTTP Configuration
METRICS_HTTP_ENABLED=false
METRICS_HTTP_PATH=/metrics
METRICS_HTTP_SEPARATE=false
METRICS_HTTP_HOST=127.0.0.1
METRICS_HTTP_PORT=8080
METRICS_NAMESPACE=routemq
METRICS_HISTOGRAM_BUCKETS=0.005,0.01,0.025,0.05,0.1,0.25,0.5,1.0,2.5,5.0,10.0
METRICS_DEFAULT_LABELS=
# PROMETHEUS_MULTIPROC_DIR=/tmp/routemq-prom

# Timezone Configuration
TIMEZONE=Asia/Jakarta

# Logging Configuration
LOG_FORMATTER=json
LOG_FIELD_PROFILE=otel
LOG_LEVEL=INFO
LOG_TO_CONSOLE=true
LOG_STREAM=stdout
LOG_INCLUDE_CONTEXT=true
ENABLE_TRACING=true
LOG_LIFECYCLE_EVENTS=true
LOG_LIFECYCLE_LEVEL=INFO
LOG_TO_FILE=false
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```
