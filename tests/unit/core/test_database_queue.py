import logging
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.queue.database_queue import DatabaseQueue


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


class DatabaseQueueBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.DatabaseQueue')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)


class DatabaseQueuePushTests(DatabaseQueueBase):
    async def test_disabled_mysql_raises(self) -> None:
        driver = DatabaseQueue()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            with self.assertRaises(RuntimeError):
                await driver.push('p', 'q', 0)

    async def test_push_inserts_and_commits(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        with (
            patch('routemq.queue.database_queue.Model') as mock_model,
            patch('routemq.queue.database_queue.QueueJob') as mock_job_cls,
        ):
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            mock_job_cls.return_value = MagicMock()

            await driver.push('p', 'q', 0)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_push_rolls_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.commit.side_effect = RuntimeError('db fail')
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)

            with self.assertRaises(RuntimeError):
                await driver.push('p', 'q', 0)

        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()


class DatabaseQueuePopTests(DatabaseQueueBase):
    async def test_disabled_returns_none(self) -> None:
        driver = DatabaseQueue()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            self.assertIsNone(await driver.pop('q'))

    async def test_no_jobs_returns_none(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        scalars = MagicMock()
        scalars.first.return_value = None
        result = MagicMock()
        result.scalars.return_value = scalars
        session.execute.return_value = result

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            self.assertIsNone(await driver.pop('q'))

    async def test_pop_returns_job_payload(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()

        job = MagicMock()
        job.id = 42
        job.payload = 'serialized'
        job.attempts = 0
        scalars = MagicMock()
        scalars.first.return_value = job
        result = MagicMock()
        result.scalars.return_value = scalars
        session.execute.return_value = result

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            popped = await driver.pop('q')

        self.assertIsNotNone(popped)
        assert popped is not None
        self.assertEqual(popped['id'], 42)
        self.assertEqual(popped['attempts'], 1)

    async def test_pop_returns_none_on_db_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db error')

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            self.assertIsNone(await driver.pop('q'))

        session.rollback.assert_awaited_once()


class DatabaseQueueReleaseTests(DatabaseQueueBase):
    async def test_release_when_disabled_is_noop(self) -> None:
        driver = DatabaseQueue()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            await driver.release(1, 'q', 0)

    async def test_release_updates_record(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            await driver.release(1, 'q', 5)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_release_rolls_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.commit.side_effect = RuntimeError('db fail')
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            with self.assertRaises(RuntimeError):
                await driver.release(1, 'q', 0)
        session.rollback.assert_awaited_once()


class DatabaseQueueDeleteTests(DatabaseQueueBase):
    async def test_delete_when_disabled_is_noop(self) -> None:
        driver = DatabaseQueue()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            await driver.delete(1, 'q')

    async def test_delete_executes_and_commits(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            await driver.delete(1, 'q')
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_delete_rolls_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db fail')
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            with self.assertRaises(RuntimeError):
                await driver.delete(1, 'q')
        session.rollback.assert_awaited_once()


class DatabaseQueueFailedTests(DatabaseQueueBase):
    async def test_failed_when_disabled_is_noop(self) -> None:
        driver = DatabaseQueue()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            await driver.failed('c', 'q', 'p', 'e')

    async def test_failed_stores_record(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        with (
            patch('routemq.queue.database_queue.Model') as mock_model,
            patch('routemq.queue.database_queue.QueueFailedJob') as mock_failed_cls,
        ):
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            mock_failed_cls.return_value = MagicMock()
            await driver.failed('c', 'q', 'p', 'e')
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_failed_rolls_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.commit.side_effect = RuntimeError('db fail')
        with (
            patch('routemq.queue.database_queue.Model') as mock_model,
            patch('routemq.queue.database_queue.QueueFailedJob'),
        ):
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            with self.assertRaises(RuntimeError):
                await driver.failed('c', 'q', 'p', 'e')
        session.rollback.assert_awaited_once()

    async def test_list_get_retry_forget_and_flush_failed_jobs_in_database(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        failed_job = MagicMock()
        failed_job.id = 5
        failed_job.connection = 'database'
        failed_job.queue = 'q'
        failed_job.payload = 'payload'
        failed_job.exception = 'boom'
        failed_job.failed_at.isoformat.return_value = '2026-05-29T00:00:00+00:00'
        scalars = MagicMock()
        scalars.all.return_value = [failed_job]
        scalars.first.return_value = failed_job
        result = MagicMock()
        result.scalars.return_value = scalars
        session.execute.return_value = result
        session.delete = AsyncMock()

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            self.assertEqual((await driver.list_failed_jobs('q'))[0]['id'], 5)
            failed_job = await driver.get_failed_job(5)
            self.assertIsNotNone(failed_job)
            assert failed_job is not None
            self.assertEqual(failed_job['payload'], 'payload')
            self.assertTrue(await driver.retry_failed_job(5))
            self.assertTrue(await driver.forget_failed_job(5))
            self.assertEqual(await driver.flush_failed_jobs('q'), 1)

        session.add.assert_called_once()
        session.delete.assert_awaited()

    async def test_failed_admin_methods_return_empty_when_mysql_disabled(self) -> None:
        driver = DatabaseQueue()

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            self.assertEqual(await driver.list_failed_jobs('q'), [])
            self.assertIsNone(await driver.get_failed_job(1))
            self.assertFalse(await driver.forget_failed_job(1))
            self.assertEqual(await driver.flush_failed_jobs('q'), 0)
            self.assertIsNone(await driver._get_failed_job_model(1))

    async def test_forget_failed_job_returns_false_when_missing(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        scalars = MagicMock()
        scalars.first.return_value = None
        result = MagicMock()
        result.scalars.return_value = scalars
        session.execute.return_value = result

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            self.assertFalse(await driver.forget_failed_job(999))

        session.delete.assert_not_called()

    async def test_forget_and_flush_failed_jobs_roll_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db down')

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            with self.assertRaises(RuntimeError):
                await driver.forget_failed_job(5)
            with self.assertRaises(RuntimeError):
                await driver.flush_failed_jobs('q')

        self.assertEqual(session.rollback.await_count, 2)


class DatabaseQueueHeartbeatTests(DatabaseQueueBase):
    async def test_heartbeat_returns_false_when_mysql_disabled(self) -> None:
        driver = DatabaseQueue()

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            self.assertFalse(await driver.heartbeat(1, 'q'))

    async def test_heartbeat_updates_reserved_job(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        result = MagicMock()
        result.rowcount = 1
        session.execute.return_value = result

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            self.assertTrue(await driver.heartbeat(1, 'q'))

        session.commit.assert_awaited_once()

    async def test_heartbeat_rolls_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db down')

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            with self.assertRaises(RuntimeError):
                await driver.heartbeat(1, 'q')

        session.rollback.assert_awaited_once()


class DatabaseQueueVisibilityReaperTests(DatabaseQueueBase):
    async def test_reap_expired_reserved_job_clears_reserved_at_when_attempts_remain(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        job = MagicMock()
        job.id = 7
        job.payload = '{"max_tries": 3}'
        job.attempts = 1
        job.reserved_at = datetime.now(UTC) - timedelta(seconds=301)
        scalars = MagicMock()
        scalars.all.return_value = [job]
        result = MagicMock()
        result.scalars.return_value = scalars
        session.execute.return_value = result

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            reaped = await driver.reap_expired('q', visibility_timeout=300)

        self.assertEqual(reaped, 1)
        self.assertIsNone(job.reserved_at)
        self.assertIsInstance(job.available_at, datetime)
        session.add.assert_not_called()
        session.commit.assert_awaited_once()

    async def test_reap_expired_returns_zero_when_mysql_disabled(self) -> None:
        driver = DatabaseQueue()

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            self.assertEqual(await driver.reap_expired('q', 300), 0)

    async def test_reap_expired_rolls_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db down')

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            with self.assertRaises(RuntimeError):
                await driver.reap_expired('q', 300)

        session.rollback.assert_awaited_once()

    async def test_reap_expired_reserved_job_moves_exhausted_to_failed(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.delete = AsyncMock()
        job = MagicMock()
        job.id = 7
        job.payload = '{"max_tries": 1}'
        job.attempts = 1
        job.reserved_at = datetime.now(UTC) - timedelta(seconds=301)
        scalars = MagicMock()
        scalars.all.return_value = [job]
        result = MagicMock()
        result.scalars.return_value = scalars
        session.execute.return_value = result

        with (
            patch('routemq.queue.database_queue.Model') as mock_model,
            patch('routemq.queue.database_queue.QueueFailedJob') as failed_cls,
        ):
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            reaped = await driver.reap_expired('q', visibility_timeout=300)

        self.assertEqual(reaped, 1)
        failed_cls.assert_called_once()
        session.add.assert_called_once()
        session.delete.assert_awaited_once_with(job)
        session.commit.assert_awaited_once()

    async def test_reap_rolls_back_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db fail')

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            with self.assertRaises(RuntimeError):
                await driver.reap_expired('q', visibility_timeout=300)

        session.rollback.assert_awaited_once()


class DatabaseQueueSizeTests(DatabaseQueueBase):
    async def test_size_when_disabled_returns_zero(self) -> None:
        driver = DatabaseQueue()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
            self.assertEqual(await driver.size('q'), 0)

    async def test_size_returns_count(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        scalars = MagicMock()
        scalars.all.return_value = ['a', 'b', 'c']
        result = MagicMock()
        result.scalars.return_value = scalars
        session.execute.return_value = result

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            self.assertEqual(await driver.size('q'), 3)

    async def test_size_returns_zero_on_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db fail')

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            self.assertEqual(await driver.size('q'), 0)


class DatabaseQueueStatsTests(DatabaseQueueBase):
    async def test_stats_returns_depths_and_oldest_ready_age(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        now = datetime.now(UTC)
        ready = MagicMock()
        ready.reserved_at = None
        ready.available_at = now - timedelta(seconds=5)
        ready.created_at = now - timedelta(seconds=30)
        delayed = MagicMock()
        delayed.reserved_at = None
        delayed.available_at = now + timedelta(seconds=30)
        delayed.created_at = now
        reserved = MagicMock()
        reserved.reserved_at = now
        reserved.available_at = now - timedelta(seconds=10)
        reserved.created_at = now - timedelta(seconds=20)
        jobs_scalars = MagicMock()
        jobs_scalars.all.return_value = [ready, delayed, reserved]
        jobs_result = MagicMock()
        jobs_result.scalars.return_value = jobs_scalars
        failed_scalars = MagicMock()
        failed_scalars.all.return_value = [MagicMock(), MagicMock()]
        failed_result = MagicMock()
        failed_result.scalars.return_value = failed_scalars
        session.execute.side_effect = [jobs_result, failed_result]

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            stats = await driver.stats('q')

        self.assertEqual(stats['queue'], 'q')
        self.assertEqual(stats['ready'], 1)
        self.assertEqual(stats['reserved'], 1)
        self.assertEqual(stats['delayed'], 1)
        self.assertEqual(stats['failed'], 2)
        self.assertGreaterEqual(stats['oldest_ready_age_seconds'], 29.0)

    async def test_stats_returns_empty_values_when_disabled(self) -> None:
        driver = DatabaseQueue()
        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = False
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

    async def test_stats_counts_ready_delayed_reserved_and_failed_jobs(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        now = datetime.now(UTC)
        ready = MagicMock(
            reserved_at=None, available_at=now - timedelta(seconds=1), created_at=now - timedelta(seconds=12)
        )
        delayed = MagicMock(reserved_at=None, available_at=now + timedelta(seconds=30), created_at=now)
        reserved = MagicMock(reserved_at=now, available_at=now, created_at=now)
        jobs_scalars = MagicMock()
        jobs_scalars.all.return_value = [ready, delayed, reserved]
        failed_scalars = MagicMock()
        failed_scalars.all.return_value = [MagicMock(), MagicMock()]
        jobs_result = MagicMock()
        jobs_result.scalars.return_value = jobs_scalars
        failed_result = MagicMock()
        failed_result.scalars.return_value = failed_scalars
        session.execute.side_effect = [jobs_result, failed_result]

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            stats = await driver.stats('q')

        self.assertEqual(stats['ready'], 1)
        self.assertEqual(stats['delayed'], 1)
        self.assertEqual(stats['reserved'], 1)
        self.assertEqual(stats['failed'], 2)
        self.assertGreaterEqual(stats['oldest_ready_age_seconds'], 0.0)

    async def test_stats_returns_empty_values_on_query_error(self) -> None:
        driver = DatabaseQueue()
        session = _mock_session()
        session.execute.side_effect = RuntimeError('db down')

        with patch('routemq.queue.database_queue.Model') as mock_model:
            mock_model._is_enabled = True
            mock_model.get_session = AsyncMock(return_value=session)
            stats = await driver.stats('q')

        self.assertEqual(stats['ready'], 0)
        self.assertEqual(stats['failed'], 0)


if __name__ == '__main__':
    unittest.main()
