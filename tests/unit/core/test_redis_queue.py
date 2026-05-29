import json
import logging
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.queue.redis_queue import (
    RedisQueue,
    _created_at_from_redis_job_id,
    _failed_job_queue_from_id,
    _reserved_job_expired,
)


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

    async def test_list_get_retry_forget_and_flush_failed_jobs_in_redis(self) -> None:
        failed = json.dumps(
            {'id': 'failed:q:1', 'connection': 'redis', 'queue': 'q', 'payload': 'p', 'exception': 'boom'}
        )
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[failed])
        client.lrem = AsyncMock(return_value=1)
        client.rpush = AsyncMock()
        client.delete = AsyncMock(return_value=1)
        driver = self._make_driver(client=client)

        with patch('routemq.queue.redis_queue.Model') as mock_model:
            mock_model._is_enabled = False
            self.assertEqual(await driver.list_failed_jobs('q'), [json.loads(failed)])
            self.assertEqual(await driver.get_failed_job('failed:q:1'), json.loads(failed))
            self.assertTrue(await driver.retry_failed_job('failed:q:1'))
            self.assertTrue(await driver.forget_failed_job('failed:q:1'))
            self.assertEqual(await driver.flush_failed_jobs('q'), 1)

        client.rpush.assert_awaited_once()
        self.assertEqual(client.rpush.await_args.args[0], driver._get_queue_key('q'))
        self.assertEqual(json.loads(client.rpush.await_args.args[1])['payload'], 'p')
        client.delete.assert_awaited_once_with('routemq:queue:failed:q')

    async def test_failed_logs_when_both_backends_disabled(self) -> None:
        driver = self._make_driver(enabled=False)
        with patch('routemq.queue.redis_queue.Model') as mock_model:
            mock_model._is_enabled = False
            await driver.failed('redis', 'q', 'p', 'exc')

    async def test_failed_swallows_database_storage_errors(self) -> None:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock(side_effect=RuntimeError('db down'))
        session.close = AsyncMock()
        driver = self._make_driver()

        with (
            patch('routemq.queue.redis_queue.Model') as mock_model,
            patch('routemq.queue.redis_queue.QueueFailedJob'),
        ):
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            await driver.failed('redis', 'q', 'p', 'exc')

        session.close.assert_awaited_once()

    async def test_failed_job_admin_rejects_missing_queue_or_disabled_redis(self) -> None:
        enabled_driver = self._make_driver(enabled=True)
        disabled_driver = self._make_driver(enabled=False)

        self.assertEqual(await enabled_driver.list_failed_jobs(None), [])
        self.assertIsNone(await enabled_driver.get_failed_job('invalid'))
        self.assertFalse(await enabled_driver.retry_failed_job('invalid'))
        self.assertFalse(await enabled_driver.forget_failed_job('invalid'))
        self.assertFalse(await disabled_driver.forget_failed_job('failed:q:1'))
        self.assertEqual(await enabled_driver.flush_failed_jobs(None), 0)
        self.assertEqual(await disabled_driver.flush_failed_jobs('q'), 0)


class RedisQueueVisibilityReaperTests(_RedisQueueBase):
    async def test_reap_expired_reserved_job_requeues_when_attempts_remain(self) -> None:
        reserved_job = json.dumps(
            {
                'id': 'q:1',
                'payload': json.dumps({'max_tries': 3}),
                'attempts': 1,
                'reserved_at': (datetime.now(UTC) - timedelta(seconds=301)).isoformat(),
            }
        )
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[reserved_job])
        client.lrem = AsyncMock()
        client.rpush = AsyncMock()
        driver = self._make_driver(client=client)

        reaped = await driver.reap_expired('q', visibility_timeout=300)

        self.assertEqual(reaped, 1)
        client.lrem.assert_awaited_once_with(driver._get_reserved_key('q'), 1, reserved_job)
        client.rpush.assert_awaited_once()

    async def test_reap_expired_reserved_job_moves_exhausted_to_failed(self) -> None:
        reserved_job = json.dumps(
            {
                'id': 'q:1',
                'payload': json.dumps({'max_tries': 1}),
                'attempts': 1,
                'reserved_at': (datetime.now(UTC) - timedelta(seconds=301)).isoformat(),
            }
        )
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[reserved_job])
        client.lrem = AsyncMock()
        client.rpush = AsyncMock()
        driver = self._make_driver(client=client)

        with patch.object(driver, 'failed', new=AsyncMock()) as failed:
            reaped = await driver.reap_expired('q', visibility_timeout=300)

        self.assertEqual(reaped, 1)
        failed.assert_awaited_once()
        client.rpush.assert_not_called()

    async def test_reap_ignores_unexpired_reserved_jobs(self) -> None:
        reserved_job = json.dumps(
            {
                'id': 'q:1',
                'payload': json.dumps({'max_tries': 3}),
                'attempts': 1,
                'reserved_at': datetime.now(UTC).isoformat(),
            }
        )
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[reserved_job])
        client.lrem = AsyncMock()
        client.rpush = AsyncMock()
        driver = self._make_driver(client=client)

        reaped = await driver.reap_expired('q', visibility_timeout=300)

        self.assertEqual(reaped, 0)
        client.lrem.assert_not_called()
        client.rpush.assert_not_called()

    async def test_reap_returns_zero_when_disabled(self) -> None:
        driver = self._make_driver(enabled=False)

        self.assertEqual(await driver.reap_expired('q', visibility_timeout=300), 0)


