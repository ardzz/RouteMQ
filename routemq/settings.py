from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from routemq.metrics.registry import DEFAULT_HISTOGRAM_BUCKETS


_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_DATABASE_POOL_CLASSES = {'default', 'null'}
_DATABASE_CONNECTIONS = {'mysql', 'postgres'}
_TELEMETRY_CONNECTIONS = {'clickhouse', 'timescaledb', 'influxdb', 'iotdb'}
_TELEMETRY_QUEUE_FULL_STRATEGIES = {'block', 'fail', 'drop_newest', 'drop_oldest'}


def _environment(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def env_str(env: Mapping[str, str], name: str, default: str) -> str:
    """Read a string environment value, preserving empty strings for compatibility."""
    value = env.get(name)
    return default if value is None else value


def env_optional_str(env: Mapping[str, str], name: str) -> str | None:
    """Read an optional string environment value, preserving empty strings for compatibility."""
    return env.get(name)


def env_bool(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    """Read a RouteMQ boolean env value using the existing permissive truth-set behavior."""
    value = env.get(name)
    if value is None:
        return default
    return value.lower() in _TRUE_VALUES


def env_optional_bool(env: Mapping[str, str], name: str) -> bool | None:
    """Read an optional boolean while preserving absence vs explicit false."""
    value = env.get(name)
    if value is None:
        return None
    return value.lower() in _TRUE_VALUES


def env_int(env: Mapping[str, str], name: str, default: int, *, fallback_on_invalid: bool = False) -> int:
    """Read an integer env value."""
    value = env.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        # Audit Accept: selected settings intentionally keep legacy fallback behavior.
        if fallback_on_invalid:
            return default
        raise


def env_float(env: Mapping[str, str], name: str, default: float, *, fallback_on_invalid: bool = False) -> float:
    """Read a float env value."""
    value = env.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        # Audit Accept: selected settings intentionally keep legacy fallback behavior.
        if fallback_on_invalid:
            return default
        raise


@dataclass(frozen=True, slots=True)
class MqttConnectionSettings:
    broker: str = 'localhost'
    port: int = 1883
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True, slots=True)
class MqttTlsSettings:
    enabled: bool = False
    ca_certs: str | None = None
    certfile: str | None = None
    keyfile: str | None = None
    insecure: bool = False


@dataclass(frozen=True, slots=True)
class MqttRetrySettings:
    max_attempts: int = 1
    min_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.0


@dataclass(frozen=True, slots=True)
class MqttSettings:
    connection: MqttConnectionSettings
    tls: MqttTlsSettings
    retry: MqttRetrySettings
    main_client_id: str
    worker_client_id_prefix: str
    group_name: str = 'mqtt_framework_group'


@dataclass(frozen=True, slots=True)
class HealthHttpSettings:
    enabled: bool = False
    host: str = '127.0.0.1'
    port: int = 8080


@dataclass(frozen=True, slots=True)
class DatabasePoolSettings:
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800
    pool_pre_ping: bool = True
    pool_use_lifo: bool = False
    pool_class: str = 'default'


@dataclass(frozen=True, slots=True)
class DatabaseConnectionSettings:
    enabled: bool = True
    connection: str = 'mysql'
    url: str = 'mysql+aiomysql://root:@localhost:3306/mqtt_framework'
    auto_create_tables: bool = False


@dataclass(frozen=True, slots=True)
class TelemetrySettings:
    enabled: bool = False
    connection: str = 'clickhouse'
    url: str = 'http://localhost:8123/default'
    queue_max_size: int = 10000
    queue_full_strategy: str = 'block'
    batch_size: int = 1000
    flush_interval: float = 1.0
    flush_timeout: float = 10.0
    max_retries: int = 3
    retry_backoff: str = 'exponential'
    async_insert: bool = True


@dataclass(frozen=True, slots=True)
class MetricsHttpSettings:
    enabled: bool = False
    path: str = '/metrics'
    separate: bool = False
    host: str = '127.0.0.1'
    port: int = 8080
    namespace: str = 'routemq'
    histogram_buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS
    default_labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueueRetrySettings:
    backoff_enabled: bool = False
    max_delay: float = 60.0
    jitter: float = 0.0


@dataclass(frozen=True, slots=True)
class QueueReliabilitySettings:
    visibility_timeout: int = 300
    reaper_interval: int = 30
    shutdown_grace: int = 300
    heartbeat_interval: int = 10


def _parse_int_env(env: Mapping[str, str], name: str, default: int, *, fallback_on_invalid: bool = True) -> int:
    value = env_int(env, name, default, fallback_on_invalid=fallback_on_invalid)
    return default if value < 0 else value


def _parse_bool_env(env: Mapping[str, str], name: str, default: bool) -> bool:
    return env_bool(env, name, default)


def load_mqtt_settings(env: Mapping[str, str] | None = None) -> MqttSettings:
    """Load MQTT-related settings from an environment mapping."""
    values = _environment(env)
    return MqttSettings(
        connection=MqttConnectionSettings(
            broker=env_str(values, 'MQTT_BROKER', 'localhost'),
            port=env_int(values, 'MQTT_PORT', 1883),
            username=env_optional_str(values, 'MQTT_USERNAME'),
            password=env_optional_str(values, 'MQTT_PASSWORD'),
        ),
        tls=MqttTlsSettings(
            enabled=env_bool(values, 'MQTT_TLS_ENABLED', False),
            ca_certs=env_optional_str(values, 'MQTT_TLS_CA_CERTS'),
            certfile=env_optional_str(values, 'MQTT_TLS_CERTFILE'),
            keyfile=env_optional_str(values, 'MQTT_TLS_KEYFILE'),
            insecure=env_bool(values, 'MQTT_TLS_INSECURE', False),
        ),
        retry=MqttRetrySettings(
            max_attempts=env_int(values, 'MQTT_CONNECT_RETRIES', 1, fallback_on_invalid=True),
            min_delay=env_float(values, 'MQTT_RETRY_MIN_DELAY', 1.0, fallback_on_invalid=True),
            max_delay=env_float(values, 'MQTT_RETRY_MAX_DELAY', 30.0, fallback_on_invalid=True),
            jitter=env_float(values, 'MQTT_RETRY_JITTER', 0.0, fallback_on_invalid=True),
        ),
        main_client_id=env_str(values, 'MQTT_CLIENT_ID', f'mqtt-framework-main-{os.getpid()}'),
        worker_client_id_prefix=env_str(values, 'MQTT_CLIENT_ID', 'mqtt-worker'),
        group_name=env_str(values, 'MQTT_GROUP_NAME', 'mqtt_framework_group'),
    )


def load_health_http_settings(env: Mapping[str, str] | None = None) -> HealthHttpSettings:
    """Load health HTTP server settings from an environment mapping."""
    values = _environment(env)
    return HealthHttpSettings(
        enabled=env_bool(values, 'HEALTH_HTTP_ENABLED', False),
        host=env_str(values, 'HEALTH_HTTP_HOST', '127.0.0.1'),
        port=env_int(values, 'HEALTH_HTTP_PORT', 8080, fallback_on_invalid=True),
    )


def load_database_pool_settings(env: Mapping[str, str] | None = None) -> DatabasePoolSettings:
    """Load SQLAlchemy database pool settings from an environment mapping."""
    values = _environment(env)
    pool_class = env_str(values, 'DB_POOL_CLASS', 'default').lower()
    if pool_class not in _DATABASE_POOL_CLASSES:
        pool_class = 'default'

    return DatabasePoolSettings(
        pool_size=_parse_int_env(values, 'DB_POOL_SIZE', 5),
        max_overflow=_parse_int_env(values, 'DB_POOL_MAX_OVERFLOW', 10),
        pool_timeout=_parse_int_env(values, 'DB_POOL_TIMEOUT', 30),
        pool_recycle=_parse_int_env(values, 'DB_POOL_RECYCLE', 1800),
        pool_pre_ping=_parse_bool_env(values, 'DB_POOL_PRE_PING', True),
        pool_use_lifo=_parse_bool_env(values, 'DB_POOL_USE_LIFO', False),
        pool_class=pool_class,
    )


def load_database_connection_settings(env: Mapping[str, str] | None = None) -> DatabaseConnectionSettings:
    """Load backend-neutral SQLAlchemy connection settings.

    ``DATABASE_URL`` wins when present. Otherwise RouteMQ builds an async SQLAlchemy URL from
    ``DB_CONNECTION`` and canonical ``DB_*`` fields while preserving legacy MySQL defaults.
    """

    values = _environment(env)
    explicit_url = env_optional_str(values, 'DATABASE_URL')
    connection = _parse_database_connection(values.get('DB_CONNECTION'))
    if explicit_url:
        connection = _connection_from_database_url(explicit_url) or connection
    explicit_selector = bool(values.get('DB_CONNECTION'))
    enabled = env_bool(values, 'ENABLE_MYSQL', True) or bool(explicit_url) or explicit_selector
    if explicit_url:
        return DatabaseConnectionSettings(
            enabled=enabled,
            connection=connection,
            url=_normalize_database_url(explicit_url),
            auto_create_tables=env_bool(values, 'DB_AUTO_CREATE_TABLES', False),
        )

    host = env_str(values, 'DB_HOST', 'localhost')
    port = env_str(values, 'DB_PORT', '5432' if connection == 'postgres' else '3306')
    name = env_str(values, 'DB_NAME', 'mqtt_framework')
    user = env_str(values, 'DB_USER', 'root')
    password = _database_password(values)
    driver = 'postgresql+asyncpg' if connection == 'postgres' else 'mysql+aiomysql'
    return DatabaseConnectionSettings(
        enabled=enabled,
        connection=connection,
        url=f'{driver}://{user}:{password}@{host}:{port}/{name}',
        auto_create_tables=env_bool(values, 'DB_AUTO_CREATE_TABLES', False),
    )


def _parse_database_connection(value: str | None) -> str:
    if value is None or not value.strip():
        return 'mysql'
    normalized = value.strip().lower()
    if normalized == 'postgresql':
        return 'postgres'
    if normalized not in _DATABASE_CONNECTIONS:
        return 'mysql'
    return normalized


def _normalize_database_url(url: str) -> str:
    if url.startswith('postgresql+asyncpg://') or url.startswith('mysql+aiomysql://'):
        return url
    if url.startswith('postgresql://'):
        return 'postgresql+asyncpg://' + url.removeprefix('postgresql://')
    if url.startswith('postgres://'):
        return 'postgresql+asyncpg://' + url.removeprefix('postgres://')
    if url.startswith('mysql://'):
        return 'mysql+aiomysql://' + url.removeprefix('mysql://')
    return url


def _connection_from_database_url(url: str) -> str | None:
    normalized = url.lower()
    if normalized.startswith(('postgresql://', 'postgres://', 'postgresql+asyncpg://')):
        return 'postgres'
    if normalized.startswith(('mysql://', 'mysql+aiomysql://')):
        return 'mysql'
    return None


def _database_password(env: Mapping[str, str]) -> str:
    password = env_optional_str(env, 'DB_PASSWORD')
    if password is not None:
        return password
    return env_str(env, 'DB_PASS', '')


def load_telemetry_settings(env: Mapping[str, str] | None = None) -> TelemetrySettings:
    """Load IoT telemetry runtime settings, including legacy ClickHouse fallbacks."""

    values = _environment(env)
    connection = _parse_telemetry_connection(values.get('TELEMETRY_CONNECTION'))
    legacy_tsdb_enabled = env_bool(values, 'ENABLE_TSDB', False)
    explicit_enabled = env_optional_bool(values, 'ENABLE_TELEMETRY')
    enabled = (
        explicit_enabled
        if explicit_enabled is not None
        else legacy_tsdb_enabled or bool(values.get('TELEMETRY_CONNECTION')) or bool(values.get('TELEMETRY_URL'))
    )
    url = env_str(values, 'TELEMETRY_URL', _legacy_clickhouse_url(values))
    queue_strategy = env_str(values, 'TELEMETRY_QUEUE_FULL_STRATEGY', 'block').lower()
    if queue_strategy not in _TELEMETRY_QUEUE_FULL_STRATEGIES:
        queue_strategy = 'block'
    retry_backoff = env_str(values, 'TELEMETRY_RETRY_BACKOFF', 'exponential').lower()
    if retry_backoff not in {'none', 'constant', 'exponential'}:
        retry_backoff = 'exponential'

    return TelemetrySettings(
        enabled=enabled,
        connection=connection,
        url=url,
        queue_max_size=_positive_int(values, 'TELEMETRY_QUEUE_MAX_SIZE', _parse_int_env(values, 'TSDB_BUFFER_MAXSIZE', 10000)),
        queue_full_strategy=queue_strategy,
        batch_size=_positive_int(values, 'TELEMETRY_BATCH_SIZE', _parse_int_env(values, 'TSDB_BATCH_SIZE', 1000)),
        flush_interval=_positive_float(values, 'TELEMETRY_FLUSH_INTERVAL', env_float(values, 'TSDB_FLUSH_INTERVAL', 1.0, fallback_on_invalid=True)),
        flush_timeout=_positive_float(values, 'TELEMETRY_FLUSH_TIMEOUT', 10.0),
        max_retries=_parse_int_env(values, 'TELEMETRY_MAX_RETRIES', 3),
        retry_backoff=retry_backoff,
        async_insert=env_bool(values, 'TELEMETRY_ASYNC_INSERT', env_bool(values, 'TSDB_ASYNC_INSERT', True)),
    )


def _parse_telemetry_connection(value: str | None) -> str:
    if value is None or not value.strip():
        return 'clickhouse'
    normalized = value.strip().lower()
    return normalized if normalized in _TELEMETRY_CONNECTIONS else 'clickhouse'


def _legacy_clickhouse_url(env: Mapping[str, str]) -> str:
    host = env_str(env, 'TSDB_HOST', 'localhost')
    port = env_str(env, 'TSDB_PORT', '8123')
    database = env_str(env, 'TSDB_DATABASE', 'default')
    username = env_optional_str(env, 'TSDB_USER')
    password = env_optional_str(env, 'TSDB_PASSWORD')
    credentials = '' if username is None else f'{username}:{password or ""}@'
    return f'http://{credentials}{host}:{port}/{database}'


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = _parse_int_env(env, name, default)
    return max(1, value)


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    value = env_float(env, name, default, fallback_on_invalid=True)
    return default if value <= 0 else value


def load_metrics_http_settings(env: Mapping[str, str] | None = None) -> MetricsHttpSettings:
    """Load metrics HTTP endpoint settings from an environment mapping."""

    values = _environment(env)
    health_host = env_str(values, 'HEALTH_HTTP_HOST', '127.0.0.1')
    health_port = env_int(values, 'HEALTH_HTTP_PORT', 8080, fallback_on_invalid=True)
    return MetricsHttpSettings(
        enabled=env_bool(values, 'METRICS_HTTP_ENABLED', False),
        path=env_str(values, 'METRICS_HTTP_PATH', '/metrics'),
        separate=env_bool(values, 'METRICS_HTTP_SEPARATE', False),
        host=env_str(values, 'METRICS_HTTP_HOST', health_host),
        port=env_int(values, 'METRICS_HTTP_PORT', health_port, fallback_on_invalid=True),
        namespace=env_str(values, 'METRICS_NAMESPACE', 'routemq'),
        histogram_buckets=_parse_histogram_buckets(values.get('METRICS_HISTOGRAM_BUCKETS')),
        default_labels=_parse_default_labels(values.get('METRICS_DEFAULT_LABELS')),
    )


def _parse_histogram_buckets(value: str | None) -> tuple[float, ...]:
    if value is None or not value.strip():
        return DEFAULT_HISTOGRAM_BUCKETS
    try:
        buckets = tuple(float(part.strip()) for part in value.split(',') if part.strip())
    except ValueError:
        return DEFAULT_HISTOGRAM_BUCKETS
    return buckets or DEFAULT_HISTOGRAM_BUCKETS


def _parse_default_labels(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    labels: dict[str, str] = {}
    for part in value.split(','):
        key, separator, raw_label_value = part.partition('=')
        key = key.strip()
        if not separator or not key:
            continue
        labels[key] = raw_label_value.strip()
    return labels


def load_queue_retry_settings(env: Mapping[str, str] | None = None) -> QueueRetrySettings:
    """Load queue retry backoff settings from an environment mapping."""
    values = _environment(env)
    return QueueRetrySettings(
        backoff_enabled=env_bool(values, 'QUEUE_RETRY_BACKOFF_ENABLED', False),
        max_delay=env_float(values, 'QUEUE_RETRY_MAX_DELAY', 60.0, fallback_on_invalid=True),
        jitter=env_float(values, 'QUEUE_RETRY_JITTER', 0.0, fallback_on_invalid=True),
    )


def load_queue_reliability_settings(env: Mapping[str, str] | None = None) -> QueueReliabilitySettings:
    """Load queue reliability settings from an environment mapping."""
    values = _environment(env)
    return QueueReliabilitySettings(
        visibility_timeout=_parse_int_env(values, 'QUEUE_VISIBILITY_TIMEOUT', 300),
        reaper_interval=_parse_int_env(values, 'QUEUE_REAPER_INTERVAL', 30),
        shutdown_grace=_parse_int_env(values, 'QUEUE_SHUTDOWN_GRACE', 300),
        heartbeat_interval=_parse_int_env(values, 'QUEUE_HEARTBEAT_INTERVAL', 10),
    )
