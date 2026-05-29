import logging
import os
import unittest
import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.queue.queue_worker import QueueWorker


class _DummyJob:
    max_tries = 3
    retry_after = 10
    timeout: int = 30
    attempts = 1
    job_id: Any = None

    def __init__(self, raises: Exception | None = None, timeout: int | None = None) -> None:
        self._raises = raises
        self.timeout = timeout if timeout is not None else _DummyJob.timeout
        self.failed_called = False

    async def handle(self) -> None:
        if self._raises:
            raise self._raises

    async def failed(self, exc: Exception) -> None:
        self.failed_called = True

    def serialize(self) -> str:
        return 'serialized-job'

    def get_retry_delay(self, attempts: int, **kwargs: Any) -> float:
        return self.retry_after


class _WorkerSignalGuard(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.QueueWorker')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def _make_worker(self, **kwargs: Any) -> QueueWorker:
        with patch('signal.signal'):
            return QueueWorker(**kwargs)


class QueueWorkerControlsTests(_WorkerSignalGuard):
    def test_worker_reads_retry_backoff_settings(self) -> None:
        with patch.dict(
            os.environ,
            {
                'QUEUE_RETRY_BACKOFF_ENABLED': 'true',
                'QUEUE_RETRY_MAX_DELAY': '12.5',
                'QUEUE_RETRY_JITTER': '0.75',
            },
            clear=True,
        ):
            worker = self._make_worker()

        self.assertTrue(worker.retry_backoff_enabled)
        self.assertEqual(worker.retry_backoff_max_delay, 12.5)
        self.assertEqual(worker.retry_backoff_jitter, 0.75)

    def test_worker_retry_backoff_settings_fall_back_on_invalid_numbers(self) -> None:
        with patch.dict(
            os.environ,
            {
                'QUEUE_RETRY_BACKOFF_ENABLED': 'false',
                'QUEUE_RETRY_MAX_DELAY': 'invalid',
                'QUEUE_RETRY_JITTER': 'invalid',
            },
            clear=True,
        ):
            worker = self._make_worker()

        self.assertFalse(worker.retry_backoff_enabled)
        self.assertEqual(worker.retry_backoff_max_delay, 60.0)
        self.assertEqual(worker.retry_backoff_jitter, 0.0)

    def test_worker_reads_reliability_settings(self) -> None:
        with patch.dict(
            os.environ,
            {
                'QUEUE_VISIBILITY_TIMEOUT': '120',
                'QUEUE_REAPER_INTERVAL': '15',
                'QUEUE_SHUTDOWN_GRACE': '45',
                'QUEUE_HEARTBEAT_INTERVAL': '5',
            },
            clear=True,
        ):
            worker = self._make_worker()

        self.assertEqual(worker.visibility_timeout, 120)
        self.assertEqual(worker.reaper_interval, 15)
        self.assertEqual(worker.shutdown_grace, 45)
        self.assertEqual(worker.heartbeat_interval, 5)

    def test_pause_sets_flag(self) -> None:
        worker = self._make_worker()
        worker.pause()
        self.assertTrue(worker.paused)

    def test_resume_clears_flag(self) -> None:
        worker = self._make_worker()
        worker.paused = True
        worker.resume()
        self.assertFalse(worker.paused)

    def test_stop_sets_should_quit(self) -> None:
        worker = self._make_worker()
        worker.stop()
        self.assertTrue(worker.should_quit)

    def test_handle_signal_sets_should_quit(self) -> None:
        worker = self._make_worker()
        with patch('routemq.queue.queue_worker.mark_worker_dead') as mark_dead:
            worker._handle_signal(15, None)

        self.assertTrue(worker.should_quit)
        self.assertEqual(worker.state, 'stopping')
        self.assertTrue(worker._shutdown_event.is_set())
        mark_dead.assert_called_once_with(os.getpid())

    def test_handle_signal_tolerates_prometheus_cleanup_failure(self) -> None:
        worker = self._make_worker()

        with patch('routemq.queue.queue_worker.mark_worker_dead', side_effect=RuntimeError('metrics down')):
            worker._handle_signal(15, None)

        self.assertTrue(worker.should_quit)


class QueueWorkerShouldStopTests(_WorkerSignalGuard):
    def test_no_limits_does_not_stop(self) -> None:
        worker = self._make_worker()
        self.assertFalse(worker._should_stop())

    def test_max_jobs_reached_stops(self) -> None:
        worker = self._make_worker(max_jobs=3)
        worker.jobs_processed = 3
        self.assertTrue(worker._should_stop())

    def test_max_jobs_under_does_not_stop(self) -> None:
        worker = self._make_worker(max_jobs=10)
        worker.jobs_processed = 2
        self.assertFalse(worker._should_stop())

    def test_max_time_exceeded_stops(self) -> None:
        worker = self._make_worker(max_time=5)
        worker.start_time = 1000.0
        with patch(
            'routemq.queue.queue_worker.asyncio.get_event_loop',
            return_value=MagicMock(time=MagicMock(return_value=1100.0)),
        ):
            self.assertTrue(worker._should_stop())


class QueueWorkerProcessJobTests(_WorkerSignalGuard):
    async def test_max_tries_exceeded_moves_to_failed(self) -> None:
        worker = self._make_worker(max_tries=2)
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.failed = AsyncMock()
        worker._fail_job = AsyncMock()

        job = _DummyJob()
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 5})

        worker._fail_job.assert_awaited_once()
        worker.driver.delete.assert_awaited_once()

    async def test_successful_job_is_deleted(self) -> None:
        worker = self._make_worker()
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.failed = AsyncMock()

        job = _DummyJob()
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1})

        worker.driver.delete.assert_awaited_once()
        self.assertIsNone(worker.current_job_id)

    async def test_shutdown_grace_releases_active_long_job(self) -> None:
        worker = self._make_worker(max_tries=3)
        cast(Any, worker).shutdown_grace = 0.01
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.release = AsyncMock()
        started = asyncio.Event()

        async def long_handle() -> None:
            started.set()
            await asyncio.sleep(60)

        job = _DummyJob()
        job.handle = long_handle  # type: ignore[method-assign]
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.return_value = job
            task = asyncio.create_task(worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1}))
            await started.wait()
            worker._handle_signal(15, None)
            await asyncio.wait_for(task, timeout=1)

        worker.driver.release.assert_awaited_once_with('j1', 'default', 10)
        worker.driver.delete.assert_not_called()
        self.assertIsNone(worker.current_job_id)

    async def test_heartbeat_refreshes_active_job_until_completion(self) -> None:
        worker = self._make_worker()
        cast(Any, worker).heartbeat_interval = 0.01
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.heartbeat = AsyncMock()

        async def slow_handle() -> None:
            await asyncio.sleep(0.03)

        job = _DummyJob()
        job.handle = slow_handle  # type: ignore[method-assign]
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1})

        self.assertGreaterEqual(worker.driver.heartbeat.await_count, 1)


