import logging
import os
import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import AsyncMock, MagicMock, patch

from bootstrap.app import Application


class GetVersionExceptionPathTests(unittest.TestCase):
    def test_returns_dev_sentinel_when_package_metadata_missing(self) -> None:
        with patch('importlib.metadata.version', side_effect=PackageNotFoundError):
            self.assertEqual(Application.get_version(), '0.0.0+dev')

    def test_returns_installed_package_version(self) -> None:
        with patch('importlib.metadata.version', return_value='1.2.3'):
            self.assertEqual(Application.get_version(), '1.2.3')


class ConstructorRouterAutoLoadTests(unittest.TestCase):
    def test_constructor_loads_router_from_registry_when_none(self) -> None:
        fake_router = MagicMock(name='router')
        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database'),
            patch('bootstrap.app.RouterRegistry') as registry_cls,
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'false'}, clear=True),
        ):
            registry = MagicMock()
            registry.discover_and_load_routers.return_value = fake_router
            registry_cls.return_value = registry
            app = Application(router=None, env_file='.env')

        self.assertIs(app.router, fake_router)

    def test_constructor_falls_back_to_empty_router_on_load_failure(self) -> None:
        with (
            patch.object(Application, 'print_banner'),
            patch.object(Application, '_setup_logging', lambda app, **_: setattr(app, 'logger', MagicMock())),
            patch.object(Application, '_setup_database'),
            patch('bootstrap.app.RouterRegistry', side_effect=RuntimeError('registry boom')),
            patch('bootstrap.app.asyncio.new_event_loop', return_value=MagicMock()),
            patch('bootstrap.app.asyncio.set_event_loop'),
            patch('bootstrap.app.WorkerManager'),
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false', 'ENABLE_REDIS': 'false'}, clear=True),
        ):
            app = Application(router=None)

        self.assertIsNotNone(app.router)


class SetupLoggingExtraPathsTests(unittest.TestCase):
    def setUp(self) -> None:
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        self.addCleanup(lambda: setattr(root, 'handlers', original_handlers))

    def test_setup_logging_time_rotation(self) -> None:
        app = object.__new__(Application)
        with (
            patch('routemq.logging_config.logging.basicConfig') as basic_config,
            patch.dict(
                os.environ,
                {
                    'LOG_TO_FILE': 'true',
                    'LOG_FILE': '/tmp/test-routemq.log',
                    'LOG_ROTATION_TYPE': 'time',
                    'LOG_ROTATION_WHEN': 'D',
                    'LOG_ROTATION_INTERVAL': '2',
                },
                clear=True,
            ),
            patch('routemq.logging_config.Path') as path_cls,
        ):
            path_cls.return_value.parent.mkdir = MagicMock()
            app._setup_logging()

        self.assertEqual(app.logger.name, 'RouteMQ.Application')
        for handler in basic_config.call_args.kwargs['handlers']:
            handler.close()

    def test_setup_logging_file_handler_failure_falls_back(self) -> None:
        app = object.__new__(Application)
        with (
            patch('routemq.logging_config.logging.basicConfig'),
            patch('routemq.logging_config.logging.handlers.RotatingFileHandler', side_effect=OSError('no disk')),
            patch.dict(
                os.environ,
                {'LOG_TO_FILE': 'true', 'LOG_FILE': '/tmp/test-routemq.log'},
                clear=True,
            ),
            patch('routemq.logging_config.Path') as path_cls,
            patch('builtins.print'),
        ):
            path_cls.return_value.parent.mkdir = MagicMock()
            app._setup_logging()

        self.assertEqual(app.logger.name, 'RouteMQ.Application')


class SetupDatabaseTests(unittest.TestCase):
    def test_setup_database_uses_env_to_build_connection_string(self) -> None:
        app = object.__new__(Application)
        with (
            patch('bootstrap.app.Model.configure') as configure,
            patch.dict(
                os.environ,
                {
                    'DB_HOST': 'h',
                    'DB_PORT': '4242',
                    'DB_NAME': 'db',
                    'DB_USER': 'u',
                    'DB_PASS': 'p',
                },
                clear=True,
            ),
        ):
            app._setup_database()

        configure.assert_called_once()
        self.assertEqual(configure.call_args.args[0], 'mysql+aiomysql://u:p@h:4242/db')


class ConnectionsEnabledTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_database_calls_create_tables_when_enabled(self) -> None:
        app = object.__new__(Application)
        app.mysql_enabled = True
        with patch('bootstrap.app.Model.create_tables', new=AsyncMock()) as create_tables:
            await app.initialize_database()
        create_tables.assert_awaited_once()

    async def test_initialize_redis_logs_success(self) -> None:
        app = object.__new__(Application)
        app.redis_enabled = True
        app.logger = MagicMock()
        with patch('bootstrap.app.redis_manager.initialize', new=AsyncMock(return_value=True)):
            await app.initialize_redis()
        app.logger.info.assert_called()

    async def test_initialize_redis_logs_warning_on_failure(self) -> None:
        app = object.__new__(Application)
        app.redis_enabled = True
        app.logger = MagicMock()
        with patch('bootstrap.app.redis_manager.initialize', new=AsyncMock(return_value=False)):
            await app.initialize_redis()
        app.logger.warning.assert_called()

    async def test_initialize_connections_invokes_both(self) -> None:
        app = object.__new__(Application)
        app.initialize_database = AsyncMock()
        app.initialize_redis = AsyncMock()
        await app._initialize_connections()
        app.initialize_database.assert_awaited_once()
        app.initialize_redis.assert_awaited_once()

    async def test_cleanup_connections_disconnects_redis_and_model_when_enabled(self) -> None:
        app = object.__new__(Application)
        app.redis_enabled = True
        app.mysql_enabled = True
        with (
            patch('bootstrap.app.redis_manager.disconnect', new=AsyncMock()) as disconnect,
            patch('bootstrap.app.Model.cleanup', new=AsyncMock()) as cleanup,
        ):
            await app._cleanup_connections()
        disconnect.assert_awaited_once()
        cleanup.assert_awaited_once()


class OnConnectTests(unittest.TestCase):
    def test_on_connect_subscribes_to_non_shared_routes(self) -> None:
        app = object.__new__(Application)
        app.logger = MagicMock()
        route_shared = MagicMock(shared=True)
        route_normal = MagicMock(shared=False, qos=1)
        route_normal.get_subscription_topic.return_value = 'devices/+/status'
        app.router = MagicMock(routes=[route_shared, route_normal])
        client = MagicMock()

        app._on_connect(client, None, None, 0)

        client.subscribe.assert_called_once_with('devices/+/status', 1)


class OnMessageErrorTests(unittest.TestCase):
    def test_on_message_swallows_dispatcher_exception(self) -> None:
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.loop = MagicMock()
        app.router = MagicMock()
        with patch(
            'bootstrap.app.asyncio.run_coroutine_threadsafe',
            side_effect=RuntimeError('schedule failed'),
        ):
            msg = MagicMock(topic='t', payload=b'{}')
            app._on_message(MagicMock(), None, msg)
        app.logger.error.assert_called()


class WorkerLifecycleTests(unittest.TestCase):
    def test_start_workers_uses_total_from_router(self) -> None:
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.router = MagicMock()
        app.router.get_total_workers_needed.return_value = 3
        app.worker_manager = MagicMock()
        app.start_workers()
        app.worker_manager.start_workers.assert_called_once_with(3)

    def test_start_workers_skips_when_no_shared_routes(self) -> None:
        app = object.__new__(Application)
        app.logger = MagicMock()
        app.router = MagicMock()
        app.router.get_total_workers_needed.return_value = 0
        app.worker_manager = MagicMock()
        app.start_workers()
        app.worker_manager.start_workers.assert_not_called()


class RunCleanupTests(unittest.TestCase):
    def test_run_disconnects_redis_and_cleans_model_when_enabled(self) -> None:
        app = object.__new__(Application)
        app.client = MagicMock()
        app.logger = MagicMock()
        app.worker_manager = MagicMock()
        app.worker_manager.get_worker_count.return_value = 0
        app.loop = MagicMock()
        app.loop.run_forever.side_effect = KeyboardInterrupt()
        app.loop.run_until_complete = MagicMock()
        app.mysql_enabled = True
        app.redis_enabled = True
        app.start_workers = MagicMock()
        app.initialize_database = MagicMock(return_value=None)
        app.initialize_redis = MagicMock(return_value=None)

        with (
            patch('bootstrap.app.redis_manager.disconnect', new=MagicMock()) as disconnect,
            patch('bootstrap.app.Model.cleanup', new=MagicMock()) as cleanup,
        ):
            app.run()

        self.assertGreaterEqual(app.loop.run_until_complete.call_count, 4)


if __name__ == '__main__':
    unittest.main()
