import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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


if __name__ == '__main__':
    unittest.main()