class RedisQueueHeartbeatTests(_RedisQueueBase):
    async def test_heartbeat_refreshes_reserved_job_timestamp(self) -> None:
        reserved = json.dumps({'id': 'q:1', 'payload': 'p', 'attempts': 1, 'reserved_at': 'old'})
        client = MagicMock()
        client.lrange = AsyncMock(return_value=[reserved])
        client.lrem = AsyncMock()
        client.rpush = AsyncMock()
        driver = self._make_driver(client=client)

        refreshed = await driver.heartbeat('q:1', 'q')

        self.assertTrue(refreshed)
        client.lrem.assert_awaited_once_with(driver._get_reserved_key('q'), 1, reserved)
        pushed_payload = client.rpush.await_args.args[1]
        self.assertIn('reserved_at', json.loads(pushed_payload))

    async def test_write_worker_heartbeat_uses_hash_with_ttl(self) -> None:
        client = MagicMock()
        client.hset = AsyncMock()
        client.expire = AsyncMock()
        driver = self._make_driver(client=client)
        heartbeat = {'worker_id': 'worker-1', 'queue': 'default', 'state': 'running'}

        await driver.write_worker_heartbeat(heartbeat, ttl=30)

        client.hset.assert_awaited_once()
        client.expire.assert_awaited_once_with('routemq:queue:workers:worker-1', 30)

    async def test_mark_worker_dead_sets_state_dead(self) -> None:
        client = MagicMock()
        client.hset = AsyncMock()
        driver = self._make_driver(client=client)

        await driver.mark_worker_dead('worker-1')

        client.hset.assert_awaited_once_with('routemq:queue:workers:worker-1', mapping={'state': 'dead'})

    async def test_heartbeat_and_worker_updates_are_noops_when_disabled(self) -> None:
        driver = self._make_driver(enabled=False)

        self.assertFalse(await driver.heartbeat('job-1', 'q'))
        self.assertIsNone(await driver.write_worker_heartbeat({'worker_id': 'worker-1'}, ttl=30))
        self.assertIsNone(await driver.mark_worker_dead('worker-1'))


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


class RedisQueueStatsTests(_RedisQueueBase):
    async def test_stats_returns_queue_depths_and_oldest_ready_age(self) -> None:
        old_ready = json.dumps(
            {
                'id': 'q:1',
                'payload': 'p',
                'attempts': 0,
                'created_at': (datetime.now(UTC) - timedelta(seconds=20)).isoformat(),
            }
        )
        client = MagicMock()
        client.llen = AsyncMock(side_effect=[3, 2, 4])
        client.zcard = AsyncMock(return_value=1)
        client.lindex = AsyncMock(return_value=old_ready)
        driver = self._make_driver(client=client)

        stats = await driver.stats('q')

        self.assertEqual(stats['queue'], 'q')
        self.assertEqual(stats['ready'], 3)
        self.assertEqual(stats['reserved'], 2)
        self.assertEqual(stats['delayed'], 1)
        self.assertEqual(stats['failed'], 4)
        self.assertGreaterEqual(stats['oldest_ready_age_seconds'], 19.0)

    async def test_stats_returns_empty_values_when_disabled(self) -> None:
        driver = self._make_driver(enabled=False)

        self.assertEqual(
            await driver.stats('q'),
            {
                'queue': 'q',
                'ready': 0,
                'reserved': 0,
                'delayed': 0,
                'failed': 0,
                'oldest_ready_age_seconds': 0.0,
            },
        )

    async def test_stats_returns_empty_values_on_client_error(self) -> None:
        client = MagicMock()
        client.llen = AsyncMock(side_effect=RuntimeError('redis down'))
        driver = self._make_driver(client=client)

        stats = await driver.stats('q')

        self.assertEqual(stats['ready'], 0)
        self.assertEqual(stats['reserved'], 0)

    async def test_oldest_ready_age_handles_missing_and_invalid_payloads(self) -> None:
        driver = self._make_driver()
        client = MagicMock()

        client.lindex = AsyncMock(return_value=None)
        self.assertEqual(await driver._oldest_ready_age_seconds(client, 'q'), 0.0)

        client.lindex = AsyncMock(return_value='not-json')
        self.assertEqual(await driver._oldest_ready_age_seconds(client, 'q'), 0.0)

        client.lindex = AsyncMock(return_value=json.dumps({'id': 'q:not-number'}))
        self.assertEqual(await driver._oldest_ready_age_seconds(client, 'q'), 0.0)

        client.lindex = AsyncMock(return_value=json.dumps({'created_at': 'not-a-date'}))
        self.assertEqual(await driver._oldest_ready_age_seconds(client, 'q'), 0.0)

        created_at = (datetime.now(UTC) - timedelta(seconds=3)).replace(tzinfo=None).isoformat()
        client.lindex = AsyncMock(return_value=json.dumps({'created_at': created_at}))
        self.assertGreaterEqual(await driver._oldest_ready_age_seconds(client, 'q'), 0.0)


class RedisQueueHelperTests(unittest.TestCase):
    def test_reserved_job_expired_handles_missing_and_invalid_timestamps(self) -> None:
        now = datetime.now(UTC)

        self.assertTrue(_reserved_job_expired({}, now, 300))
        self.assertTrue(_reserved_job_expired({'reserved_at': 'not-a-date'}, now, 300))
        self.assertTrue(
            _reserved_job_expired(
                {'reserved_at': (now - timedelta(seconds=301)).replace(tzinfo=None).isoformat()},
                now,
                300,
            )
        )

    def test_failed_job_id_parser_rejects_invalid_ids(self) -> None:
        self.assertIsNone(_failed_job_queue_from_id('invalid'))
        self.assertIsNone(_failed_job_queue_from_id('failed::1'))

    def test_created_at_parser_handles_invalid_ids(self) -> None:
        self.assertIsNone(_created_at_from_redis_job_id('invalid'))
        self.assertIsNone(_created_at_from_redis_job_id('queue:not-number'))


if __name__ == '__main__':
    unittest.main()