class QueueWorkerHeartbeatTests(_WorkerSignalGuard):
    async def test_write_worker_heartbeat_includes_state_and_current_job(self) -> None:
        worker = self._make_worker(queue_name='emails')
        worker.driver = MagicMock()
        worker.driver.write_worker_heartbeat = AsyncMock()
        worker.current_job_id = 'j1'
        worker.state = 'draining'

        await worker._write_worker_heartbeat()

        heartbeat = worker.driver.write_worker_heartbeat.await_args.args[0]
        self.assertEqual(heartbeat['worker_id'], worker.worker_id)
        self.assertEqual(heartbeat['queue'], 'emails')
        self.assertEqual(heartbeat['state'], 'draining')
        self.assertEqual(heartbeat['current_job_id'], 'j1')
        self.assertIn('pid', heartbeat)

    async def test_mark_worker_dead_uses_driver_when_available(self) -> None:
        worker = self._make_worker()
        worker.driver = MagicMock()
        worker.driver.mark_worker_dead = AsyncMock()

        await worker._mark_worker_dead()

        worker.driver.mark_worker_dead.assert_awaited_once_with(worker.worker_id)


class QueueWorkerReaperTests(_WorkerSignalGuard):
    async def test_run_reaper_when_due_reaps_and_publishes_stats(self) -> None:
        worker = self._make_worker(queue_name='emails')
        worker.reaper_interval = 1
        worker.visibility_timeout = 120
        worker._last_reaper_run = 0.0
        worker.driver = MagicMock()
        worker.driver.reap_expired = AsyncMock(return_value=2)
        stats = {'queue': 'emails', 'ready': 1, 'reserved': 0, 'delayed': 0, 'failed': 0}
        worker.driver.stats = AsyncMock(return_value=stats)

        with patch('routemq.queue.queue_worker.lifecycle') as lifecycle:
            await worker._run_reaper_if_due()

        worker.driver.reap_expired.assert_awaited_once_with('emails', 120)
        worker.driver.stats.assert_awaited_once_with('emails')
        lifecycle.assert_called_once_with('queue.stats', stats)

    async def test_run_reaper_is_throttled_until_interval_elapsed(self) -> None:
        worker = self._make_worker()
        worker.reaper_interval = 60
        worker._last_reaper_run = asyncio.get_running_loop().time()
        worker.driver = MagicMock()
        worker.driver.reap_expired = AsyncMock()
        worker.driver.stats = AsyncMock()

        await worker._run_reaper_if_due()

        worker.driver.reap_expired.assert_not_awaited()
        worker.driver.stats.assert_not_awaited()

    async def test_run_reaper_skips_when_interval_disabled(self) -> None:
        worker = self._make_worker()
        worker.reaper_interval = 0
        worker.driver = MagicMock()
        worker.driver.reap_expired = AsyncMock()

        await worker._run_reaper_if_due()

        worker.driver.reap_expired.assert_not_awaited()

    async def test_handle_timeout_marks_as_failure_and_retries(self) -> None:
        worker = self._make_worker(max_tries=3)
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.release = AsyncMock()

        import asyncio

        async def slow_handle() -> None:
            await asyncio.sleep(10)

        async def timeout_wait_for(coro: Any, timeout: float | None = None) -> None:
            coro.close()
            raise asyncio.TimeoutError

        job = _DummyJob(timeout=0)
        job.handle = slow_handle  # type: ignore[method-assign]
        with (
            patch('routemq.queue.queue_worker.Job') as mock_job_cls,
            patch('routemq.queue.queue_worker.asyncio.wait_for', side_effect=timeout_wait_for),
        ):
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1})

        worker.driver.release.assert_awaited_once()

    async def test_timeout_exception_chain_is_preserved_for_failure_handling(self) -> None:
        worker = self._make_worker(max_tries=1)
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker._fail_job = AsyncMock()

        import asyncio

        timeout_exc = asyncio.TimeoutError()

        async def slow_handle() -> None:
            return None

        async def timeout_wait_for(coro: Any, timeout: float | None = None) -> None:
            coro.close()
            raise timeout_exc

        job = _DummyJob(timeout=0)
        job.handle = slow_handle  # type: ignore[method-assign]
        with (
            patch('routemq.queue.queue_worker.Job') as mock_job_cls,
            patch('routemq.queue.queue_worker.asyncio.wait_for', side_effect=timeout_wait_for),
            self.assertLogs('RouteMQ.QueueWorker', level='ERROR') as logs,
        ):
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1})

        await_args = worker._fail_job.await_args
        self.assertIsNotNone(await_args)
        assert await_args is not None
        failed_exception = await_args.args[1]
        self.assertIs(failed_exception.__cause__, timeout_exc)
        worker.driver.delete.assert_awaited_once()
        self.assertTrue(any('timed out' in output for output in logs.output))
        self.assertTrue(any(record.exc_info is not None for record in logs.records))

    async def test_failure_with_remaining_tries_releases_job(self) -> None:
        worker = self._make_worker(max_tries=3)
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.release = AsyncMock()

        job = _DummyJob(raises=RuntimeError('boom'))
        with (
            patch('routemq.queue.queue_worker.Job') as mock_job_cls,
            self.assertLogs('RouteMQ.QueueWorker', level='ERROR') as logs,
        ):
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1})

        worker.driver.release.assert_awaited_once()
        self.assertIn('Job j1 failed', logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    async def test_failure_with_backoff_enabled_uses_job_delay_calculation(self) -> None:
        worker = self._make_worker(max_tries=3)
        worker.retry_backoff_enabled = True
        worker.retry_backoff_max_delay = 99
        worker.retry_backoff_jitter = 0.5
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.release = AsyncMock()

        job = _DummyJob(raises=RuntimeError('boom'))
        job.get_retry_delay = MagicMock(return_value=42)
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 2})

        job.get_retry_delay.assert_called_once_with(
            2,
            backoff_enabled=True,
            max_delay=99,
            jitter=0.5,
        )
        worker.driver.release.assert_awaited_once_with('j1', 'default', 42)

    async def test_failure_with_max_tries_calls_fail_job(self) -> None:
        worker = self._make_worker(max_tries=2)
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker._fail_job = AsyncMock()

        job = _DummyJob(raises=RuntimeError('boom'))
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 2})

        worker._fail_job.assert_awaited_once()

    async def test_corrupted_payload_is_deleted(self) -> None:
        worker = self._make_worker()
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()

        with (
            patch('routemq.queue.queue_worker.Job') as mock_job_cls,
            self.assertLogs('RouteMQ.QueueWorker', level='ERROR') as logs,
        ):
            mock_job_cls.unserialize.side_effect = ValueError('cannot unserialize')
            await worker._process_job({'id': 'j1', 'payload': 'garbage', 'attempts': 1})

        worker.driver.delete.assert_awaited_once()
        self.assertTrue(any('Failed to unserialize job j1' in output for output in logs.output))
        self.assertTrue(any(record.exc_info is not None for record in logs.records))


