import logging
import logging.handlers
import os
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from bootstrap.app import Application
from routemq.health import HealthStatus
from routemq.metrics import MetricsRegistry
from routemq.settings import DatabasePoolSettings, MetricsHttpSettings, load_metrics_http_settings


class TestApplicationInitialization(unittest.TestCase):
    def test_constructor_uses_supplied_router_and_disables_services(self) -> None:
        """Constructor honors explicit router and service env gates."""
        router = MagicMock(name='router')

        with (
            patch.object(Application, 'print_banner') as print_banner,
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database') as setup_database,
            patch('bootstrap.app.load_dotenv') as load_dotenv,
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock(name='loop')),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager') as worker_manager,
            patch.dict(
                os.environ,
                {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'false', 'LOG_FORMATTER': 'plain'},
                clear=True,
            ),
        ):
            app = Application(router=router, env_file='custom.env', router_directory='custom.routers')

        self.assertIs(app.router, router)
        print_banner.assert_called_once_with()
        load_dotenv.assert_called_once_with('custom.env')
        setup_database.assert_not_called()
        worker_manager.assert_called_once_with(router, 'mqtt_framework_group', 'custom.routers')

    def test_constructor_skips_banner_when_disabled(self) -> None:
        """show_banner=False lets callers own their startup output."""
        router = MagicMock(name='router')

        with (
            patch.object(Application, 'print_banner') as print_banner,
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database') as setup_database,
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'false'}, clear=True),
        ):
            Application(router=router, show_banner=False)

        print_banner.assert_not_called()
        setup_database.assert_not_called()

    def test_constructor_skips_banner_when_json_logging_enabled(self) -> None:
        """JSON logging keeps stdout as NDJSON by suppressing banner text."""
        router = MagicMock(name='router')

        with (
            patch.object(Application, 'print_banner') as print_banner,
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database') as setup_database,
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(
                os.environ,
                {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'false', 'LOG_FORMATTER': 'json'},
                clear=True,
            ),
        ):
            Application(router=router, show_banner=True)

        print_banner.assert_not_called()
        setup_database.assert_not_called()

    def test_constructor_can_disable_console_logging(self) -> None:
        """Embedded callers can keep app logs out of their console."""
        router = MagicMock(name='router')

        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', autospec=True) as setup_logging,
            patch.object(Application, '_setup_database') as setup_database,
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'false'}, clear=True),
        ):
            setup_logging.side_effect = lambda app, **_: setattr(app, 'logger', MagicMock())
            Application(router=router, show_banner=False, log_to_console=False)

        self.assertFalse(setup_logging.call_args.kwargs['log_to_console'])
        setup_database.assert_not_called()

    def test_constructor_sets_up_database_when_mysql_enabled(self) -> None:
        """ENABLE_MYSQL=true keeps database setup in the boot path."""
        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database') as setup_database,
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(os.environ, {'ENABLE_MYSQL': 'true', 'ENABLE_REDIS': 'false'}, clear=True),
        ):
            Application(router=MagicMock())

        setup_database.assert_called_once_with()

    def test_constructor_records_redis_gate_when_enabled(self) -> None:
        """ENABLE_REDIS=true is stored without opening Redis during construction."""
        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database'),
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'true'}, clear=True),
        ):
            app = Application(router=MagicMock())

        self.assertTrue(app.redis_enabled)


class TestApplicationBanner(unittest.TestCase):
    def test_get_version_reads_installed_package_version(self) -> None:
        """Version source is the installed routemq distribution metadata."""
        with patch('importlib.metadata.version', return_value='9.8.7') as version:
            resolved = Application.get_version()

        version.assert_called_once_with('routemq')
        self.assertEqual(resolved, '9.8.7')

    def test_get_version_falls_back_when_package_missing(self) -> None:
        """Src checkouts without installed metadata use the dev sentinel."""
        with patch('importlib.metadata.version', side_effect=PackageNotFoundError):
            version = Application.get_version()

        self.assertEqual(version, '0.0.0+dev')

    def test_print_banner_includes_version_and_system_info(self) -> None:
        """Banner output keeps version and runtime facts visible."""
        memory = MagicMock(total=2 * 1024**3)

        with (
            patch.object(Application, 'get_version', return_value='1.2.3'),
            patch('bootstrap.app.platform.system', return_value='TestOS'),
            patch('bootstrap.app.psutil.cpu_count', return_value=8),
            patch('bootstrap.app.psutil.virtual_memory', return_value=memory),
            patch('builtins.print') as print_mock,
        ):
            Application.print_banner()

        self.assertIn('1.2.3', print_mock.call_args.args[0])


