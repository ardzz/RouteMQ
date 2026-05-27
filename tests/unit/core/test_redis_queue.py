import json
import logging
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.queue.redis_queue import RedisQueue


class _RedisQueueBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.RedisQueue')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def _make_driver(self, enabled: bool = True, client: Any = None) -> RedisQueue:
        driver = RedisQueue()
        driver.redis = MagicMock()
        driver.redis.is_enabled.return_value = enabled
        driver.redis.get_client.return_value = client or MagicMock()
        return driver


class RedisQueuePushTests(_RedisQueueBase):
    async def test_disabled_redis_raises_on_push(self) -> None:
        driver = self._make_driver(enabled=False)
        with self.assertRaises(RuntimeError):
            await driver.push('p', 'default', 0)

    async def test_immediate_push_uses_rpush(self) -> None:
        client = MagicMock()
        client.rpush = AsyncMock()
        client.zadd = AsyncMock()
        driver = self._make_driver(client=client)

        await driver.push('p', 'q', 0)
        client.rpush.assert_awaited_once()
        client.zadd.assert_not_called()

    async def test_delayed_push_uses_zadd(self) -> None:
        client = MagicMock()
        client.rpush = AsyncMock()
        client.zadd = AsyncMock()
        driver = self._make_driver(client=client)

        await driver.push('p', 'q', delay=15)
        client.zadd.assert_awaited_once()
        client.rpush.assert_not_called()

    async def test_push_propagates_client_error(self) -> None:
        client = MagicMock()
        client.rpush = AsyncMock(side_effect=RuntimeError('redis down'))
        driver = self._make_driver(client=client)

        with self.assertRaises(RuntimeError):
            await driver.push('p', 'q', 0)


class RedisQueuePopTests(_RedisQueueBase):
    async def test_disabled_redis_returns_none(self) -> None:
        driver = self._make_driver(enabled=False)
        self.assertIsNone(await driver.pop('q'))

    async def test_empty_queue_returns_none(self) -> None:
        client = MagicMock()
        client.rpoplpush = AsyncMock(return_value=None)
        client.zrangebyscore = AsyncMock(return_value=[])
        driver = self._make_driver(client=client)
        self.assertIsNone(await driver.pop('q'))

    async def test_pop_increments_attempts_and_returns_payload(self) -> None:
        job = {'id': 'q:1', 'payload': 'payload-blob', 'attempts': 2}
        client = MagicMock()
        client.zrangebyscore = AsyncMock(return_value=[])
        client.rpoplpush = AsyncMock(return_value=json.dumps(job))
        client.lrem = AsyncMock()
        client.rpush = AsyncMock()
        driver = self._make_driver(client=client)

        result = await driver.pop('q')
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result['attempts'], 3)
        self.assertEqual(result['id'], 'q:1')

    async def test_pop_swallows_exceptions_and_returns_none(self) -> None:
        client = MagicMock()
        client.zrangebyscore = AsyncMock(side_effect=RuntimeError('boom'))
        client.rpoplpush = AsyncMock(side_effect=RuntimeError('boom'))
        driver = self._make_driver(client=client)
        self.assertIsNone(await driver.pop('q'))


class RedisQueueDelayedMigrationTests(_RedisQueueBase):
    async def test_migrate_skips_when_disabled(self) -> None:
        driver = self._make_driver(enabled=False)
        await driver._migrate_delayed_jobs('q')

    async def test_migrate_moves_available_jobs(self) -> None:
        client = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock()
        pipe.rpush = MagicMock()
        pipe.zrem = MagicMock()
        client.pipeline.return_value = pipe
        client.zrangebyscore = AsyncMock(return_value=['{"id":"q:1"}', '{"id":"q:2"}'])
        driver = self._make_driver(client=client)

        await driver._migrate_delayed_jobs('q')
        self.assertEqual(pipe.rpush.call_count, 2)
        self.assertEqual(pipe.zrem.call_count, 2)
        pipe.execute.assert_awaited_once()

    async def test_migrate_swallows_pipeline_failure(self) -> None:
        client = MagicMock()
        client.zrangebyscore = AsyncMock(side_effect=RuntimeError('boom'))
        driver = self._make_driver(client=client)
        await driver._migrate_delayed_jobs('q')


