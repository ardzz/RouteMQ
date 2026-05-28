from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


_TRUE_VALUES = {'1', 'true', 'yes', 'on'}


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


def env_int(env: Mapping[str, str], name: str, default: int, *, fallback_on_invalid: bool = False) -> int:
    """Read an integer env value."""
    value = env.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
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
class QueueRetrySettings:
    backoff_enabled: bool = False
    max_delay: float = 60.0
    jitter: float = 0.0


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


def load_queue_retry_settings(env: Mapping[str, str] | None = None) -> QueueRetrySettings:
    """Load queue retry backoff settings from an environment mapping."""
    values = _environment(env)
    return QueueRetrySettings(
        backoff_enabled=env_bool(values, 'QUEUE_RETRY_BACKOFF_ENABLED', False),
        max_delay=env_float(values, 'QUEUE_RETRY_MAX_DELAY', 60.0, fallback_on_invalid=True),
        jitter=env_float(values, 'QUEUE_RETRY_JITTER', 0.0, fallback_on_invalid=True),
    )
