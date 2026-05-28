import os
import unittest
from unittest.mock import MagicMock, patch

from routemq.mqtt_utils import (
    MqttTlsConfig,
    connect_mqtt_client_with_retries,
    create_mqtt_client,
    get_mqtt_retry_config,
    get_mqtt_tls_config,
)


class MqttTlsConfigTests(unittest.TestCase):
    def test_tls_config_defaults_to_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = get_mqtt_tls_config()

        self.assertFalse(config.enabled)

    def test_create_client_applies_tls_then_insecure(self) -> None:
        fake_client = MagicMock()
        calls: list[str] = []
        fake_client.tls_set.side_effect = lambda **kwargs: calls.append('tls_set')
        fake_client.tls_insecure_set.side_effect = lambda value: calls.append('tls_insecure_set')

        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            create_mqtt_client(
                'client',
                on_connect=MagicMock(),
                on_message=MagicMock(),
                tls_config=MqttTlsConfig(
                    enabled=True,
                    ca_certs='ca.pem',
                    certfile='cert.pem',
                    keyfile='key.pem',
                    insecure=True,
                ),
            )

        fake_client.tls_set.assert_called_once_with(ca_certs='ca.pem', certfile='cert.pem', keyfile='key.pem')
        fake_client.tls_insecure_set.assert_called_once_with(True)
        self.assertEqual(calls, ['tls_set', 'tls_insecure_set'])

    def test_create_client_uses_new_style_paho_exponential_backoff_when_supported(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None
                self.reconnect_kwargs = None

            def reconnect_delay_set(self, *, min_delay=1, max_delay=120, exponential_backoff=False) -> None:
                self.reconnect_kwargs = {
                    'min_delay': min_delay,
                    'max_delay': max_delay,
                    'exponential_backoff': exponential_backoff,
                }

        fake_client = FakeClient()

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch.dict(
                os.environ,
                {'MQTT_CONNECT_RETRIES': '3', 'MQTT_RETRY_MIN_DELAY': '2', 'MQTT_RETRY_MAX_DELAY': '9'},
                clear=True,
            ),
        ):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())

        self.assertEqual(
            fake_client.reconnect_kwargs,
            {'min_delay': 2.0, 'max_delay': 9.0, 'exponential_backoff': True},
        )

    def test_create_client_supports_old_style_paho_reconnect_delays(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None
                self.reconnect_kwargs = None

            def reconnect_delay_set(self, *, min_delay=1, max_delay=120) -> None:
                self.reconnect_kwargs = {'min_delay': min_delay, 'max_delay': max_delay}

        fake_client = FakeClient()

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch.dict(
                os.environ,
                {'MQTT_CONNECT_RETRIES': '3', 'MQTT_RETRY_MIN_DELAY': '2', 'MQTT_RETRY_MAX_DELAY': '9'},
                clear=True,
            ),
        ):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())

        self.assertEqual(fake_client.reconnect_kwargs, {'min_delay': 2.0, 'max_delay': 9.0})

    def test_create_client_does_not_swallow_reconnect_delay_errors(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None

            def reconnect_delay_set(self, *, min_delay=1, max_delay=120) -> None:
                raise RuntimeError('paho internal error')

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=FakeClient()),
            self.assertRaises(RuntimeError),
        ):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())


class MqttRetryTests(unittest.TestCase):
    def test_retry_config_reads_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                'MQTT_CONNECT_RETRIES': '4',
                'MQTT_RETRY_MIN_DELAY': '0.5',
                'MQTT_RETRY_MAX_DELAY': '5',
                'MQTT_RETRY_JITTER': '1',
            },
            clear=True,
        ):
            config = get_mqtt_retry_config()

        self.assertEqual(config.max_attempts, 4)
        self.assertEqual(config.min_delay, 0.5)
        self.assertEqual(config.max_delay, 5)
        self.assertEqual(config.jitter, 1)

    def test_connect_retries_network_startup_errors_with_fake_sleep(self) -> None:
        fake_client = MagicMock()
        fake_client.connect.side_effect = [ConnectionRefusedError('down'), None]
        sleeps: list[float] = []

        with patch.dict(os.environ, {'MQTT_CONNECT_RETRIES': '2', 'MQTT_RETRY_MIN_DELAY': '3'}, clear=True):
            connect_mqtt_client_with_retries(fake_client, 'broker', 1883, sleep=sleeps.append)

        self.assertEqual(fake_client.connect.call_count, 2)
        self.assertEqual(sleeps, [3.0])

    def test_connect_does_not_retry_non_network_errors(self) -> None:
        fake_client = MagicMock()
        fake_client.connect.side_effect = RuntimeError('bad')
        sleeps: list[float] = []

        with self.assertRaises(RuntimeError):
            connect_mqtt_client_with_retries(fake_client, 'broker', 1883, sleep=sleeps.append)

        self.assertEqual(sleeps, [])


if __name__ == '__main__':
    unittest.main()
