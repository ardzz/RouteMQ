import logging
import unittest
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

    async def test_handle_timeout_marks_as_failure_and_retries(self) -> None:
        worker = self._make_worker(max_tries=3)
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.release = AsyncMock()

        import asyncio

        async def slow_handle() -> None:
            await asyncio.sleep(10)

        job = _DummyJob(timeout=0)
        job.handle = slow_handle  # type: ignore[method-assign]
        with (
            patch('routemq.queue.queue_worker.Job') as mock_job_cls,
            patch(
                'routemq.queue.queue_worker.asyncio.wait_for',
                AsyncMock(side_effect=asyncio.TimeoutError()),
            ),
        ):
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1})

        worker.driver.release.assert_awaited_once()

    async def test_failure_with_remaining_tries_releases_job(self) -> None:
        worker = self._make_worker(max_tries=3)
        worker.driver = MagicMock()
        worker.driver.delete = AsyncMock()
        worker.driver.release = AsyncMock()

        job = _DummyJob(raises=RuntimeError('boom'))
        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.return_value = job
            await worker._process_job({'id': 'j1', 'payload': 'p', 'attempts': 1})

        worker.driver.release.assert_awaited_once()

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

        with patch('routemq.queue.queue_worker.Job') as mock_job_cls:
            mock_job_cls.unserialize.side_effect = ValueError('cannot unserialize')
            await worker._process_job({'id': 'j1', 'payload': 'garbage', 'attempts': 1})

        worker.driver.delete.assert_awaited_once()


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

        await worker.work()

        self.assertGreaterEqual(pop_calls, 2)

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
        await worker._fail_job(cast(Any, job), RuntimeError('orig'))


if __name__ == '__main__':
    unittest.main()
