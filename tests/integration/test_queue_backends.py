import asyncio
import os
import unittest
from importlib import import_module
from typing import Any

from routemq.model import Model
from routemq.queue.database_queue import DatabaseQueue
from routemq.queue.redis_queue import RedisQueue
from routemq.redis_manager import RedisManager
from tests.integration.helpers import DockerIntegrationTestCase


class RedisQueueIntegrationTests(DockerIntegrationTestCase, unittest.IsolatedAsyncioTestCase):
    redis_container: Any

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        redis_container = import_module('testcontainers.redis').RedisContainer
        cls.redis_container = redis_container('redis:7')
        cls.redis_container.start()
        cls.addClassCleanup(cls.redis_container.stop)

    def setUp(self) -> None:
        self._env = dict(os.environ)
        self._redis_instance = RedisManager._instance
        self._redis_pool = RedisManager._redis_pool
        self._redis_client = RedisManager._redis_client

        os.environ['ENABLE_REDIS'] = 'true'
        os.environ['REDIS_HOST'] = self.redis_container.get_container_host_ip()
        os.environ['REDIS_PORT'] = str(self.redis_container.get_exposed_port(6379))
        os.environ['REDIS_DB'] = '0'
        os.environ.pop('REDIS_PASSWORD', None)
        os.environ.pop('REDIS_USERNAME', None)
        RedisManager._instance = None
        RedisManager._redis_pool = None
        RedisManager._redis_client = None

    async def asyncTearDown(self) -> None:
        await RedisManager().disconnect()

    def tearDown(self) -> None:
        RedisManager._instance = self._redis_instance
        RedisManager._redis_pool = self._redis_pool
        RedisManager._redis_client = self._redis_client
        os.environ.clear()
        os.environ.update(self._env)

    async def test_redis_queue_push_pop_delete_round_trip(self) -> None:
        manager = RedisManager()
        self.assertTrue(await manager.initialize())

        queue = RedisQueue()
        await queue.push('{"job": "redis"}', queue='integration')

        self.assertEqual(await queue.size('integration'), 1)
        job = await queue.pop('integration')
        assert job is not None
        self.assertEqual(job['payload'], '{"job": "redis"}')
        self.assertEqual(job['attempts'], 1)

        await queue.delete(job['id'], 'integration')
        self.assertEqual(await queue.size('integration'), 0)


class DatabaseQueueIntegrationTests(DockerIntegrationTestCase, unittest.IsolatedAsyncioTestCase):
    mysql_container: Any

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        mysql_container = import_module('testcontainers.mysql').MySqlContainer
        cls.mysql_container = mysql_container('mysql:8.0', dialect='aiomysql')
        cls.mysql_container.start()
        cls.addClassCleanup(cls.mysql_container.stop)

    def setUp(self) -> None:
        self._env = dict(os.environ)
        self._model_engine = Model._engine
        self._model_session_factory = Model._session_factory
        self._model_enabled = Model._is_enabled

        os.environ['ENABLE_MYSQL'] = 'true'

    async def asyncSetUp(self) -> None:
        Model.configure(self.mysql_container.get_connection_url())
        await Model.create_tables()

    async def asyncTearDown(self) -> None:
        await Model.cleanup()

    def tearDown(self) -> None:
        Model._engine = self._model_engine
        Model._session_factory = self._model_session_factory
        Model._is_enabled = self._model_enabled
        os.environ.clear()
        os.environ.update(self._env)

    async def test_database_queue_push_pop_delete_round_trip(self) -> None:
        queue = DatabaseQueue()
        await queue.push('{"job": "database"}', queue='integration')

        self.assertEqual(await queue.size('integration'), 1)
        await asyncio.sleep(1.1)
        job = await queue.pop('integration')
        assert job is not None
        self.assertEqual(job['payload'], '{"job": "database"}')
        self.assertEqual(job['attempts'], 1)

        await queue.delete(job['id'], 'integration')
        self.assertEqual(await queue.size('integration'), 0)


if __name__ == '__main__':
    unittest.main()