class TestApplicationLogging(unittest.TestCase):
    def test_setup_logging_respects_console_level_and_format(self) -> None:
        """Logging configuration reads level and format from environment."""
        app = object.__new__(Application)

        with (
            patch('routemq.logging_config.logging.basicConfig') as basic_config,
            patch.dict(
                os.environ,
                {'LOG_LEVEL': 'debug', 'LOG_TO_FILE': 'false', 'LOG_FORMAT': '%(levelname)s:%(message)s'},
                clear=True,
            ),
        ):
            app._setup_logging()

        basic_config.assert_called_once()
        self.assertEqual(basic_config.call_args.kwargs['level'], logging.DEBUG)
        handlers = basic_config.call_args.kwargs['handlers']
        self.assertTrue(any(type(handler) is logging.StreamHandler for handler in handlers))
        stream_handler = next(handler for handler in handlers if type(handler) is logging.StreamHandler)
        formatter = stream_handler.formatter
        self.assertIsNotNone(formatter)
        assert formatter is not None
        record = logging.LogRecord('RouteMQ.Test', logging.INFO, __file__, 1, 'hello', (), None)
        self.assertEqual(formatter.format(record), 'INFO:hello')

    def test_setup_logging_can_omit_console_handler(self) -> None:
        """Quiet embedded startup keeps file logging without a console stream."""
        app = object.__new__(Application)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / 'app.log')
            with (
                patch('routemq.logging_config.logging.basicConfig') as basic_config,
                patch.dict(os.environ, {'LOG_FILE': log_file, 'LOG_TO_FILE': 'true'}, clear=True),
            ):
                app._setup_logging(log_to_console=False)

        handlers = basic_config.call_args.kwargs['handlers']
        self.assertFalse(any(type(handler) is logging.StreamHandler for handler in handlers))
        self.assertTrue(any(isinstance(handler, logging.handlers.RotatingFileHandler) for handler in handlers))
        for handler in handlers:
            handler.close()

    def test_setup_logging_uses_null_handler_when_fully_quiet(self) -> None:
        """basicConfig must not synthesize a console handler when no outputs are enabled."""
        app = object.__new__(Application)

        with (
            patch('routemq.logging_config.logging.basicConfig') as basic_config,
            patch.dict(os.environ, {'LOG_TO_FILE': 'false'}, clear=True),
        ):
            app._setup_logging(log_to_console=False)

        handlers = basic_config.call_args.kwargs['handlers']
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], logging.NullHandler)

    def test_setup_logging_uses_log_file_environment(self) -> None:
        """File logging uses LOG_FILE when rotation is enabled."""
        app = object.__new__(Application)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / 'app.log')
            with (
                patch('routemq.logging_config.logging.basicConfig') as basic_config,
                patch.dict(
                    os.environ,
                    {'LOG_FILE': log_file, 'LOG_TO_FILE': 'true', 'LOG_TO_CONSOLE': 'false'},
                    clear=True,
                ),
            ):
                app._setup_logging()

        self.assertEqual(logging.getLogger('RouteMQ.Application').name, app.logger.name)
        for handler in basic_config.call_args.kwargs['handlers']:
            handler.close()


