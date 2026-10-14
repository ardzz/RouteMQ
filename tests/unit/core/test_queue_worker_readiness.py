import asyncio
import gc
import http.client
import json
import logging
import socket
import threading
import time
import unittest
import warnings
from typing import Any
from unittest.mock import patch

from routemq.health import HealthServer
from routemq.job import Job
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_worker import QueueWorker


class BlockingReadinessJob(Job):
    started: asyncio.Event
    release: asyncio.Event

    async def handle(self) -> None:
        BlockingReadinessJob.started.set()
        await BlockingReadinessJob.release.wait()


Job.register(BlockingReadinessJob)


class ScriptedQueueDriver(QueueDriver):
    def __init__(self, jobs: list[dict[str, Any]] | None = None) -> None:
        self.jobs = list(jobs or [])

    async def push(self, payload: str, queue: str = 'default', delay: int = 0) -> None:
        return None

    async def pop(self, queue: str = 'default') -> dict | None:
        return self.jobs.pop(0) if self.jobs else None

    async def release(self, job_id: int | str, queue: str, delay: int = 0) -> None:
        return None

    async def delete(self, job_id: int | str, queue: str) -> None:
        return None

    async def failed(self, connection: str, queue: str, payload: str, exception: str) -> None:
        return None

    async def size(self, queue: str = 'default') -> int:
        return len(self.jobs)


class ScriptedBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[asyncio.AbstractEventLoop, threading.Thread, str | None]] = []
        self.error: Exception | None = None
        self.hang = False
        self.gate: asyncio.Event | None = None
        self.entered = asyncio.Event()
        self.cancelled = threading.Event()

    async def validate_connection(self, connection: str | None = None) -> str:
        self.calls.append((asyncio.get_running_loop(), threading.current_thread(), connection))
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.hang:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        if self.error is not None:
            raise self.error
        return 'redis'


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _get(port: int, path: str) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class QueueWorkerReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        logger = logging.getLogger('RouteMQ.QueueWorker')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

        with patch('signal.signal'):
            self.worker = QueueWorker(queue_name='emails', connection='redis', sleep=1)
        self.driver = ScriptedQueueDriver()
        self.backend = ScriptedBackend()
        for patcher in (
            patch.object(self.worker.queue_manager, 'get_driver', return_value=self.driver),
            patch.object(self.worker.queue_manager, 'validate_connection', self.backend.validate_connection),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.server = HealthServer(self.worker, port=_free_port())
        self.server.start()
        self.addCleanup(self.server.stop)
        self.task: asyncio.Task[None] | None = None

    async def asyncTearDown(self) -> None:
        if self.task is not None and not self.task.done():
            self.worker.stop()
            await asyncio.wait_for(self.task, timeout=5)

    async def _request(self, path: str = '/ready') -> tuple[int, dict[str, Any]]:
        return await asyncio.to_thread(_get, self.server.port, path)

    async def _start_worker(self) -> dict[str, Any]:
        self.task = asyncio.create_task(self.worker.work())
        deadline = time.monotonic() + 5
        while True:
            code, payload = await self._request()
            if code == 200:
                return payload
            if self.task.done() or time.monotonic() > deadline:
                self.fail(f'worker never became ready: {payload}')
            await asyncio.sleep(0.01)

    async def test_ready_is_unavailable_before_worker_loop_starts_without_backend_probe(self) -> None:
        code, payload = await self._request()
        health_code, _ = await self._request('/health')

        self.assertEqual(code, 503)
        self.assertEqual(payload['status'], 'not_ready')
        self.assertFalse(payload['initialized'])
        self.assertNotIn('mqtt_connected', payload)
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(health_code, 200)

    async def test_idle_worker_validates_selected_backend_on_its_own_loop_for_each_probe(self) -> None:
        worker_loop = asyncio.get_running_loop()
        worker_thread = threading.current_thread()

        payload = await self._start_worker()
        calls_after_first_ready = len(self.backend.calls)
        second_code, _ = await self._request()

        self.assertEqual(payload['status'], 'ready')
        self.assertEqual(payload['connection'], 'redis')
        self.assertEqual(payload['queue'], 'emails')
        self.assertEqual(second_code, 200)
        self.assertEqual(len(self.backend.calls), calls_after_first_ready + 1)
        for loop, thread, connection in self.backend.calls:
            self.assertIs(loop, worker_loop)
            self.assertIs(thread, worker_thread)
            self.assertEqual(connection, 'redis')

    async def test_backend_failure_reports_not_ready_until_backend_recovers(self) -> None:
        await self._start_worker()

        self.backend.error = ConnectionError('redis unavailable')
        failed_code, failed_payload = await self._request()
        self.backend.error = None
        recovered_code, recovered_payload = await self._request()

        self.assertEqual(failed_code, 503)
        self.assertEqual(failed_payload['status'], 'not_ready')
        self.assertEqual(failed_payload['error'], 'ConnectionError')
        self.assertEqual(recovered_code, 200)
        self.assertEqual(recovered_payload['status'], 'ready')

    async def test_hung_backend_probe_is_bounded_and_cancelled_on_worker_loop(self) -> None:
        await self._start_worker()
        self.backend.hang = True

        with patch('routemq.queue.queue_worker.READINESS_TIMEOUT_SECONDS', 0.2):
            started = time.monotonic()
            code, payload = await self._request()
            elapsed = time.monotonic() - started

        self.assertEqual(code, 503)
        self.assertEqual(payload['error'], 'TimeoutError')
        self.assertLess(elapsed, 2)
        self.assertTrue(await asyncio.to_thread(self.backend.cancelled.wait, 2))

    async def test_unresponsive_event_loop_reports_not_ready_then_recovers(self) -> None:
        await self._start_worker()
        loop = asyncio.get_running_loop()
        probe_done = threading.Event()

        def probe_while_loop_is_blocked() -> tuple[int, dict[str, Any]]:
            try:
                return _get(self.server.port, '/ready')
            finally:
                probe_done.set()

        with patch('routemq.queue.queue_worker.READINESS_TIMEOUT_SECONDS', 0.2):
            loop.call_soon(probe_done.wait, 5)
            blocked_code, blocked_payload = await asyncio.to_thread(probe_while_loop_is_blocked)
            recovered_code, _ = await self._request()

        self.assertEqual(blocked_code, 503)
        self.assertEqual(blocked_payload['error'], 'TimeoutError')
        self.assertEqual(recovered_code, 200)

    async def test_busy_worker_with_responsive_loop_stays_ready(self) -> None:
        BlockingReadinessJob.started = asyncio.Event()
        BlockingReadinessJob.release = asyncio.Event()
        self.driver.jobs.append({'id': 'job-1', 'payload': BlockingReadinessJob().serialize(), 'attempts': 1})

        self.task = asyncio.create_task(self.worker.work())
        await asyncio.wait_for(BlockingReadinessJob.started.wait(), timeout=5)
        code, payload = await self._request()
        BlockingReadinessJob.release.set()

        self.assertEqual(code, 200)
        self.assertEqual(payload['state'], 'running')

    async def test_paused_worker_is_not_ready_until_resumed(self) -> None:
        await self._start_worker()
        calls_before_pause = len(self.backend.calls)

        self.worker.pause()
        paused_code, paused_payload = await self._request()
        calls_while_paused = len(self.backend.calls)
        self.worker.resume()
        resumed_code, _ = await self._request()

        self.assertEqual(paused_code, 503)
        self.assertTrue(paused_payload['paused'])
        self.assertEqual(calls_while_paused, calls_before_pause)
        self.assertEqual(resumed_code, 200)

    async def test_shutdown_reports_not_ready_immediately_and_after_worker_exit(self) -> None:
        await self._start_worker()

        self.worker.stop()
        # Read before the worker loop can exit; a stopping worker must answer without scheduling a loop probe.
        stopping_code, stopping_payload = self.worker.readiness_payload()
        assert self.task is not None
        await asyncio.wait_for(self.task, timeout=5)
        stopped_code, stopped_payload = await self._request()
        health_code, health_payload = await self._request('/health')

        self.assertEqual(stopping_code, 503)
        self.assertEqual(stopping_payload['state'], 'stopping')
        self.assertEqual(stopped_code, 503)
        self.assertEqual(stopped_payload['state'], 'dead')
        self.assertFalse(stopped_payload['initialized'])
        self.assertEqual(health_code, 503)
        self.assertFalse(health_payload['alive'])

    async def test_shutdown_during_in_flight_probe_never_reports_ready_and_closes_listener(self) -> None:
        await self._start_worker()
        self.backend.entered.clear()
        self.backend.gate = asyncio.Event()

        # Generous probe bound so the held validation finishes by release, not by timeout.
        with patch('routemq.queue.queue_worker.READINESS_TIMEOUT_SECONDS', 30):
            probe = asyncio.create_task(self._request())
            await asyncio.wait_for(self.backend.entered.wait(), timeout=5)
            self.worker.stop()
            assert self.task is not None
            await asyncio.wait_for(self.task, timeout=5)
            self.server.stop()
            self.backend.gate.set()
            code, payload = await asyncio.wait_for(probe, timeout=5)

        self.assertEqual(code, 503)
        self.assertEqual(payload['status'], 'not_ready')
        self.assertEqual(payload['state'], 'dead')
        self.assertEqual(payload['connection'], 'redis')
        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(('127.0.0.1', self.server.port), timeout=1).close()

    async def test_startup_failure_never_reports_ready(self) -> None:
        with patch.object(self.worker.queue_manager, 'get_driver', side_effect=RuntimeError('database disabled')):
            with self.assertRaisesRegex(RuntimeError, 'database disabled'):
                await self.worker.work()

        code, payload = await self._request()

        self.assertEqual(code, 503)
        self.assertFalse(payload['initialized'])
        self.assertEqual(self.backend.calls, [])

    async def test_closed_worker_loop_reports_not_ready_without_leaking_probe_coroutine(self) -> None:
        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        self.worker._loop = closed_loop

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            code, payload = await self._request()
            gc.collect()

        self.assertEqual(code, 503)
        self.assertEqual(payload['error'], 'RuntimeError')
        self.assertFalse([warning for warning in caught if 'was never awaited' in str(warning.message)])


if __name__ == '__main__':
    unittest.main()
