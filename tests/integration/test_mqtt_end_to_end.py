import asyncio
import json
import os
import unittest
from typing import Any

import paho.mqtt.client as mqtt_client
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from core.router import Router


_MOSQUITTO_INLINE_CONFIG = 'listener 1883\\nallow_anonymous true'


@unittest.skipUnless(
    os.environ.get('RUN_INTEGRATION_TESTS'),
    'Set RUN_INTEGRATION_TESTS=1 to run integration tests (requires Docker).',
)
class MqttBrokerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    container: DockerContainer
    broker_host: str
    broker_port: int

    @classmethod
    def setUpClass(cls) -> None:
        cls.container = (
            DockerContainer('eclipse-mosquitto:2.0.18')
            .with_exposed_ports(1883)
            .with_command(
                f'sh -c "printf \\"{_MOSQUITTO_INLINE_CONFIG}\\n\\" > /mosquitto/config/mosquitto.conf && '
                'exec /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf"'
            )
        )
        cls.container.start()
        wait_for_logs(cls.container, 'mosquitto version', timeout=30)
        cls.broker_host = cls.container.get_container_host_ip()
        cls.broker_port = int(cls.container.get_exposed_port(1883))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.container.stop()

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
            callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
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
            callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
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