class TestApplicationMetrics(unittest.TestCase):
    def test_constructor_installs_metrics_registry_and_default_hooks(self) -> None:
        router = MagicMock(name='router')
        registry = MagicMock(name='metrics_registry')
        hook_handle = MagicMock(name='metrics_hooks_handle')

        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database'),
            patch.object(Application, '_setup_metrics'),
            patch('bootstrap.app.MetricsRegistry', return_value=registry) as registry_cls,
            patch('bootstrap.app.install_default_hooks', return_value=hook_handle) as install_hooks,
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(
                os.environ,
                {
                    'ENABLE_MYSQL': 'false',
                    'ENABLE_REDIS': 'false',
                    'METRICS_NAMESPACE': 'custom',
                    'METRICS_HISTOGRAM_BUCKETS': '0.25,1.0',
                },
                clear=True,
            ),
        ):
            app = Application(router=router, show_banner=False)

        registry_cls.assert_called_once_with()
        install_hooks.assert_called_once_with(registry, namespace='custom', histogram_buckets=(0.25, 1.0))
        self.assertIs(app.metrics_registry, registry)
        self.assertIs(app.metrics_hooks_handle, hook_handle)

    def test_setup_metrics_does_not_build_renderer_when_disabled(self) -> None:
        app = object.__new__(Application)
        app.health_status = HealthStatus()
        app.metrics_settings = load_metrics_http_settings({})
        health_server = MagicMock(name='health_server')

        with (
            patch.object(Application, '_build_metrics_renderer') as build_renderer,
            patch('bootstrap.app.health_server_from_env', return_value=health_server) as from_env,
        ):
            app._setup_metrics()

        build_renderer.assert_not_called()
        from_env.assert_called_once_with(app.health_status, metrics_renderer=None, metrics_path='/metrics')
        self.assertIs(app.health_server, health_server)
        self.assertIsNone(app.metrics_health_server)

    def test_build_metrics_renderer_closes_over_registry_and_default_labels(self) -> None:
        app = object.__new__(Application)
        app.metrics_registry = MetricsRegistry()
        app.metrics_registry.counter('routemq_test_counter', help='h').inc()
        settings = MetricsHttpSettings(enabled=True, default_labels={'env': 'test'})

        with patch('bootstrap.app.find_spec', return_value=None):
            renderer = app._build_metrics_renderer(settings)

        content_type, body = renderer(None)

        self.assertEqual(content_type, 'text/plain; version=0.0.4; charset=utf-8')
        self.assertIn(b'routemq_test_counter_total{env="test"} 1', body)

    def test_setup_metrics_configures_separate_metrics_server(self) -> None:
        app = object.__new__(Application)
        app.health_status = HealthStatus()
        app.metrics_settings = MetricsHttpSettings(
            enabled=True,
            separate=True,
            host='127.0.0.2',
            port=9090,
            path='/internal/metrics',
        )
        renderer = MagicMock(name='renderer')
        health_server = MagicMock(name='health_server')
        metrics_server = MagicMock(name='metrics_server')

        with (
            patch.object(Application, '_build_metrics_renderer', return_value=renderer),
            patch('bootstrap.app.health_server_from_env', return_value=health_server),
            patch('bootstrap.app.HealthServer', return_value=metrics_server) as health_server_cls,
        ):
            app._setup_metrics()

        self.assertIs(app.health_server, health_server)
        self.assertIs(app.metrics_health_server, metrics_server)
        health_server_cls.assert_called_once_with(
            app.health_status,
            host='127.0.0.2',
            port=9090,
            metrics_renderer=renderer,
            metrics_path='/internal/metrics',
        )

    def test_run_starts_and_stops_separate_metrics_server(self) -> None:
        app = object.__new__(Application)
        app.client = None
        app.logger = MagicMock()
        app.worker_manager = MagicMock()
        app.worker_manager.get_worker_count.return_value = 0
        app.loop = MagicMock(name='loop')
        app.loop.run_forever.side_effect = KeyboardInterrupt
        app.mysql_enabled = False
        app.redis_enabled = False
        app.tsdb_enabled = False
        app.start_workers = MagicMock()
        app.initialize_database = MagicMock(return_value=None)
        app.initialize_redis = MagicMock(return_value=None)
        app.initialize_tsdb = MagicMock(return_value=None)
        app.health_status = HealthStatus()
        app.health_server = MagicMock(name='health_server')
        app.metrics_health_server = MagicMock(name='metrics_health_server')

        app.run()

        app.health_server.start.assert_called_once_with()
        app.metrics_health_server.start.assert_called_once_with()
        app.health_server.stop.assert_called_once_with()
        app.metrics_health_server.stop.assert_called_once_with()


