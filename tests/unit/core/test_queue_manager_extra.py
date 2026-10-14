import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.model import Model
from routemq.queue.database_queue import DatabaseQueue
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager


class FakeQueueDriver(QueueDriver):
    async def push(self, payload: str, queue: str = 'default', delay: int = 0) -> None:
        pass

    async def pop(self, queue: str = 'default') -> dict | None:
        return None

    async def release(self, job_id: int | str, queue: str, delay: int = 0) -> None:
        pass

    async def delete(self, job_id: int | str, queue: str) -> None:
        pass

    async def failed(self, connection: str, queue: str, payload: str, exception: str) -> None:
        pass

    async def size(self, queue: str = 'default') -> int:
        return 0


class NotAQueueDriver:
    pass


class FakeEntryPoint:
    def __init__(self, name: str, loaded):
        self.name = name
        self.loaded = loaded

    def load(self):
        return self.loaded


class PingClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.pings = 0

    async def ping(self) -> bool:
        self.pings += 1
        if self.error is not None:
            raise self.error
        return True


def _redis_manager(client: PingClient | None) -> MagicMock:
    redis_manager = MagicMock()
    redis_manager.is_enabled.return_value = client is not None
    redis_manager.get_client.return_value = client
    redis_manager.initialize = AsyncMock(return_value=True)
    return redis_manager


class QueueManagerExtraTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._env = dict(os.environ)
        os.environ.pop('ENABLE_REDIS', None)
        os.environ.pop('ENABLE_MYSQL', None)
        self._manager_instance = QueueManager._instance
        self._manager_driver = QueueManager._driver
        self._manager_default = QueueManager._default_connection
        self._manager_factories = dict(QueueManager._driver_factories)
        self._manager_entry_points_loaded = QueueManager._entry_points_loaded
        QueueManager._instance = None
        QueueManager._driver = None
        QueueManager._driver_factories = {}
        QueueManager._entry_points_loaded = False

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        QueueManager._instance = self._manager_instance
        QueueManager._driver = self._manager_driver
        QueueManager._default_connection = self._manager_default
        QueueManager._driver_factories = self._manager_factories
        QueueManager._entry_points_loaded = self._manager_entry_points_loaded

    def test_get_driver_raises_for_unknown_connection(self) -> None:
        manager = QueueManager()

        with self.assertRaisesRegex(RuntimeError, 'Unknown queue connection'):
            manager.get_driver('nonexistent')

    def test_resolve_connection_raises_for_unknown_connection(self) -> None:
        manager = QueueManager()

        with self.assertRaisesRegex(RuntimeError, 'Unknown queue connection: nonexistent'):
            manager._resolve_connection('nonexistent')

    async def test_size_delegates_to_driver(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.size = AsyncMock(return_value=42)

        with patch.object(manager, 'get_driver', return_value=driver):
            size = await manager.size(queue='work')

        driver.size.assert_awaited_once_with('work')
        self.assertEqual(size, 42)

    async def test_stats_delegates_to_driver_and_emits_lifecycle(self) -> None:
        manager = QueueManager()
        stats = {'queue': 'work', 'ready': 2, 'reserved': 1, 'delayed': 0, 'failed': 0}
        driver = MagicMock(spec=QueueDriver)
        driver.stats = AsyncMock(return_value=stats)

        with (
            patch.object(manager, 'get_driver', return_value=driver),
            patch('routemq.queue.queue_manager._lifecycle') as lifecycle,
        ):
            result = await manager.stats(queue='work', connection='redis')

        driver.stats.assert_awaited_once_with('work')
        lifecycle.assert_called_once_with('queue.stats', stats)
        self.assertEqual(result, stats)

    async def test_failed_job_admin_methods_delegate_to_driver(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.list_failed_jobs = AsyncMock(return_value=[{'id': '1'}])
        driver.get_failed_job = AsyncMock(return_value={'id': '1'})
        driver.retry_failed_job = AsyncMock(return_value=True)
        driver.forget_failed_job = AsyncMock(return_value=True)
        driver.flush_failed_jobs = AsyncMock(return_value=2)

        with patch.object(manager, 'get_driver', return_value=driver):
            self.assertEqual(await manager.list_failed_jobs(queue='emails', connection='redis'), [{'id': '1'}])
            self.assertEqual(await manager.get_failed_job('1', connection='redis'), {'id': '1'})
            self.assertTrue(await manager.retry_failed_job('1', connection='redis'))
            self.assertTrue(await manager.forget_failed_job('1', connection='redis'))
            self.assertEqual(await manager.flush_failed_jobs(queue='emails', connection='redis'), 2)

        driver.list_failed_jobs.assert_awaited_once_with('emails')
        driver.get_failed_job.assert_awaited_once_with('1')
        driver.retry_failed_job.assert_awaited_once_with('1')
        driver.forget_failed_job.assert_awaited_once_with('1')
        driver.flush_failed_jobs.assert_awaited_once_with('emails')

    def test_register_driver_resolves_custom_connection(self) -> None:
        manager = QueueManager()

        QueueManager.register_driver('fake', FakeQueueDriver)

        self.assertIsInstance(manager.get_driver('fake'), FakeQueueDriver)

    def test_register_driver_rejects_empty_name(self) -> None:
        with self.assertRaisesRegex(ValueError, 'cannot be empty'):
            QueueManager.register_driver(' ', FakeQueueDriver)

    def test_register_driver_rejects_non_driver_class(self) -> None:
        with self.assertRaisesRegex(TypeError, 'must inherit QueueDriver'):
            getattr(QueueManager, 'register_driver')('invalid', NotAQueueDriver)

    def test_get_driver_rejects_factory_that_returns_wrong_type(self) -> None:
        manager = QueueManager()
        QueueManager.register_driver('invalid', MagicMock(return_value=NotAQueueDriver()))

        with self.assertRaisesRegex(TypeError, 'did not return a QueueDriver'):
            manager.get_driver('invalid')

    def test_registered_drivers_includes_builtins(self) -> None:
        self.assertEqual(QueueManager.registered_drivers(), ('database', 'redis'))

    def test_entry_point_driver_is_loaded_once(self) -> None:
        manager = QueueManager()
        entry_point = FakeEntryPoint('fake', FakeQueueDriver)

        with patch('routemq.queue.queue_manager.entry_points', return_value=[entry_point]) as entry_points:
            self.assertIsInstance(manager.get_driver('fake'), FakeQueueDriver)
            self.assertIsInstance(manager.get_driver('fake'), FakeQueueDriver)

        entry_points.assert_called_once_with(group='routemq.queue_drivers')

    def test_entry_point_cannot_override_builtin_driver(self) -> None:
        entry_point = FakeEntryPoint('redis', FakeQueueDriver)

        with patch('routemq.queue.queue_manager.entry_points', return_value=[entry_point]):
            self.assertIn('redis', QueueManager.registered_drivers())

        self.assertIsNot(QueueManager._driver_factories['redis'], FakeQueueDriver)

    async def test_queue_driver_optional_defaults_are_safe_noops(self) -> None:
        driver = FakeQueueDriver()

        self.assertEqual(
            await driver.stats('emails'),
            {
                'queue': 'emails',
                'ready': 0,
                'reserved': 0,
                'delayed': 0,
                'failed': 0,
                'oldest_ready_age_seconds': 0.0,
            },
        )
        self.assertEqual(await driver.reap_expired('emails', 30), 0)
        self.assertFalse(await driver.heartbeat('job-1', 'emails'))
        self.assertIsNone(await driver.write_worker_heartbeat({'worker_id': 'w1'}, 30))
        self.assertIsNone(await driver.mark_worker_dead('w1'))
        self.assertEqual(await driver.list_failed_jobs('emails'), [])
        self.assertIsNone(await driver.get_failed_job('failed:emails:1'))
        self.assertFalse(await driver.retry_failed_job('failed:emails:1'))
        self.assertFalse(await driver.forget_failed_job('failed:emails:1'))
        self.assertEqual(await driver.flush_failed_jobs('emails'), 0)

    async def test_validate_redis_pings_existing_client_without_reinitializing_pool(self) -> None:
        manager = QueueManager()
        client = PingClient()
        redis_manager = _redis_manager(client)

        with patch('routemq.queue.queue_manager.RedisManager', return_value=redis_manager):
            results = [await manager.validate_connection('redis'), await manager.validate_connection('redis')]

        self.assertEqual(results, ['redis', 'redis'])
        self.assertEqual(client.pings, 2)
        redis_manager.initialize.assert_not_awaited()

    async def test_validate_requested_redis_fails_even_when_database_fallback_is_healthy(self) -> None:
        manager = QueueManager()

        with (
            patch('routemq.queue.queue_manager.RedisManager', return_value=_redis_manager(None)),
            patch.object(Model, '_is_enabled', True),
            patch.object(Model, 'validate_connection', new_callable=AsyncMock) as database_validation,
        ):
            delivery_driver = manager.get_driver('redis')
            with self.assertRaisesRegex(RuntimeError, 'Redis queue connection is not available'):
                await manager.validate_connection('redis')

        self.assertIsInstance(delivery_driver, DatabaseQueue)
        database_validation.assert_not_awaited()

    async def test_validate_redis_propagates_ping_failure(self) -> None:
        manager = QueueManager()
        error = ConnectionError('redis refused connection')

        with patch('routemq.queue.queue_manager.RedisManager', return_value=_redis_manager(PingClient(error))):
            with self.assertRaises(ConnectionError) as raised:
                await manager.validate_connection('redis')

        self.assertIs(raised.exception, error)

    async def test_validate_fails_closed_for_custom_driver(self) -> None:
        manager = QueueManager()
        QueueManager.register_driver('fake', FakeQueueDriver)

        with patch('routemq.queue.queue_manager.RedisManager') as redis_manager:
            with self.assertRaisesRegex(RuntimeError, "not supported for queue connection 'fake'"):
                await manager.validate_connection('fake')

        redis_manager.assert_not_called()

    async def test_validate_fails_closed_when_builtin_name_is_registered_to_custom_driver(self) -> None:
        manager = QueueManager()
        QueueManager.register_driver('redis', FakeQueueDriver)
        client = PingClient()

        with patch('routemq.queue.queue_manager.RedisManager', return_value=_redis_manager(client)):
            with self.assertRaisesRegex(RuntimeError, "not supported for queue connection 'redis'"):
                await manager.validate_connection('redis')

        self.assertEqual(client.pings, 0)


if __name__ == '__main__':
    unittest.main()