class QueueWorkerWorkLoopTests(_WorkerSignalGuard):
    async def test_work_exits_immediately_when_should_quit(self) -> None:
        worker = self._make_worker(max_jobs=99, sleep=0)
        driver = MagicMock()
        driver.pop = AsyncMock()
        worker.queue_manager.get_driver = MagicMock(return_value=driver)
        worker.should_quit = True

        await worker.work()

        driver.pop.assert_not_called()
        self.assertEqual(worker.jobs_processed, 0)

    async def test_work_sleeps_and_continues_when_paused(self) -> None:
        worker = self._make_worker(sleep=0)
        driver = MagicMock()
        pop_calls = 0

        async def pop_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal pop_calls
            pop_calls += 1
            worker.should_quit = True
            return None

        worker.paused = True
        worker.queue_manager.get_driver = MagicMock(return_value=driver)
        # After one sleep cycle, unpause and stop
        original_sleep = worker.sleep
        worker.sleep = 0

        async def unpause_and_stop():
            worker.paused = False
            worker.should_quit = True

        driver.pop = AsyncMock(side_effect=pop_side_effect)

        # Override sleep so it exits after one paused iteration
        async def sleep_side_effect(duration):
            worker.paused = False
            worker.should_quit = True

        with patch('asyncio.sleep', AsyncMock(side_effect=sleep_side_effect)):
            await worker.work()

        worker.sleep = original_sleep
        driver.pop.assert_not_called()

    async def test_work_sleeps_when_no_job_available(self) -> None:
        worker = self._make_worker(sleep=0)
        driver = MagicMock()
        pop_calls = 0

        async def pop_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal pop_calls
            pop_calls += 1
            if pop_calls >= 3:
                worker.should_quit = True
            return None

        driver.pop = AsyncMock(side_effect=pop_side_effect)
        worker.queue_manager.get_driver = MagicMock(return_value=driver)

        await worker.work()

        self.assertGreaterEqual(driver.pop.await_count, 2)

    async def test_work_catches_pop_exception_and_continues(self) -> None:
        worker = self._make_worker(sleep=0)
        driver = MagicMock()
        pop_calls = 0

        async def pop_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal pop_calls
            pop_calls += 1
            if pop_calls == 1:
                raise RuntimeError('pop error')
            worker.should_quit = True
            return None

        driver.pop = AsyncMock(side_effect=pop_side_effect)
        worker.queue_manager.get_driver = MagicMock(return_value=driver)

        with self.assertLogs('RouteMQ.QueueWorker', level='ERROR') as logs:
            await worker.work()

        self.assertGreaterEqual(pop_calls, 2)
        self.assertIn('Error in worker loop for queue default', logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    async def test_process_job_recovers_if_second_unserialize_succeeds(self) -> None:
        worker = self._make_worker(connection='redis')
        driver = MagicMock()
        driver.delete = AsyncMock()
        driver.release = AsyncMock()
        worker.driver = cast(Any, driver)

        job = _DummyJob(raises=RuntimeError('boom'))
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.side_effect = [ValueError('first fail'), job]
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 2})

        driver.release.assert_awaited_once()
        driver.delete.assert_not_called()