class TestApplicationConnections(unittest.IsolatedAsyncioTestCase):
    def test_setup_database_passes_pool_settings_to_model(self) -> None:
        app = object.__new__(Application)
        pool_settings = DatabasePoolSettings(
            pool_size=7,
            max_overflow=3,
            pool_timeout=11,
            pool_recycle=600,
            pool_pre_ping=False,
            pool_use_lifo=True,
            pool_class='null',
        )

        with (
            patch.dict(
                os.environ,
                {
                    'DB_HOST': 'db',
                    'DB_PORT': '3307',
                    'DB_NAME': 'app_db',
                    'DB_USER': 'app_user',
                    'DB_PASS': 'secret',
                },
                clear=True,
            ),
            patch('bootstrap.app.load_database_pool_settings', return_value=pool_settings) as load_pool_settings,
            patch('bootstrap.app.Model.configure') as configure,
        ):
            app._setup_database()

        load_pool_settings.assert_called_once_with()
        configure.assert_called_once_with(
            'mysql+aiomysql://app_user:secret@db:3307/app_db',
            pool_size=7,
            max_overflow=3,
            pool_timeout=11,
            pool_recycle=600,
            pool_pre_ping=False,
            pool_use_lifo=True,
            pool_class='null',
        )

    async def test_initialize_database_skips_when_mysql_disabled(self) -> None:
        """Database initialization is gated by mysql_enabled."""
        app = object.__new__(Application)
        app.mysql_enabled = False

        with patch('bootstrap.app.Model.create_tables') as create_tables:
            await app.initialize_database()

        create_tables.assert_not_called()

    async def test_initialize_redis_skips_when_redis_disabled(self) -> None:
        """Redis initialization is gated by redis_enabled."""
        app = object.__new__(Application)
        app.redis_enabled = False

        with patch('bootstrap.app.redis_manager.initialize') as initialize:
            await app.initialize_redis()

        initialize.assert_not_called()

    async def test_cleanup_connections_respects_enabled_flags(self) -> None:
        """Cleanup only calls integrations that were enabled."""
        app = object.__new__(Application)
        app.redis_enabled = False
        app.mysql_enabled = False
        app.tsdb_enabled = False

        with (
            patch('bootstrap.app.redis_manager.disconnect') as disconnect,
            patch('bootstrap.app.Model.cleanup') as cleanup,
        ):
            await app._cleanup_connections()

        disconnect.assert_not_called()
        cleanup.assert_not_called()


