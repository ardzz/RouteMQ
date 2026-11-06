import asyncio
import json
import unittest
from importlib.metadata import distribution
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt_client
from paho.mqtt.enums import CallbackAPIVersion

from routemq.router import Router
from tests.integration.helpers import DockerIntegrationTestCase, require_integration_dependency


class MqttBrokerIntegrationTests(DockerIntegrationTestCase, unittest.IsolatedAsyncioTestCase):
    container: Any
    broker_host: str
    broker_port: int

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        docker_container = require_integration_dependency(cls.__name__, 'testcontainers.core.container').DockerContainer
        log_message_wait_strategy = require_integration_dependency(
            cls.__name__, 'testcontainers.core.wait_strategies'
        ).LogMessageWaitStrategy
        config_file = Path(
            str(
                distribution('testcontainers').locate_file(
                    'testcontainers/mqtt/testcontainers-mosquitto-default-configuration.conf'
                )
            )
        )
        cls.container = (
            docker_container('eclipse-mosquitto:2.0.18')
            .with_exposed_ports(1883)
            .with_volume_mapping(config_file, '/mosquitto/config/mosquitto.conf')
            .waiting_for(log_message_wait_strategy(r'mosquitto version \d+\.\d+\.\d+ running').with_startup_timeout(30))
        )
        cls.container.start()
        cls.addClassCleanup(cls.container.stop)
        cls.broker_host = cls.container.get_container_host_ip()
        cls.broker_port = int(cls.container.get_exposed_port(1883))

    async def test_router_dispatches_topic_with_extracted_params(self) -> None:
        router = Router()
        handler_called = asyncio.Event()
        captured: dict[str, Any] = {}

        async def handle_status(*, id: str, payload: Any, client: Any) -> None:
            captured['id'] = id
            captured['payload'] = payload
            handler_called.set()

        router.on('test/devices/{id}/status', handle_status, qos=1)

        loop = asyncio.get_event_loop()
        sub_client = mqtt_client.Client(
            client_id='integration-sub',
            callback_api_version=CallbackAPIVersion.VERSION2,
        )

        def on_message(client: Any, userdata: Any, msg: Any) -> None:
            asyncio.run_coroutine_threadsafe(
                router.dispatch(msg.topic, msg.payload, client),
                loop,
            )

        sub_client.on_message = on_message
        sub_client.connect(self.broker_host, self.broker_port)
        sub_client.subscribe('test/devices/+/status', qos=1)
        sub_client.loop_start()
        await asyncio.sleep(0.5)

        pub_client = mqtt_client.Client(
            client_id='integration-pub',
            callback_api_version=CallbackAPIVersion.VERSION2,
        )
        pub_client.connect(self.broker_host, self.broker_port)
        pub_client.publish('test/devices/abc123/status', json.dumps({'state': 'online'}), qos=1)

        try:
            await asyncio.wait_for(handler_called.wait(), timeout=5.0)
        finally:
            sub_client.loop_stop()
            sub_client.disconnect()
            pub_client.disconnect()

        self.assertEqual(captured['id'], 'abc123')
        self.assertEqual(captured['payload'], b'{"state": "online"}')


if __name__ == '__main__':
    unittest.main()
