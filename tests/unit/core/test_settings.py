import unittest
from unittest.mock import patch

from routemq.settings import (
    load_database_pool_settings,
    load_health_http_settings,
    load_mqtt_settings,
    load_queue_retry_settings,
)


class MqttSettingsTests(unittest.TestCase):
    def test_load_mqtt_settings_defaults(self) -> None:
        with patch('routemq.settings.os.getpid', return_value=1234):
            settings = load_mqtt_settings({})

        self.assertEqual(settings.connection.broker, 'localhost')
        self.assertEqual(settings.connection.port, 1883)
        self.assertEqual(settings.main_client_id, 'mqtt-framework-main-1234')
        self.assertEqual(settings.worker_client_id_prefix, 'mqtt-worker')
        self.assertEqual(settings.group_name, 'mqtt_framework_group')

    def test_load_mqtt_settings_parses_values(self) -> None:
        settings = load_mqtt_settings(
            {
                'MQTT_BROKER': 'broker.local',
                'MQTT_PORT': '1884',
                'MQTT_USERNAME': 'user',
                'MQTT_PASSWORD': 'secret',
                'MQTT_TLS_ENABLED': 'yes',
                'MQTT_TLS_CA_CERTS': 'ca.pem',
                'MQTT_TLS_CERTFILE': 'cert.pem',
                'MQTT_TLS_KEYFILE': 'key.pem',
                'MQTT_TLS_INSECURE': 'on',
                'MQTT_CONNECT_RETRIES': '3',
                'MQTT_RETRY_MIN_DELAY': '0.5',
                'MQTT_RETRY_MAX_DELAY': '9',
                'MQTT_RETRY_JITTER': '1.5',
                'MQTT_CLIENT_ID': 'client',
                'MQTT_GROUP_NAME': 'group',
            }
        )

        self.assertEqual(settings.connection.broker, 'broker.local')
        self.assertEqual(settings.connection.port, 1884)
        self.assertEqual(settings.connection.username, 'user')
        self.assertEqual(settings.connection.password, 'secret')
        self.assertTrue(settings.tls.enabled)
        self.assertEqual(settings.tls.ca_certs, 'ca.pem')
        self.assertEqual(settings.tls.certfile, 'cert.pem')
        self.assertEqual(settings.tls.keyfile, 'key.pem')
        self.assertTrue(settings.tls.insecure)
        self.assertEqual(settings.retry.max_attempts, 3)
        self.assertEqual(settings.retry.min_delay, 0.5)
        self.assertEqual(settings.retry.max_delay, 9)
        self.assertEqual(settings.retry.jitter, 1.5)
        self.assertEqual(settings.main_client_id, 'client')
        self.assertEqual(settings.worker_client_id_prefix, 'client')
        self.assertEqual(settings.group_name, 'group')

    def test_load_mqtt_settings_raises_for_invalid_port(self) -> None:
        with self.assertRaises(ValueError):
            load_mqtt_settings({'MQTT_PORT': 'invalid'})

    def test_load_mqtt_retry_settings_falls_back_for_invalid_numbers(self) -> None:
        settings = load_mqtt_settings(
            {
                'MQTT_CONNECT_RETRIES': 'invalid',
                'MQTT_RETRY_MIN_DELAY': 'invalid',
                'MQTT_RETRY_MAX_DELAY': 'invalid',
                'MQTT_RETRY_JITTER': 'invalid',
            }
        )

        self.assertEqual(settings.retry.max_attempts, 1)
        self.assertEqual(settings.retry.min_delay, 1.0)
        self.assertEqual(settings.retry.max_delay, 30.0)
        self.assertEqual(settings.retry.jitter, 0.0)


class HealthHttpSettingsTests(unittest.TestCase):
    def test_load_health_http_settings_parses_enabled_server(self) -> None:
        settings = load_health_http_settings(
            {
                'HEALTH_HTTP_ENABLED': '1',
                'HEALTH_HTTP_HOST': '0.0.0.0',
                'HEALTH_HTTP_PORT': '9090',
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.host, '0.0.0.0')
        self.assertEqual(settings.port, 9090)

    def test_load_health_http_settings_falls_back_for_invalid_port(self) -> None:
        settings = load_health_http_settings({'HEALTH_HTTP_ENABLED': 'true', 'HEALTH_HTTP_PORT': 'invalid'})

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.port, 8080)