class RedisQueueReleaseTests(_RedisQueueBase):
    async def test_release_when_disabled_is_noop(self) -> None:
        driver = self._make_driver(enabled=False)
        await driver.release('q:1', 'q')

    async def test_release_without_delay_pushes_back(self) -> None:
        reserved = json.dumps({'id': 'q:1', 'payload': 'p', 'attempts': 1})
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[reserved])
        client.lrem = AsyncMock()
        client.rpush = AsyncMock()
        client.zadd = AsyncMock()
        driver = self._make_driver(client=client)

        await driver.release('q:1', 'q', delay=0)
        client.lrem.assert_awaited_once()
        client.rpush.assert_awaited_once()
        client.zadd.assert_not_called()

    async def test_release_with_delay_uses_zadd(self) -> None:
        reserved = json.dumps({'id': 'q:1', 'payload': 'p', 'attempts': 1})
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[reserved])
        client.lrem = AsyncMock()
        client.rpush = AsyncMock()
        client.zadd = AsyncMock()
        driver = self._make_driver(client=client)

        await driver.release('q:1', 'q', delay=5)
        client.zadd.assert_awaited_once()
        client.rpush.assert_not_called()

    async def test_release_logs_warning_when_job_not_found(self) -> None:
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[])
        driver = self._make_driver(client=client)
        await driver.release('missing', 'q', 0)

    async def test_release_propagates_unexpected_error(self) -> None:
        client = MagicMock()
        client.lrange = AsyncMock(side_effect=RuntimeError('boom'))
        driver = self._make_driver(client=client)
        with self.assertRaises(RuntimeError):
            await driver.release('id', 'q')


class RedisQueueDeleteTests(_RedisQueueBase):
    async def test_delete_when_disabled_is_noop(self) -> None:
        driver = self._make_driver(enabled=False)
        await driver.delete('q:1', 'q')

    async def test_delete_removes_matching_job(self) -> None:
        reserved = json.dumps({'id': 'q:1', 'payload': 'p', 'attempts': 1})
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[reserved])
        client.lrem = AsyncMock()
        driver = self._make_driver(client=client)

        await driver.delete('q:1', 'q')
        client.lrem.assert_awaited_once()

    async def test_delete_warns_when_job_not_found(self) -> None:
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[])
        driver = self._make_driver(client=client)
        await driver.delete('missing', 'q')

    async def test_delete_propagates_unexpected_error(self) -> None:
        client = MagicMock()
        client.lrange = AsyncMock(side_effect=RuntimeError('boom'))
        driver = self._make_driver(client=client)
        with self.assertRaises(RuntimeError):
            await driver.delete('id', 'q')


class RedisQueueFailedTests(_RedisQueueBase):
    async def test_failed_stores_in_database_when_model_enabled(self) -> None:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.close = AsyncMock()
        driver = self._make_driver()

        with (
            patch('routemq.queue.redis_queue.Model') as mock_model,
            patch('routemq.queue.redis_queue.QueueFailedJob') as mock_failed_cls,
        ):
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            mock_failed_cls.return_value = MagicMock()

            await driver.failed('redis', 'q', 'p', 'exc')

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_failed_falls_back_to_redis_when_only_redis_enabled(self) -> None:
        client = MagicMock()
        client.rpush = AsyncMock()
        driver = self._make_driver(client=client)

        with patch('routemq.queue.redis_queue.Model') as mock_model:
            mock_model._is_enabled = False
            await driver.failed('redis', 'q', 'p', 'exc')

        client.rpush.assert_awaited_once()

    async def test_failed_logs_when_both_backends_disabled(self) -> None:
        driver = self._make_driver(enabled=False)
        with patch('routemq.queue.redis_queue.Model') as mock_model:
            mock_model._is_enabled = False
            await driver.failed('redis', 'q', 'p', 'exc')


class RedisQueueSizeTests(_RedisQueueBase):
    async def test_size_returns_zero_when_disabled(self) -> None:
        driver = self._make_driver(enabled=False)
        self.assertEqual(await driver.size('q'), 0)

    async def test_size_sums_main_and_delayed(self) -> None:
        client = MagicMock()
        client.llen = AsyncMock(return_value=3)
        client.zcard = AsyncMock(return_value=2)
        driver = self._make_driver(client=client)
        self.assertEqual(await driver.size('q'), 5)

    async def test_size_returns_zero_on_error(self) -> None:
        client = MagicMock()
        client.llen = AsyncMock(side_effect=RuntimeError('boom'))
        driver = self._make_driver(client=client)
        self.assertEqual(await driver.size('q'), 0)


if __name__ == '__main__':
    unittest.main()
