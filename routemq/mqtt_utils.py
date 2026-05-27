import errno
import json
import os
import socket
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from paho.mqtt import client as mqtt_client


@dataclass(frozen=True)
class MqttConnectionConfig:
    broker: str
    port: int
    username: Optional[str]
    password: Optional[str]


def parse_mqtt_payload(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return payload


def get_mqtt_connection_config() -> MqttConnectionConfig:
    return MqttConnectionConfig(
        broker=os.getenv('MQTT_BROKER', 'localhost'),
        port=int(os.getenv('MQTT_PORT', '1883')),
        username=os.getenv('MQTT_USERNAME'),
        password=os.getenv('MQTT_PASSWORD'),
    )


def get_main_client_id() -> str:
    return os.getenv('MQTT_CLIENT_ID', f'mqtt-framework-main-{os.getpid()}')


def get_worker_client_id_prefix() -> str:
    return os.getenv('MQTT_CLIENT_ID', 'mqtt-worker')


def get_mqtt_group_name() -> str:
    return os.getenv('MQTT_GROUP_NAME', 'mqtt_framework_group')


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
) -> Any:
    client = mqtt_client.Client(client_id=client_id)
    client.on_connect = on_connect
    client.on_message = on_message

    if username and password:
        client.username_pw_set(username, password)

    return client


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