class QueueWorkerShouldStopExtraTests(_WorkerSignalGuard):
    def test_max_time_not_exceeded_does_not_stop(self) -> None:
        worker = self._make_worker(max_time=10)
        worker.start_time = 1000.0
        with patch(
            'routemq.queue.queue_worker.asyncio.get_event_loop',
            return_value=MagicMock(time=MagicMock(return_value=1005.0)),
        ):
            self.assertFalse(worker._should_stop())


class QueueWorkerFailJobTests(_WorkerSignalGuard):
    async def test_fail_job_calls_handlers(self) -> None:
        worker = self._make_worker(connection='redis')
        worker.driver = MagicMock()
        worker.driver.failed = AsyncMock()

        job = _DummyJob()
        await worker._fail_job(cast(Any, job), RuntimeError('boom'))

        self.assertTrue(job.failed_called)
        worker.driver.failed.assert_awaited_once()

    async def test_fail_job_swallows_exceptions(self) -> None:
        worker = self._make_worker()
        worker.driver = MagicMock()
        worker.driver.failed = AsyncMock(side_effect=RuntimeError('storage down'))

        job = _DummyJob()
        with self.assertLogs('RouteMQ.QueueWorker', level='ERROR') as logs:
            await worker._fail_job(cast(Any, job), RuntimeError('orig'))

        self.assertIn('Error handling failed job', logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)


if __name__ == '__main__':
    unittest.main()
