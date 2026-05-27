import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager


class QueueManagerExtraTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._env = dict(os.environ)
        os.environ.pop('ENABLE_REDIS', None)
        os.environ.pop('ENABLE_MYSQL', None)
        self._manager_instance = QueueManager._instance
        self._manager_driver = QueueManager._driver
        self._manager_default = QueueManager._default_connection
        QueueManager._instance = None
        QueueManager._driver = None

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        QueueManager._instance = self._manager_instance
        QueueManager._driver = self._manager_driver
        QueueManager._default_connection = self._manager_default

    def test_get_driver_raises_for_unknown_connection(self) -> None:
        manager = QueueManager()

        with self.assertRaisesRegex(RuntimeError, 'Unknown queue connection'):
            manager.get_driver('nonexistent')

    async def test_size_delegates_to_driver(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.size = AsyncMock(return_value=42)

        with patch.object(manager, 'get_driver', return_value=driver):
            size = await manager.size(queue='work')

        driver.size.assert_awaited_once_with('work')
        self.assertEqual(size, 42)


if __name__ == '__main__':
    unittest.main()