class TestApplicationMqtt(unittest.TestCase):
    def test_connect_configures_mqtt_client_from_environment(self) -> None:
        """MQTT connection path binds callbacks and broker configuration."""
        app = object.__new__(Application)
        app.logger = MagicMock()
        fake_client = MagicMock(name='mqtt_client')

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client) as client_class,
            patch.dict(
                os.environ,
                {'MQTT_BROKER': 'broker', 'MQTT_PORT': '1884', 'MQTT_CLIENT_ID': 'client'},
                clear=True,
            ),
        ):
            app.connect()

        client_class.assert_called_once_with(client_id='client')
        fake_client.connect.assert_called_once_with('broker', 1884)
        self.assertEqual(fake_client.on_message, app._on_message)

    def test_connect_sets_credentials_when_both_are_present(self) -> None:
        """MQTT credentials are applied only when username and password exist."""
        app = object.__new__(Application)
        app.logger = MagicMock()
        fake_client = MagicMock(name='mqtt_client')

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch.dict(os.environ, {'MQTT_USERNAME': 'user', 'MQTT_PASSWORD': 'pass'}, clear=True),
        ):
            app.connect()

        fake_client.username_pw_set.assert_called_once_with('user', 'pass')

    def test_on_message_dispatches_decoded_json_to_router_loop(self) -> None:
        """MQTT messages bridge into router.dispatch on the application loop."""
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.loop = MagicMock(name='loop')
        app.router = MagicMock(name='router')
        app.router.dispatch.return_value = MagicMock(name='coroutine')
        msg = MagicMock(topic='devices/1', payload=b'{"ok": true}')
        client = MagicMock(name='client')

        with patch('bootstrap.app.asyncio.run_coroutine_threadsafe') as run_threadsafe:
            app._on_message(client, None, msg)

        app.router.dispatch.assert_not_called()
        run_threadsafe.assert_called_once()
        coro, loop = run_threadsafe.call_args.args
        self.assertIs(loop, app.loop)
        coro.close()

    def test_on_message_uses_raw_payload_when_json_decode_fails(self) -> None:
        """Invalid JSON payloads are still dispatched as raw bytes."""
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.loop = MagicMock()
        app.router = MagicMock()
        app.router.dispatch.return_value = MagicMock(name='coroutine')
        msg = MagicMock(topic='raw/topic', payload=b'not-json')

        with patch('bootstrap.app.asyncio.run_coroutine_threadsafe') as run_threadsafe:
            app._on_message(MagicMock(), None, msg)

        app.router.dispatch.assert_not_called()
        run_threadsafe.call_args.args[0].close()

    def test_on_message_uses_raw_payload_when_unicode_decode_fails(self) -> None:
        """Non-UTF8 payloads are dispatched as their original bytes."""
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.loop = MagicMock()
        app.router = MagicMock()
        app.router.dispatch.return_value = MagicMock(name='coroutine')
        msg = MagicMock(topic='raw/topic', payload=b'\xff\xfe binary')

        with patch('bootstrap.app.asyncio.run_coroutine_threadsafe') as run_threadsafe:
            app._on_message(MagicMock(), None, msg)

        app.router.dispatch.assert_not_called()
        run_threadsafe.call_args.args[0].close()

    def test_on_message_logs_and_lifecycles_scheduling_failure(self) -> None:
        """Scheduling failures emit a failed lifecycle before being swallowed by Paho."""
        app = object.__new__(Application)
        app.logger = logging.getLogger('RouteMQ.Application')
        app.loop = MagicMock(name='loop')
        app.router = MagicMock(name='router')
        msg = MagicMock(topic='devices/1', payload=b'{}')

        with (
            patch('bootstrap.app.asyncio.run_coroutine_threadsafe', side_effect=RuntimeError('loop down')),
            patch('bootstrap.app.observability.lifecycle') as lifecycle,
            self.assertLogs('RouteMQ.Application', level='ERROR') as logs,
        ):
            app._on_message(MagicMock(), None, msg)

        lifecycle.assert_called_once_with(
            'mqtt.message.failed',
            {'process': 'main', 'error': 'RuntimeError', 'mqtt_topic': 'devices/1'},
        )
        self.assertIn('Error processing message on topic devices/1', logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_run_drives_loop_lifecycle_and_cleanup(self) -> None:
        """Run uses the stored event loop and always stops client and workers."""
        app = object.__new__(Application)
        app.client = MagicMock(name='client')
        app.logger = MagicMock()
        app.worker_manager = MagicMock()
        app.worker_manager.get_worker_count.return_value = 0
        app.loop = MagicMock(name='loop')
        app.loop.run_forever.side_effect = KeyboardInterrupt
        app.mysql_enabled = False
        app.redis_enabled = False
        app.tsdb_enabled = False
        app.start_workers = MagicMock()
        app.initialize_database = MagicMock(return_value=None)
        app.initialize_redis = MagicMock(return_value=None)
        app.initialize_tsdb = MagicMock(return_value=None)
        app._cleanup_connections = MagicMock(return_value=None)
        app.health_status = HealthStatus()
        app.health_server = None

        app.run()

        app.start_workers.assert_called_once_with()
        app.client.loop_stop.assert_called_once_with()
        app.worker_manager.stop_workers.assert_called_once_with()

    def test_request_shutdown_marks_not_ready_and_stops_running_loop(self) -> None:
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.health_status = HealthStatus(startup_complete=True, mqtt_connected=True)
        app.loop = MagicMock()
        app.loop.is_running.return_value = True

        app._request_shutdown(15, None)

        self.assertTrue(app._shutdown_requested)
        self.assertTrue(app.health_status.shutting_down)
        app.loop.call_soon_threadsafe.assert_called_once_with(app.loop.stop)


if __name__ == '__main__':
    unittest.main()
