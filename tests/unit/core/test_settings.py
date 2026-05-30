import unittest
from unittest.mock import patch

from routemq.metrics.registry import DEFAULT_HISTOGRAM_BUCKETS
from routemq.settings import (
    load_database_connection_settings,
    load_queue_reliability_settings,
    load_database_pool_settings,
    load_health_http_settings,
    load_metrics_http_settings,
    load_mqtt_settings,
    load_queue_retry_settings,
    load_telemetry_settings,
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


class DatabaseConnectionSettingsTests(unittest.TestCase):
    def test_defaults_preserve_legacy_mysql_url(self) -> None:
        settings = load_database_connection_settings({})

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.connection, 'mysql')
        self.assertEqual(settings.url, 'mysql+aiomysql://root:@localhost:3306/mqtt_framework')
        self.assertFalse(settings.auto_create_tables)

    def test_database_auto_create_tables_is_explicit_opt_in(self) -> None:
        settings = load_database_connection_settings({'DB_AUTO_CREATE_TABLES': 'true'})

        self.assertTrue(settings.auto_create_tables)

    def test_enable_mysql_false_disables_database_without_url(self) -> None:
        settings = load_database_connection_settings({'ENABLE_MYSQL': 'false'})

        self.assertFalse(settings.enabled)

    def test_database_url_wins_and_normalizes_driver(self) -> None:
        settings = load_database_connection_settings({'ENABLE_MYSQL': 'false', 'DATABASE_URL': 'postgres://u:p@db:5432/app'})

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.url, 'postgresql+asyncpg://u:p@db:5432/app')

    def test_postgres_selector_builds_asyncpg_url(self) -> None:
        settings = load_database_connection_settings(
            {
                'DB_CONNECTION': 'postgres',
                'DB_HOST': 'postgres',
                'DB_NAME': 'app',
                'DB_USER': 'route',
                'DB_PASSWORD': 'secret',
            }
        )

        self.assertEqual(settings.connection, 'postgres')
        self.assertEqual(settings.url, 'postgresql+asyncpg://route:secret@postgres:5432/app')

    def test_mysql_selector_keeps_db_pass_alias(self) -> None:
        settings = load_database_connection_settings({'DB_CONNECTION': 'mysql', 'DB_PASS': 'legacy'})

        self.assertEqual(settings.url, 'mysql+aiomysql://root:legacy@localhost:3306/mqtt_framework')

    def test_invalid_selector_falls_back_to_mysql(self) -> None:
        settings = load_database_connection_settings({'DB_CONNECTION': 'sqlite'})

        self.assertEqual(settings.connection, 'mysql')


