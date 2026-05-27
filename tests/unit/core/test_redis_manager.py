import importlib
import os
import sys
import types
import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch


class TestRedisManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._module_names = ['routemq.redis_manager', 'redis.asyncio', 'redis']
        self._saved_modules = {name: sys.modules[name] for name in self._module_names if name in sys.modules}
        self._clear_modules()

        self.fake_pool = MagicMock(name='ConnectionPool')
        self.fake_client = MagicMock(name='Redis')
        self.fake_redis_asyncio = cast(Any, types.ModuleType('redis.asyncio'))
        self.fake_redis_asyncio.ConnectionPool = MagicMock(return_value=self.fake_pool)
        self.fake_redis_asyncio.Redis = MagicMock(return_value=self.fake_client)

        self.fake_redis = cast(Any, types.ModuleType('redis'))
        self.fake_redis.asyncio = self.fake_redis_asyncio

        sys.modules['redis'] = self.fake_redis
        sys.modules['redis.asyncio'] = self.fake_redis_asyncio

    def tearDown(self) -> None:
        self._clear_modules()
        for name, module in self._saved_modules.items():
            sys.modules[name] = module

    def _clear_modules(self) -> None:
        for name in self._module_names:
            sys.modules.pop(name, None)

    def _import_manager(self, env: dict[str, str] | None = None, clear: bool = True) -> Any:
        patcher = patch.dict(os.environ, env or {}, clear=clear)
        patcher.start()
        self.addCleanup(patcher.stop)
        return importlib.import_module('routemq.redis_manager')

    async def test_singleton_instance_is_shared_with_module_global(self) -> None:
        module = self._import_manager({'ENABLE_REDIS': 'false'})

        first = module.RedisManager()
        second = module.RedisManager()

        self.assertIs(first, second)
        self.assertIs(first, module.redis_manager)

    async def test_missing_enable_redis_is_disabled_noop_state(self) -> None:
        module = self._import_manager({})
        manager = module.redis_manager

        self.assertFalse(manager.enabled)
        self.assertFalse(manager.is_enabled())
        self.assertIsNone(manager.get_client())
        self.assertFalse(await manager.initialize())
        self.fake_redis_asyncio.ConnectionPool.assert_not_called()
        self.fake_redis_asyncio.Redis.assert_not_called()

    async def test_disabled_helpers_return_contract_sentinels(self) -> None:
        module = self._import_manager({'ENABLE_REDIS': 'false'})
        manager = module.redis_manager

        self.assertIsNone(await manager.get('key'))
        self.assertFalse(await manager.set('key', 'value'))
        self.assertIsNone(await manager.incr('key'))
        self.assertFalse(await manager.expire('key', 10))
        self.assertEqual(await manager.delete('key'), 0)
        self.assertFalse(await manager.exists('key'))
        self.assertEqual(await manager.ttl('key'), -2)
        self.assertIsNone(await manager.hget('hash', 'field'))
        self.assertEqual(await manager.hset('hash', 'field', 'value'), 0)
        self.assertIsNone(await manager.get_json('key'))
        self.assertFalse(await manager.set_json('key', {'a': 1}))

    async def test_enabled_initialize_uses_redis_environment(self) -> None:
        self.fake_client.ping = AsyncMock(return_value=True)
        module = self._import_manager(
            {
                'ENABLE_REDIS': 'true',
                'REDIS_HOST': 'redis-host',
                'REDIS_PORT': '6380',
                'REDIS_DB': '2',
                'REDIS_PASSWORD': 'secret',
                'REDIS_USERNAME': 'user',
                'REDIS_MAX_CONNECTIONS': '23',
                'REDIS_SOCKET_TIMEOUT': '1.5',
                'REDIS_SOCKET_CONNECT_TIMEOUT': '2.5',
            }
        )

        result = await module.redis_manager.initialize()

        self.assertTrue(result)
        self.fake_redis_asyncio.ConnectionPool.assert_called_once_with(
            host='redis-host',
            port=6380,
            db=2,
            password='secret',
            username='user',
            max_connections=23,
            socket_timeout=1.5,
            socket_connect_timeout=2.5,
            decode_responses=True,
            health_check_interval=30,
        )
        self.fake_redis_asyncio.Redis.assert_called_once_with(connection_pool=self.fake_pool)
        self.fake_client.ping.assert_awaited_once_with()
        self.assertIs(module.redis_manager.get_client(), self.fake_client)
        self.assertTrue(module.redis_manager.is_enabled())

    async def test_initialize_failure_disables_manager_and_returns_false(self) -> None:
        self.fake_client.ping = AsyncMock(side_effect=ConnectionError('boom'))
        module = self._import_manager({'ENABLE_REDIS': 'true'})

        result = await module.redis_manager.initialize()

        self.assertFalse(result)
        self.assertFalse(module.redis_manager.enabled)
        self.assertFalse(module.redis_manager.is_enabled())

    async def test_helpers_happy_path_delegate_to_client(self) -> None:
        module = self._import_manager({'ENABLE_REDIS': 'true'})
        manager = module.redis_manager
        manager._redis_client = self.fake_client

        self.fake_client.get = AsyncMock(return_value='value')
        self.fake_client.set = AsyncMock(return_value=True)
        self.fake_client.incrby = AsyncMock(return_value=3)
        self.fake_client.expire = AsyncMock(return_value=1)
        self.fake_client.delete = AsyncMock(return_value=2)
        self.fake_client.exists = AsyncMock(return_value=1)
        self.fake_client.ttl = AsyncMock(return_value=30)
        self.fake_client.hget = AsyncMock(return_value='hash-value')
        self.fake_client.hset = AsyncMock(return_value=1)

        self.assertEqual(await manager.get('key'), 'value')
        self.assertTrue(await manager.set('key', 'value', ex=10, px=20, nx=True, xx=False))
        self.assertEqual(await manager.incr('counter', 2), 3)
        self.assertTrue(await manager.expire('key', 30))
        self.assertEqual(await manager.delete('a', 'b'), 2)
        self.assertTrue(await manager.exists('key'))
        self.assertEqual(await manager.ttl('key'), 30)
        self.assertEqual(await manager.hget('hash', 'field'), 'hash-value')
        self.assertEqual(await manager.hset('hash', 'field', 'value'), 1)
        self.assertEqual(await manager.hset('hash', mapping={'field': 'value'}), 1)
        self.assertEqual(await manager.hset('hash'), 0)

        self.fake_client.set.assert_awaited_once_with('key', 'value', ex=10, px=20, nx=True, xx=False)
        self.fake_client.incrby.assert_awaited_once_with('counter', 2)
        self.fake_client.delete.assert_awaited_once_with('a', 'b')
        self.fake_client.hset.assert_any_await('hash', 'field', 'value')
        self.fake_client.hset.assert_any_await('hash', mapping={'field': 'value'})

    async def test_helper_errors_return_contract_sentinels(self) -> None:
        module = self._import_manager({'ENABLE_REDIS': 'true'})
        manager = module.redis_manager
        manager._redis_client = self.fake_client

        self.fake_client.get = AsyncMock(side_effect=RuntimeError('get'))
        self.fake_client.set = AsyncMock(side_effect=RuntimeError('set'))
        self.fake_client.incrby = AsyncMock(side_effect=RuntimeError('incr'))
        self.fake_client.expire = AsyncMock(side_effect=RuntimeError('expire'))
        self.fake_client.delete = AsyncMock(side_effect=RuntimeError('delete'))
        self.fake_client.exists = AsyncMock(side_effect=RuntimeError('exists'))
        self.fake_client.ttl = AsyncMock(side_effect=RuntimeError('ttl'))
        self.fake_client.hget = AsyncMock(side_effect=RuntimeError('hget'))
        self.fake_client.hset = AsyncMock(side_effect=RuntimeError('hset'))

        self.assertIsNone(await manager.get('key'))
        self.assertFalse(await manager.set('key', 'value'))
        self.assertIsNone(await manager.incr('key'))
        self.assertFalse(await manager.expire('key', 10))
        self.assertEqual(await manager.delete('key'), 0)
        self.assertFalse(await manager.exists('key'))
        self.assertEqual(await manager.ttl('key'), -2)
        self.assertIsNone(await manager.hget('hash', 'field'))
        self.assertEqual(await manager.hset('hash', 'field', 'value'), 0)

    async def test_json_helpers_use_get_set_and_return_sentinels_on_errors(self) -> None:
        module = self._import_manager({'ENABLE_REDIS': 'true'})
        manager = module.redis_manager

        manager.get = AsyncMock(return_value='{"count": 2}')
        manager.set = AsyncMock(return_value=True)
        self.assertEqual(await manager.get_json('json-key'), {'count': 2})
        self.assertTrue(await manager.set_json('json-key', {'count': 2}, ex=5))
        manager.set.assert_awaited_once_with('json-key', '{"count": 2}', ex=5, px=None, nx=False, xx=False)

        manager.get = AsyncMock(return_value='not-json')
        self.assertIsNone(await manager.get_json('json-key'))
        self.assertFalse(await manager.set_json('bad', object()))

    async def test_disconnect_is_idempotent_and_clears_connections(self) -> None:
        module = self._import_manager({'ENABLE_REDIS': 'true'})
        manager = module.redis_manager
        manager._redis_client = self.fake_client
        manager._redis_pool = self.fake_pool
        self.fake_client.aclose = AsyncMock(return_value=None)
        self.fake_pool.aclose = AsyncMock(return_value=None)

        await manager.disconnect()
        await manager.disconnect()

        self.fake_client.aclose.assert_awaited_once_with()
        self.fake_pool.aclose.assert_awaited_once_with()
        self.assertIsNone(manager._redis_client)
        self.assertIsNone(manager._redis_pool)

    async def test_invalid_numeric_environment_raises_value_error(self) -> None:
        invalid_envs = [
            {'ENABLE_REDIS': 'true', 'REDIS_PORT': 'not-an-int'},
            {'ENABLE_REDIS': 'true', 'REDIS_DB': 'not-an-int'},
            {'ENABLE_REDIS': 'true', 'REDIS_MAX_CONNECTIONS': 'not-an-int'},
            {'ENABLE_REDIS': 'true', 'REDIS_SOCKET_TIMEOUT': 'not-a-float'},
            {'ENABLE_REDIS': 'true', 'REDIS_SOCKET_CONNECT_TIMEOUT': 'not-a-float'},
        ]

        for env in invalid_envs:
            with self.subTest(env=env):
                self._clear_modules()
                sys.modules['redis'] = self.fake_redis
                sys.modules['redis.asyncio'] = self.fake_redis_asyncio
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(ValueError):
                        importlib.import_module('routemq.redis_manager')


if __name__ == '__main__':
    unittest.main()
