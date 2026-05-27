import logging
import os
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from bootstrap.app import Application


class TestApplicationInitialization(unittest.TestCase):
    def test_constructor_uses_supplied_router_and_disables_services(self) -> None:
        """Constructor honors explicit router and service env gates."""
        router = MagicMock(name='router')

        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database') as setup_database,
            patch('bootstrap.app.load_dotenv') as load_dotenv,
            patch('bootstrap.app.asyncio.get_event_loop', return_value=MagicMock(name='loop')),
            patch('bootstrap.app.WorkerManager') as worker_manager,
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'false'}, clear=True),
        ):
            app = Application(router=router, env_file='custom.env', router_directory='custom.routers')

        self.assertIs(app.router, router)
        load_dotenv.assert_called_once_with('custom.env')
        setup_database.assert_not_called()
        worker_manager.assert_called_once_with(router, 'mqtt_framework_group', 'custom.routers')

    def test_constructor_sets_up_database_when_mysql_enabled(self) -> None:
        """ENABLE_MYSQL=true keeps database setup in the boot path."""
        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database') as setup_database,
            patch('bootstrap.app.asyncio.get_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(os.environ, {'ENABLE_MYSQL': 'true', 'ENABLE_REDIS': 'false'}, clear=True),
        ):
            Application(router=MagicMock())

        setup_database.assert_called_once_with()

    def test_constructor_records_redis_gate_when_enabled(self) -> None:
        """ENABLE_REDIS=true is stored without opening Redis during construction."""
        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database'),
            patch('bootstrap.app.asyncio.get_event_loop', return_value=MagicMock()),
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
            patch('bootstrap.app.logging.basicConfig') as basic_config,
            patch.dict(
                os.environ,
                {'LOG_LEVEL': 'debug', 'LOG_TO_FILE': 'false', 'LOG_FORMAT': '%(levelname)s:%(message)s'},
                clear=True,
            ),
        ):
            app._setup_logging()

        basic_config.assert_called_once()
        self.assertEqual(basic_config.call_args.kwargs['level'], logging.DEBUG)
        self.assertEqual(basic_config.call_args.kwargs['format'], '%(levelname)s:%(message)s')

    def test_setup_logging_uses_log_file_environment(self) -> None:
        """File logging uses LOG_FILE when rotation is enabled."""
        app = object.__new__(Application)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / 'app.log')
            with patch.dict(os.environ, {'LOG_FILE': log_file, 'LOG_TO_FILE': 'true'}, clear=True):
                app._setup_logging()

        self.assertEqual(logging.getLogger('RouteMQ.Application').name, app.logger.name)


class TestApplicationConnections(unittest.IsolatedAsyncioTestCase):
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
            patch('bootstrap.app.mqtt_client.Client', return_value=fake_client) as client_class,
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
            patch('bootstrap.app.mqtt_client.Client', return_value=fake_client),
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

        app.router.dispatch.assert_called_once_with('devices/1', {'ok': True}, client)
        run_threadsafe.assert_called_once_with(app.router.dispatch.return_value, app.loop)

    def test_on_message_uses_raw_payload_when_json_decode_fails(self) -> None:
        """Invalid JSON payloads are still dispatched as raw bytes."""
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.loop = MagicMock()
        app.router = MagicMock()
        app.router.dispatch.return_value = MagicMock(name='coroutine')
        msg = MagicMock(topic='raw/topic', payload=b'not-json')

        with patch('bootstrap.app.asyncio.run_coroutine_threadsafe'):
            app._on_message(MagicMock(), None, msg)

        self.assertEqual(app.router.dispatch.call_args.args[1], b'not-json')

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
        app.start_workers = MagicMock()
        app.initialize_database = MagicMock(return_value=None)
        app.initialize_redis = MagicMock(return_value=None)

        app.run()

        app.start_workers.assert_called_once_with()
        app.client.loop_stop.assert_called_once_with()
        app.worker_manager.stop_workers.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
