import errno
import json
import socket
import time
import uuid
from dataclasses import dataclass
from inspect import signature
from typing import Any, Callable, Optional

from paho.mqtt import client as mqtt_client

from .observability import lifecycle
from .retry import RetryConfig, retry_sync
from .settings import load_mqtt_settings


@dataclass(frozen=True)
class MqttConnectionConfig:
    broker: str
    port: int
    username: Optional[str]
    password: Optional[str]


@dataclass(frozen=True)
class MqttTlsConfig:
    enabled: bool = False
    ca_certs: Optional[str] = None
    certfile: Optional[str] = None
    keyfile: Optional[str] = None
    insecure: bool = False


def parse_mqtt_payload(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Audit Accept: invalid JSON is a valid MQTT payload; dispatch raw bytes instead.
        return payload


def get_mqtt_connection_config() -> MqttConnectionConfig:
    config = load_mqtt_settings().connection
    return MqttConnectionConfig(
        broker=config.broker,
        port=config.port,
        username=config.username,
        password=config.password,
    )


def get_mqtt_tls_config() -> MqttTlsConfig:
    config = load_mqtt_settings().tls
    return MqttTlsConfig(
        enabled=config.enabled,
        ca_certs=config.ca_certs,
        certfile=config.certfile,
        keyfile=config.keyfile,
        insecure=config.insecure,
    )


def get_mqtt_retry_config() -> RetryConfig:
    config = load_mqtt_settings().retry
    return RetryConfig(
        max_attempts=config.max_attempts,
        min_delay=config.min_delay,
        max_delay=config.max_delay,
        jitter=config.jitter,
    )


def get_main_client_id() -> str:
    return load_mqtt_settings().main_client_id


def get_worker_client_id_prefix() -> str:
    return load_mqtt_settings().worker_client_id_prefix


def get_mqtt_group_name() -> str:
    return load_mqtt_settings().group_name


def build_worker_broker_config() -> dict[str, Any]:
    config = get_mqtt_connection_config()
    return {
        'broker': config.broker,
        'port': str(config.port),
        'username': config.username,
        'password': config.password,
        'client_id_prefix': get_worker_client_id_prefix(),
    }


def build_worker_client_id(worker_id: int, prefix: str = 'mqtt-worker') -> str:
    return f'{prefix}-{worker_id}-{uuid.uuid4().hex[:8]}'


def create_mqtt_client(
    client_id: str,
    *,
    on_connect: Callable[..., Any],
    on_message: Callable[..., Any],
    username: Optional[str] = None,
    password: Optional[str] = None,
    tls_config: MqttTlsConfig | None = None,
    on_disconnect: Callable[..., Any] | None = None,
    retry_config: RetryConfig | None = None,
) -> Any:
    client = mqtt_client.Client(client_id=client_id)
    client.on_connect = on_connect
    client.on_message = on_message
    if on_disconnect is not None:
        client.on_disconnect = on_disconnect

    if username and password:
        client.username_pw_set(username, password)

    resolved_tls_config = tls_config or get_mqtt_tls_config()
    if resolved_tls_config.enabled:
        client.tls_set(
            ca_certs=resolved_tls_config.ca_certs,
            certfile=resolved_tls_config.certfile,
            keyfile=resolved_tls_config.keyfile,
        )
        if resolved_tls_config.insecure:
            client.tls_insecure_set(True)

    resolved_retry_config = retry_config or get_mqtt_retry_config()
    if hasattr(client, 'reconnect_delay_set'):
        reconnect_delay_set = getattr(client, 'reconnect_delay_set')
        kwargs = {
            'min_delay': resolved_retry_config.min_delay,
            'max_delay': resolved_retry_config.max_delay,
        }
        try:
            parameters = signature(reconnect_delay_set).parameters
        except (TypeError, ValueError):
            # Audit Accept: older/mock Paho callables may not expose signatures.
            parameters = {}
        if 'exponential_backoff' in parameters:
            kwargs['exponential_backoff'] = True
        reconnect_delay_set(**kwargs)

    return client


def connect_mqtt_client_with_retries(
    client: Any,
    broker: str,
    port: int,
    *,
    retry_config: RetryConfig | None = None,
    sleep=None,
    rng=None,
    process: str = 'main',
) -> None:
    """Connect a Paho client with bounded startup retries for network failures."""

    config = retry_config or get_mqtt_retry_config()

    def operation() -> None:
        client.connect(broker, port)

    def on_retry(attempt: int, exc: BaseException, delay: float) -> None:
        lifecycle(
            'mqtt.connect.retry',
            {
                'process': process,
                'attempt': attempt,
                'delay': delay,
                'error': exc.__class__.__name__,
            },
        )

    retry_sync(
        operation,
        config=config,
        retryable=is_network_startup_error,
        sleep=sleep if sleep is not None else time.sleep,
        rng=rng,
        on_retry=on_retry,
    )
    lifecycle('mqtt.connect.succeeded', {'process': process})


def is_network_startup_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionRefusedError, TimeoutError, socket.timeout, socket.gaierror, ConnectionError)):
        return True
    if isinstance(exc, OSError) and exc.errno in {
        errno.ECONNREFUSED,
        errno.ETIMEDOUT,
        errno.ENETUNREACH,
        errno.EHOSTUNREACH,
        errno.ENETDOWN,
        errno.ECONNRESET,
        errno.ECONNABORTED,
        errno.EADDRNOTAVAIL,
    }:
        return True
    return False