class DatabasePoolSettingsTests(unittest.TestCase):
    def test_load_database_pool_settings_defaults(self) -> None:
        settings = load_database_pool_settings({})

        self.assertEqual(settings.pool_size, 5)
        self.assertEqual(settings.max_overflow, 10)
        self.assertEqual(settings.pool_timeout, 30)
        self.assertEqual(settings.pool_recycle, 1800)
        self.assertTrue(settings.pool_pre_ping)
        self.assertFalse(settings.pool_use_lifo)
        self.assertEqual(settings.pool_class, 'default')

    def test_load_database_pool_settings_parses_values(self) -> None:
        settings = load_database_pool_settings(
            {
                'DB_POOL_SIZE': '8',
                'DB_POOL_MAX_OVERFLOW': '16',
                'DB_POOL_TIMEOUT': '45',
                'DB_POOL_RECYCLE': '900',
                'DB_POOL_PRE_PING': 'false',
                'DB_POOL_USE_LIFO': 'yes',
                'DB_POOL_CLASS': 'null',
            }
        )

        self.assertEqual(settings.pool_size, 8)
        self.assertEqual(settings.max_overflow, 16)
        self.assertEqual(settings.pool_timeout, 45)
        self.assertEqual(settings.pool_recycle, 900)
        self.assertFalse(settings.pool_pre_ping)
        self.assertTrue(settings.pool_use_lifo)
        self.assertEqual(settings.pool_class, 'null')

    def test_load_database_pool_settings_falls_back_for_invalid_numbers(self) -> None:
        settings = load_database_pool_settings(
            {
                'DB_POOL_SIZE': 'invalid',
                'DB_POOL_MAX_OVERFLOW': 'invalid',
                'DB_POOL_TIMEOUT': 'invalid',
                'DB_POOL_RECYCLE': 'invalid',
            }
        )

        self.assertEqual(settings.pool_size, 5)
        self.assertEqual(settings.max_overflow, 10)
        self.assertEqual(settings.pool_timeout, 30)
        self.assertEqual(settings.pool_recycle, 1800)

    def test_load_database_pool_settings_falls_back_for_negative_numbers(self) -> None:
        settings = load_database_pool_settings(
            {
                'DB_POOL_SIZE': '-1',
                'DB_POOL_MAX_OVERFLOW': '-1',
                'DB_POOL_TIMEOUT': '-1',
                'DB_POOL_RECYCLE': '-1',
            }
        )

        self.assertEqual(settings.pool_size, 5)
        self.assertEqual(settings.max_overflow, 10)
        self.assertEqual(settings.pool_timeout, 30)
        self.assertEqual(settings.pool_recycle, 1800)

    def test_load_database_pool_settings_falls_back_for_invalid_pool_class(self) -> None:
        settings = load_database_pool_settings({'DB_POOL_CLASS': 'garbage'})

        self.assertEqual(settings.pool_class, 'default')


class QueueRetrySettingsTests(unittest.TestCase):
    def test_load_queue_retry_settings_parses_values(self) -> None:
        settings = load_queue_retry_settings(
            {
                'QUEUE_RETRY_BACKOFF_ENABLED': 'on',
                'QUEUE_RETRY_MAX_DELAY': '120.5',
                'QUEUE_RETRY_JITTER': '0.25',
            }
        )

        self.assertTrue(settings.backoff_enabled)
        self.assertEqual(settings.max_delay, 120.5)
        self.assertEqual(settings.jitter, 0.25)

    def test_load_queue_retry_settings_falls_back_for_invalid_numbers(self) -> None:
        settings = load_queue_retry_settings(
            {
                'QUEUE_RETRY_BACKOFF_ENABLED': 'false',
                'QUEUE_RETRY_MAX_DELAY': 'invalid',
                'QUEUE_RETRY_JITTER': 'invalid',
            }
        )

        self.assertFalse(settings.backoff_enabled)
        self.assertEqual(settings.max_delay, 60.0)
        self.assertEqual(settings.jitter, 0.0)


if __name__ == '__main__':
    unittest.main()
