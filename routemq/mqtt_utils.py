import errno
import json
import socket
import time
import uuid
from dataclasses import dataclass
from inspect import signature
from typing import Any, Callable, Optional

from paho.mqtt import client as mqtt_client

from .observability import current_span, get_context_attributes, lifecycle, start_span
from .retry import RetryConfig, retry_sync
from .settings import load_mqtt_settings

_TRACEPARENT_PROPERTY = 'traceparent'
_TRACESTATE_PROPERTY = 'tracestate'
_TRACEPARENT_VERSION = '00'


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

    return wrap_mqtt_publish_with_trace_context(client)


def wrap_mqtt_publish_with_trace_context(client: Any) -> Any:
    """Wrap Paho publish calls with producer spans and MQTT v5 trace propagation."""

    if getattr(client, '_routemq_trace_publish_wrapped', False):
        return client
    publish = getattr(client, 'publish', None)
    if not callable(publish):
        return client

    def publish_with_trace(*args: Any, **kwargs: Any) -> Any:
        topic = kwargs.get('topic', args[0] if args else '')
        span_attributes = {
            'messaging.system': 'mqtt',
            'messaging.operation.type': 'publish',
            'messaging.destination': str(topic),
        }
        with start_span('mqtt.publish', span_attributes, kind='producer') as span:
            traced_args = args
            if _client_supports_user_properties(client):
                if 'properties' in kwargs:
                    kwargs['properties'] = inject_trace_context(client, kwargs['properties'])
                elif len(args) >= 5:
                    positional = list(args)
                    positional[4] = inject_trace_context(client, positional[4])
                    traced_args = tuple(positional)
                else:
                    properties = inject_trace_context(client, None)
                    if properties is not None:
                        kwargs['properties'] = properties

            result = publish(*traced_args, **kwargs)
            message_id = getattr(result, 'mid', None)
            if span is not None and message_id is not None:
                span.set_attribute('messaging.message.id', str(message_id))
            return result

    setattr(client, 'publish', publish_with_trace)
    setattr(client, '_routemq_trace_publish_wrapped', True)
    return client


def inject_trace_context(client: Any, properties: Any = None) -> Any:
    """Inject the active span into MQTT v5 UserProperty fields.

    MQTT 3.1.1 clients do not support publish properties, so this returns the
    original ``properties`` object unchanged for non-v5 clients.
    """

    if not _client_supports_user_properties(client):
        return properties
    span = current_span()
    if span is None:
        return properties

    resolved = properties if properties is not None else _new_publish_properties()
    if resolved is None:
        return properties

    _set_user_property(
        resolved,
        _TRACEPARENT_PROPERTY,
        f'{_TRACEPARENT_VERSION}-{span.trace_id}-{span.span_id}-{span.trace_flags}',
    )
    tracestate = get_context_attributes().get(_TRACESTATE_PROPERTY)
    if isinstance(tracestate, str) and tracestate:
        _set_user_property(resolved, _TRACESTATE_PROPERTY, tracestate)
    return resolved


def extract_trace_context(message: Any) -> dict[str, str]:
    """Extract W3C trace context from MQTT v5 UserProperty fields."""

    properties = getattr(message, 'properties', None)
    user_properties = _user_property_pairs(properties)
    traceparent = _last_user_property(user_properties, _TRACEPARENT_PROPERTY)
    context = _parse_traceparent(traceparent)
    if not context:
        return {}

    tracestate = _last_user_property(user_properties, _TRACESTATE_PROPERTY)
    if tracestate:
        context[_TRACESTATE_PROPERTY] = tracestate
    return context


def _client_supports_user_properties(client: Any) -> bool:
    protocol = getattr(client, '_protocol', getattr(client, 'protocol', None))
    return protocol == getattr(mqtt_client, 'MQTTv5', 5)


def _new_publish_properties() -> Any:
    try:
        from paho.mqtt.packettypes import PacketTypes
        from paho.mqtt.properties import Properties
    except ImportError:  # pragma: no cover - paho>=2 ships these with the required dependency
        return None
    return Properties(PacketTypes.PUBLISH)


def _set_user_property(properties: Any, name: str, value: str) -> None:
    user_properties = [item for item in _user_property_pairs(properties) if item[0] != name]
    user_properties.append((name, value))
    properties.UserProperty = user_properties


def _user_property_pairs(properties: Any) -> list[tuple[str, str]]:
    if properties is None:
        return []
    raw = getattr(properties, 'UserProperty', None)
    if raw is None:
        return []
    if _looks_like_user_property(raw):
        return [(str(raw[0]), str(raw[1]))]
    pairs: list[tuple[str, str]] = []
    try:
        iterator = iter(raw)
    except TypeError:
        return []
    for item in iterator:
        if _looks_like_user_property(item):
            pairs.append((str(item[0]), str(item[1])))
    return pairs


def _looks_like_user_property(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], str)


def _last_user_property(user_properties: list[tuple[str, str]], name: str) -> str | None:
    for key, value in reversed(user_properties):
        if key == name:
            return value
    return None


def _parse_traceparent(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    parts = value.split('-')
    if len(parts) != 4:
        return {}
    version, trace_id, span_id, trace_flags = parts
    if version != _TRACEPARENT_VERSION:
        return {}
    if not _valid_hex(trace_id, 32) or not _valid_hex(span_id, 16) or not _valid_trace_flags(trace_flags):
        return {}
    return {'trace_id': trace_id.lower(), 'span_id': span_id.lower(), 'trace_flags': trace_flags.lower()}


def _valid_hex(value: str, length: int) -> bool:
    if len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value != '0' * length


def _valid_trace_flags(value: str) -> bool:
    if len(value) != 2:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


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