class TelemetrySettingsTests(unittest.TestCase):
    def test_defaults_disable_telemetry(self) -> None:
        settings = load_telemetry_settings({})

        self.assertFalse(settings.enabled)
        self.assertEqual(settings.connection, 'clickhouse')
        self.assertEqual(settings.url, 'http://localhost:8123/default')

    def test_explicit_connection_enables_and_parses_runtime(self) -> None:
        settings = load_telemetry_settings(
            {
                'ENABLE_TELEMETRY': 'true',
                'TELEMETRY_CONNECTION': 'influxdb',
                'TELEMETRY_URL': 'http://influx:8086?bucket=iot&org=factory',
                'TELEMETRY_QUEUE_MAX_SIZE': '12',
                'TELEMETRY_QUEUE_FULL_STRATEGY': 'drop_oldest',
                'TELEMETRY_BATCH_SIZE': '7',
                'TELEMETRY_FLUSH_INTERVAL': '0.25',
                'TELEMETRY_FLUSH_TIMEOUT': '2',
                'TELEMETRY_MAX_RETRIES': '5',
                'TELEMETRY_RETRY_BACKOFF': 'constant',
                'TELEMETRY_ASYNC_INSERT': 'false',
                'ENABLE_TSDB': 'true',
                'TSDB_BATCH_SIZE': '99',
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.connection, 'influxdb')
        self.assertEqual(settings.queue_max_size, 12)
        self.assertEqual(settings.queue_full_strategy, 'drop_oldest')
        self.assertEqual(settings.batch_size, 7)
        self.assertEqual(settings.flush_interval, 0.25)
        self.assertEqual(settings.flush_timeout, 2)
        self.assertEqual(settings.max_retries, 5)
        self.assertEqual(settings.retry_backoff, 'constant')
        self.assertFalse(settings.async_insert)

    def test_legacy_tsdb_enables_clickhouse_defaults(self) -> None:
        settings = load_telemetry_settings(
            {
                'ENABLE_TSDB': 'true',
                'TSDB_HOST': 'clickhouse',
                'TSDB_PORT': '9000',
                'TSDB_DATABASE': 'iot',
                'TSDB_BATCH_SIZE': '88',
                'TSDB_BUFFER_MAXSIZE': '99',
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.connection, 'clickhouse')
        self.assertEqual(settings.url, 'http://clickhouse:9000/iot')
        self.assertEqual(settings.batch_size, 88)
        self.assertEqual(settings.queue_max_size, 99)

    def test_enable_telemetry_false_overrides_legacy_tsdb_enable(self) -> None:
        settings = load_telemetry_settings({'ENABLE_TELEMETRY': 'false', 'ENABLE_TSDB': 'true'})

        self.assertFalse(settings.enabled)

    def test_explicit_telemetry_url_wins_over_legacy_clickhouse_fields(self) -> None:
        settings = load_telemetry_settings(
            {
                'TELEMETRY_URL': 'http://new-clickhouse:8123/canonical',
                'TSDB_HOST': 'legacy-clickhouse',
                'TSDB_DATABASE': 'legacy',
            }
        )

        self.assertEqual(settings.url, 'http://new-clickhouse:8123/canonical')

    def test_invalid_values_fall_back_to_safe_defaults(self) -> None:
        settings = load_telemetry_settings(
            {
                'TELEMETRY_CONNECTION': 'unknown',
                'TELEMETRY_QUEUE_MAX_SIZE': '-1',
                'TELEMETRY_QUEUE_FULL_STRATEGY': 'discard',
                'TELEMETRY_BATCH_SIZE': '0',
                'TELEMETRY_FLUSH_INTERVAL': '-1',
                'TELEMETRY_FLUSH_TIMEOUT': 'bad',
                'TELEMETRY_RETRY_BACKOFF': 'weird',
            }
        )

        self.assertEqual(settings.connection, 'clickhouse')
        self.assertEqual(settings.queue_max_size, 10000)
        self.assertEqual(settings.queue_full_strategy, 'block')
        self.assertEqual(settings.batch_size, 1)
        self.assertEqual(settings.flush_interval, 1.0)
        self.assertEqual(settings.flush_timeout, 10.0)
        self.assertEqual(settings.retry_backoff, 'exponential')

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


class MetricsHttpSettingsTests(unittest.TestCase):
    def test_load_metrics_http_settings_defaults(self) -> None:
        settings = load_metrics_http_settings({})

        self.assertFalse(settings.enabled)
        self.assertEqual(settings.path, '/metrics')
        self.assertFalse(settings.separate)
        self.assertEqual(settings.host, '127.0.0.1')
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.namespace, 'routemq')
        self.assertEqual(settings.histogram_buckets, DEFAULT_HISTOGRAM_BUCKETS)
        self.assertEqual(settings.default_labels, {})

    def test_load_metrics_http_settings_parses_all_fields(self) -> None:
        settings = load_metrics_http_settings(
            {
                'METRICS_HTTP_ENABLED': 'true',
                'METRICS_HTTP_PATH': '/internal/metrics',
                'METRICS_HTTP_SEPARATE': 'yes',
                'METRICS_HTTP_HOST': '0.0.0.0',
                'METRICS_HTTP_PORT': '9090',
                'METRICS_NAMESPACE': 'custom',
                'METRICS_HISTOGRAM_BUCKETS': '0.1, 0.5, 1.0',
                'METRICS_DEFAULT_LABELS': 'env=prod, region=us-east-1,broken,no_key=,=missing',
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.path, '/internal/metrics')
        self.assertTrue(settings.separate)
        self.assertEqual(settings.host, '0.0.0.0')
        self.assertEqual(settings.port, 9090)
        self.assertEqual(settings.namespace, 'custom')
        self.assertEqual(settings.histogram_buckets, (0.1, 0.5, 1.0))
        self.assertEqual(settings.default_labels, {'env': 'prod', 'region': 'us-east-1', 'no_key': ''})

    def test_load_metrics_http_settings_inherits_health_bind_defaults(self) -> None:
        settings = load_metrics_http_settings(
            {
                'HEALTH_HTTP_HOST': '127.0.0.2',
                'HEALTH_HTTP_PORT': '8181',
            }
        )

        self.assertEqual(settings.host, '127.0.0.2')
        self.assertEqual(settings.port, 8181)

    def test_load_metrics_http_settings_falls_back_for_invalid_numbers(self) -> None:
        settings = load_metrics_http_settings(
            {
                'METRICS_HTTP_ENABLED': 'true',
                'METRICS_HTTP_PORT': 'invalid',
                'METRICS_HISTOGRAM_BUCKETS': '0.1,invalid',
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.histogram_buckets, DEFAULT_HISTOGRAM_BUCKETS)


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


class QueueReliabilitySettingsTests(unittest.TestCase):
    def test_load_queue_reliability_settings_defaults(self) -> None:
        settings = load_queue_reliability_settings({})

        self.assertEqual(settings.visibility_timeout, 300)
        self.assertEqual(settings.reaper_interval, 30)
        self.assertEqual(settings.shutdown_grace, 300)
        self.assertEqual(settings.heartbeat_interval, 10)

    def test_load_queue_reliability_settings_parses_values(self) -> None:
        settings = load_queue_reliability_settings(
            {
                'QUEUE_VISIBILITY_TIMEOUT': '120',
                'QUEUE_REAPER_INTERVAL': '15',
                'QUEUE_SHUTDOWN_GRACE': '45',
                'QUEUE_HEARTBEAT_INTERVAL': '5',
            }
        )

        self.assertEqual(settings.visibility_timeout, 120)
        self.assertEqual(settings.reaper_interval, 15)
        self.assertEqual(settings.shutdown_grace, 45)
        self.assertEqual(settings.heartbeat_interval, 5)

    def test_load_queue_reliability_settings_falls_back_for_invalid_numbers(self) -> None:
        settings = load_queue_reliability_settings(
            {
                'QUEUE_VISIBILITY_TIMEOUT': 'invalid',
                'QUEUE_REAPER_INTERVAL': '-1',
                'QUEUE_SHUTDOWN_GRACE': 'invalid',
                'QUEUE_HEARTBEAT_INTERVAL': '-2',
            }
        )

        self.assertEqual(settings.visibility_timeout, 300)
        self.assertEqual(settings.reaper_interval, 30)
        self.assertEqual(settings.shutdown_grace, 300)
        self.assertEqual(settings.heartbeat_interval, 10)


if __name__ == '__main__':
    unittest.main()
