import json
import os
import unittest
from datetime import datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.job import Job
from routemq.model import Model
from routemq.queue.database_queue import DatabaseQueue
from routemq.queue.models import QueueFailedJob, QueueJob
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager, dispatch, queue
from routemq.queue.queue_worker import QueueWorker
from routemq.queue.redis_queue import RedisQueue


class QueueTestJob(Job):
    queue = 'jobs'
    max_tries = 3
    retry_after = 7

    def __init__(self, value: str = 'payload') -> None:
        super().__init__()
        self.value = value
        self.handled = False
        self.failed_exception = ''

    async def handle(self) -> None:
        self.handled = True

    async def failed(self, exception: Exception) -> None:
        self.failed_exception = str(exception)


class FailingQueueTestJob(QueueTestJob):
    max_tries = 2
    retry_after = 11

    async def handle(self) -> None:
        raise RuntimeError('boom')


Job.register(QueueTestJob)
Job.register(FailingQueueTestJob)


class QueueTestCase(unittest.IsolatedAsyncioTestCase):
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


class TestQueueManager(QueueTestCase):
    def test_get_driver_selects_redis_when_enabled(self) -> None:
        manager = QueueManager()
        redis_manager = MagicMock()
        redis_manager.is_enabled.return_value = True

        with patch('routemq.queue.queue_manager.RedisManager', return_value=redis_manager):
            driver = manager.get_driver('redis')

        self.assertIsInstance(driver, RedisQueue)

    def test_get_driver_falls_back_to_database_when_redis_disabled(self) -> None:
        manager = QueueManager()
        redis_manager = MagicMock()
        redis_manager.is_enabled.return_value = False

        with patch('routemq.queue.queue_manager.RedisManager', return_value=redis_manager):
            with patch.object(Model, '_is_enabled', True):
                driver = manager.get_driver('redis')

        self.assertIsInstance(driver, DatabaseQueue)

    def test_get_driver_selects_database_when_configured(self) -> None:
        manager = QueueManager()

        with patch.object(Model, '_is_enabled', True):
            driver = manager.get_driver('database')

        self.assertIsInstance(driver, DatabaseQueue)

    def test_get_driver_raises_when_database_disabled(self) -> None:
        manager = QueueManager()

        with patch.object(Model, '_is_enabled', False):
            with self.assertRaisesRegex(RuntimeError, 'MySQL is disabled'):
                manager.get_driver('database')

    async def test_push_serializes_job_to_expected_backend(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.push = AsyncMock()

        with patch.object(manager, 'get_driver', return_value=driver) as get_driver:
            await manager.push(QueueTestJob('alpha'), connection='redis')

        get_driver.assert_called_once_with('redis')
        driver.push.assert_awaited_once()
        payload, queue_name = driver.push.await_args.args
        self.assertEqual(queue_name, 'jobs')
        self.assertEqual(json.loads(payload)['data']['value'], 'alpha')

    async def test_push_uses_custom_queue_name(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.push = AsyncMock()

        with patch.object(manager, 'get_driver', return_value=driver):
            await manager.push(QueueTestJob(), queue='custom')

        driver.push.assert_awaited_once()
        self.assertEqual(driver.push.await_args.args[1], 'custom')

    async def test_later_passes_delay_to_driver(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.push = AsyncMock()

        with patch.object(manager, 'get_driver', return_value=driver):
            await manager.later(15, QueueTestJob(), queue='scheduled')

        driver.push.assert_awaited_once()
        _, queue_name, delay = driver.push.await_args.args
        self.assertEqual(queue_name, 'scheduled')
        self.assertEqual(delay, 15)

    async def test_bulk_dispatches_each_job(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.push = AsyncMock()

        with patch.object(manager, 'get_driver', return_value=driver):
            await manager.bulk([QueueTestJob('one'), QueueTestJob('two')], queue='bulk')

        self.assertEqual(driver.push.await_count, 2)
        self.assertEqual([call.args[1] for call in driver.push.await_args_list], ['bulk', 'bulk'])

    async def test_dispatch_helper_uses_global_queue(self) -> None:
        with patch.object(queue, 'push', new=AsyncMock()) as push:
            await dispatch(QueueTestJob())

        push.assert_awaited_once()

    async def test_repeated_manager_configuration_is_idempotent(self) -> None:
        os.environ['QUEUE_CONNECTION'] = 'database'
        first = QueueManager()
        second = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.push = AsyncMock()

        with patch.object(second, 'get_driver', return_value=driver):
            await second.push(QueueTestJob())

        self.assertIs(first, second)
        self.assertEqual(second._default_connection, 'database')
        driver.push.assert_awaited_once()


class TestQueueWorker(QueueTestCase):
    def make_worker(self) -> tuple[QueueWorker, MagicMock]:
        worker = QueueWorker(queue_name='work', sleep=0)
        driver = MagicMock(spec=QueueDriver)
        driver.delete = AsyncMock()
        driver.release = AsyncMock()
        driver.failed = AsyncMock()
        worker.driver = cast(QueueDriver, driver)
        return worker, driver

    async def test_process_job_handles_and_deletes_successful_job(self) -> None:
        worker, driver = self.make_worker()
        job = QueueTestJob('ok')

        await worker._process_job({'id': 'job-1', 'payload': job.serialize(), 'attempts': 1})

        driver.delete.assert_awaited_once_with('job-1', 'work')
        driver.release.assert_not_awaited()
        driver.failed.assert_not_awaited()

    async def test_retryable_failure_releases_job_with_retry_after_delay(self) -> None:
        worker, driver = self.make_worker()
        job = FailingQueueTestJob()

        await worker._process_job({'id': 'job-2', 'payload': job.serialize(), 'attempts': 1})

        driver.release.assert_awaited_once_with('job-2', 'work', 11)
        driver.delete.assert_not_awaited()
        driver.failed.assert_not_awaited()

    async def test_max_tries_failure_moves_job_to_failed_queue(self) -> None:
        worker, driver = self.make_worker()
        job = FailingQueueTestJob()

        await worker._process_job({'id': 'job-3', 'payload': job.serialize(), 'attempts': 2})

        driver.failed.assert_awaited_once()
        failed_kwargs = driver.failed.await_args.kwargs
        self.assertEqual(failed_kwargs['connection'], 'default')
        self.assertEqual(failed_kwargs['queue'], 'work')
        self.assertIn('RuntimeError: boom', failed_kwargs['exception'])
        driver.delete.assert_awaited_once_with('job-3', 'work')

    async def test_attempts_above_max_tries_are_dead_lettered_before_handle(self) -> None:
        worker, driver = self.make_worker()
        job = QueueTestJob()

        await worker._process_job({'id': 'job-4', 'payload': job.serialize(), 'attempts': 4})

        driver.failed.assert_awaited_once()
        self.assertIn('Max tries exceeded', driver.failed.await_args.kwargs['exception'])
        driver.delete.assert_awaited_once_with('job-4', 'work')

    async def test_handle_exception_is_logged_and_not_propagated(self) -> None:
        worker, driver = self.make_worker()
        job = FailingQueueTestJob()

        with self.assertLogs('RouteMQ.QueueWorker', level='ERROR') as logs:
            await worker._process_job({'id': 'job-5', 'payload': job.serialize(), 'attempts': 1})

        self.assertTrue(any('Job job-5 failed: boom' in message for message in logs.output))
        driver.release.assert_awaited_once_with('job-5', 'work', 11)

    async def test_work_pop_loop_processes_one_job_and_marks_complete(self) -> None:
        worker = QueueWorker(queue_name='work', max_jobs=1, sleep=0)
        driver = MagicMock(spec=QueueDriver)
        driver.pop = AsyncMock(return_value={'id': 'job-6', 'payload': QueueTestJob().serialize(), 'attempts': 1})
        driver.delete = AsyncMock()
        driver.release = AsyncMock()
        driver.failed = AsyncMock()

        with patch.object(worker.queue_manager, 'get_driver', return_value=driver):
            await worker.work()

        driver.pop.assert_awaited_once_with('work')
        driver.delete.assert_awaited_once_with('job-6', 'work')
        self.assertEqual(worker.jobs_processed, 1)


class TestRedisQueue(QueueTestCase):
    def make_queue(self, enabled: bool = True) -> tuple[RedisQueue, MagicMock]:
        redis_queue = RedisQueue()
        client = MagicMock()
        client.rpush = AsyncMock()
        client.zadd = AsyncMock()
        client.zrangebyscore = AsyncMock(return_value=[])
        client.rpoplpush = AsyncMock(return_value=None)
        client.lrem = AsyncMock()
        client.lrange = AsyncMock(return_value=[])
        client.llen = AsyncMock(return_value=0)
        client.zcard = AsyncMock(return_value=0)
        redis_manager = MagicMock()
        redis_manager.is_enabled.return_value = enabled
        redis_manager.get_client.return_value = client
        redis_queue.redis = redis_manager
        return redis_queue, client

    async def test_push_immediate_job_uses_redis_list(self) -> None:
        redis_queue, client = self.make_queue()

        await redis_queue.push('payload', 'fast')

        client.rpush.assert_awaited_once()
        key, job_json = client.rpush.await_args.args
        self.assertEqual(key, 'routemq:queue:fast')
        self.assertEqual(json.loads(job_json)['payload'], 'payload')

    async def test_push_delayed_job_uses_sorted_set(self) -> None:
        redis_queue, client = self.make_queue()

        await redis_queue.push('payload', 'slow', delay=9)

        client.zadd.assert_awaited_once()
        self.assertEqual(client.zadd.await_args.args[0], 'routemq:queue:slow:delayed')

    async def test_pop_migrates_and_reserves_job(self) -> None:
        redis_queue, client = self.make_queue()
        job_json = json.dumps({'id': 'redis-job', 'payload': 'payload', 'attempts': 0})
        client.rpoplpush.return_value = job_json

        job_data = await redis_queue.pop('fast')

        self.assertEqual(job_data, {'id': 'redis-job', 'payload': 'payload', 'attempts': 1})
        client.lrem.assert_awaited_once_with('routemq:queue:fast:reserved', 1, job_json)
        self.assertEqual(json.loads(client.rpush.await_args.args[1])['attempts'], 1)

    async def test_release_moves_reserved_job_back_with_delay(self) -> None:
        redis_queue, client = self.make_queue()
        job_json = json.dumps({'id': 'redis-job', 'payload': 'payload', 'attempts': 1})
        client.lrange.return_value = [job_json]

        await redis_queue.release('redis-job', 'fast', delay=3)

        client.lrem.assert_awaited_once_with('routemq:queue:fast:reserved', 1, job_json)
        client.zadd.assert_awaited_once()

    async def test_delete_removes_reserved_job(self) -> None:
        redis_queue, client = self.make_queue()
        job_json = json.dumps({'id': 'redis-job', 'payload': 'payload', 'attempts': 1})
        client.lrange.return_value = [job_json]

        await redis_queue.delete('redis-job', 'fast')

        client.lrem.assert_awaited_once_with('routemq:queue:fast:reserved', 1, job_json)

    async def test_failed_stores_failed_job_in_redis_when_database_disabled(self) -> None:
        redis_queue, client = self.make_queue()

        with patch.object(Model, '_is_enabled', False):
            await redis_queue.failed('redis', 'fast', 'payload', 'exception')

        client.rpush.assert_awaited_once()
        key, failed_json = client.rpush.await_args.args
        self.assertEqual(key, 'routemq:queue:failed:fast')
        failed_data = json.loads(failed_json)
        self.assertEqual(failed_data['payload'], 'payload')
        self.assertEqual(failed_data['exception'], 'exception')

    async def test_size_counts_ready_and_delayed_jobs(self) -> None:
        redis_queue, client = self.make_queue()
        client.llen.return_value = 2
        client.zcard.return_value = 3

        size = await redis_queue.size('fast')

        self.assertEqual(size, 5)


class TestDatabaseQueue(QueueTestCase):
    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.execute = AsyncMock()
        session.refresh = AsyncMock()
        return session

    async def test_push_adds_queue_job_and_commits(self) -> None:
        database_queue = DatabaseQueue()
        session = self.make_session()

        with patch.object(Model, '_is_enabled', True):
            with patch.object(Model, 'get_session', new=AsyncMock(return_value=session)):
                await database_queue.push('payload', 'db', delay=5)

        session.add.assert_called_once()
        added_job = session.add.call_args.args[0]
        self.assertIsInstance(added_job, QueueJob)
        self.assertEqual(added_job.queue, 'db')
        self.assertEqual(added_job.payload, 'payload')
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_pop_reserves_and_returns_database_job(self) -> None:
        database_queue = DatabaseQueue()
        session = self.make_session()
        job = QueueJob(queue='db', payload='payload', attempts=0, available_at=datetime.utcnow())
        job.id = 42
        result = MagicMock()
        result.scalars.return_value.first.return_value = job
        session.execute.return_value = result

        with patch.object(Model, '_is_enabled', True):
            with patch.object(Model, 'get_session', new=AsyncMock(return_value=session)):
                job_data = await database_queue.pop('db')

        self.assertEqual(job_data, {'id': 42, 'payload': 'payload', 'attempts': 1})
        self.assertIsNotNone(job.reserved_at)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    async def test_release_executes_update_and_commits(self) -> None:
        database_queue = DatabaseQueue()
        session = self.make_session()

        with patch.object(Model, '_is_enabled', True):
            with patch.object(Model, 'get_session', new=AsyncMock(return_value=session)):
                await database_queue.release(42, 'db', delay=1)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_delete_executes_delete_and_commits(self) -> None:
        database_queue = DatabaseQueue()
        session = self.make_session()

        with patch.object(Model, '_is_enabled', True):
            with patch.object(Model, 'get_session', new=AsyncMock(return_value=session)):
                await database_queue.delete(42, 'db')

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_failed_adds_failed_job_and_commits(self) -> None:
        database_queue = DatabaseQueue()
        session = self.make_session()

        with patch.object(Model, '_is_enabled', True):
            with patch.object(Model, 'get_session', new=AsyncMock(return_value=session)):
                await database_queue.failed('database', 'db', 'payload', 'exception')

        session.add.assert_called_once()
        failed_job = session.add.call_args.args[0]
        self.assertIsInstance(failed_job, QueueFailedJob)
        self.assertEqual(failed_job.connection, 'database')
        self.assertEqual(failed_job.queue, 'db')
        self.assertEqual(failed_job.payload, 'payload')
        self.assertEqual(failed_job.exception, 'exception')
        session.commit.assert_awaited_once()

    async def test_size_counts_unreserved_jobs_from_mocked_result(self) -> None:
        database_queue = DatabaseQueue()
        session = self.make_session()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [object(), object()]
        session.execute.return_value = result

        with patch.object(Model, '_is_enabled', True):
            with patch.object(Model, 'get_session', new=AsyncMock(return_value=session)):
                size = await database_queue.size('db')

        self.assertEqual(size, 2)
        session.execute.assert_awaited_once()


class TestQueueModels(unittest.TestCase):
    def test_queue_job_fields_are_present(self) -> None:
        expected_fields = {'id', 'queue', 'payload', 'attempts', 'reserved_at', 'available_at', 'created_at'}

        self.assertTrue(expected_fields.issubset(QueueJob.__table__.columns.keys()))

    def test_queue_failed_job_fields_are_present(self) -> None:
        expected_fields = {'id', 'connection', 'queue', 'payload', 'exception', 'failed_at'}

        self.assertTrue(expected_fields.issubset(QueueFailedJob.__table__.columns.keys()))

    def test_queue_models_can_be_constructed_without_session(self) -> None:
        available_at = datetime.utcnow()
        queue_job = QueueJob(queue='default', payload='payload', attempts=0, available_at=available_at)
        failed_job = QueueFailedJob(
            connection='redis',
            queue='default',
            payload='payload',
            exception='RuntimeError: boom',
            failed_at=available_at,
        )

        self.assertEqual(queue_job.queue, 'default')
        self.assertEqual(queue_job.payload, 'payload')
        self.assertEqual(failed_job.connection, 'redis')
        self.assertEqual(failed_job.exception, 'RuntimeError: boom')


if __name__ == '__main__':
    unittest.main()
