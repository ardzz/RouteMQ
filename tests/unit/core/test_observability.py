import json
import unittest
from importlib import import_module
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bootstrap.app import Application
from routemq.job import Job
from routemq.middleware import Middleware
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager
from routemq.queue.queue_worker import QueueWorker
from routemq.router import Router
from routemq.worker_manager import WorkerProcess

observability = import_module('routemq.observability')


class ObservableJob(Job):
    seen_contexts: list[dict[str, Any]] = []

    async def handle(self) -> None:
        self.__class__.seen_contexts.append(observability.snapshot_context())


Job.register(ObservableJob)


class ObservabilityTestCase(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        observability.clear_hooks()


class ObservabilityUtilitiesTests(ObservabilityTestCase):
    def test_set_context_snapshot_and_reset_do_not_leak(self) -> None:
        token = observability.set_context({'correlation_id': 'corr-1', 'tenant': 'acme'})
        try:
            self.assertEqual(observability.get_correlation_id(), 'corr-1')
            self.assertEqual(observability.snapshot_context()['tenant'], 'acme')
        finally:
            observability.reset_context(token)

        self.assertIsNone(observability.get_correlation_id())
        self.assertEqual(observability.get_context_attributes(), {})

    def test_hook_exceptions_are_swallowed(self) -> None:
        calls: list[str] = []

        def broken_trace(name: str, attributes: dict[str, Any]) -> None:
            calls.append(name)
            raise RuntimeError('trace hook failed')

        def broken_metric(name: str, value: float, attributes: dict[str, Any]) -> None:
            calls.append(f'{name}:{value}')
            raise RuntimeError('metric hook failed')

        observability.register_trace_hook(broken_trace)
        observability.register_metric_hook(broken_metric)

        observability.lifecycle('test.event', {'ok': True}, value=2.0)

        self.assertEqual(calls, ['test.event', 'test.event:2.0'])


class RouterObservabilityTests(ObservabilityTestCase):
    async def test_router_enriches_middleware_context_and_resets_after_dispatch(self) -> None:
        router = Router()
        client = MagicMock()
        seen_context: dict[str, Any] = {}

        class CaptureMiddleware(Middleware):
            async def handle(self, context: dict[str, Any], next_handler: Any) -> Any:
                seen_context.update(context)
                return await next_handler(context)

        async def handler(device_id: str, payload: Any, client: Any) -> None:
            seen_context['handler_correlation_id'] = observability.get_correlation_id()
            seen_context['handler_device_id'] = device_id

        token = observability.set_context({'correlation_id': 'router-corr', 'tenant': 'tenant-a'})
        try:
            router.on('devices/{device_id}/status', handler, middleware=[CaptureMiddleware()])
            await router.dispatch('devices/123/status', {'ok': True}, client)
        finally:
            observability.reset_context(token)

        self.assertEqual(seen_context['correlation_id'], 'router-corr')
        self.assertEqual(seen_context['observability']['tenant'], 'tenant-a')
        self.assertEqual(seen_context['observability']['route_pattern'], 'devices/{device_id}/status')
        self.assertEqual(seen_context['route_pattern'], 'devices/{device_id}/status')
        self.assertEqual(seen_context['handler_correlation_id'], 'router-corr')
        self.assertEqual(seen_context['handler_device_id'], '123')
        self.assertIsNone(observability.get_correlation_id())

    async def test_noop_hooks_do_not_mask_handler_errors(self) -> None:
        router = Router()
        observability.register_trace_hook(lambda name, attributes: (_ for _ in ()).throw(RuntimeError('hook')))
        observability.register_metric_hook(lambda name, value, attributes: (_ for _ in ()).throw(RuntimeError('hook')))

        async def handler(payload: Any, client: Any) -> None:
            raise ValueError('user failure')

        router.on('boom', handler)

        with self.assertRaisesRegex(ValueError, 'user failure'):
            await router.dispatch('boom', {}, MagicMock())


class MqttObservabilityTests(ObservabilityTestCase):
    async def test_application_dispatch_wrapper_sets_and_resets_loop_context(self) -> None:
        app = object.__new__(Application)
        app.router = MagicMock()
        seen: dict[str, Any] = {}

        async def dispatch(topic: str, payload: Any, client: Any) -> None:
            seen.update(observability.snapshot_context())

        app.router.dispatch = dispatch

        await app._dispatch_mqtt_message('devices/1', {'ok': True}, MagicMock(), {'mqtt_topic': 'devices/1'})

        self.assertEqual(seen['mqtt_topic'], 'devices/1')
        self.assertIsInstance(seen['correlation_id'], str)
        self.assertIsNone(observability.get_correlation_id())

    def test_worker_message_wrapper_sets_worker_context_and_resets(self) -> None:
        worker = WorkerProcess(
            worker_id=7,
            router_directory='app.routers',
            shared_routes=[],
            broker_config={'broker': 'localhost', 'port': 1883},
            group_name='workers',
        )
        seen: dict[str, Any] = {}

        async def dispatch(topic: str, payload: Any, client: Any) -> None:
            seen.update(observability.snapshot_context())
            seen['topic_arg'] = topic

        worker.router = MagicMock()
        worker.router.dispatch = dispatch
        msg = MagicMock(topic='$share/workers/devices/9/status', payload=b'{}')

        worker._on_message(MagicMock(), None, msg)

        self.assertEqual(seen['worker_id'], 7)
        self.assertEqual(seen['mqtt_topic'], '$share/workers/devices/9/status')
        self.assertEqual(seen['actual_topic'], 'devices/9/status')
        self.assertEqual(seen['group_name'], 'workers')
        self.assertEqual(seen['topic_arg'], 'devices/9/status')
        self.assertIsNone(observability.get_correlation_id())


class QueueObservabilityTests(ObservabilityTestCase):
    def setUp(self) -> None:
        super().setUp()
        ObservableJob.seen_contexts.clear()
        self._manager_instance = QueueManager._instance
        self._manager_driver = QueueManager._driver
        self._manager_default = QueueManager._default_connection
        QueueManager._instance = None
        QueueManager._driver = None

    def tearDown(self) -> None:
        QueueManager._instance = self._manager_instance
        QueueManager._driver = self._manager_driver
        QueueManager._default_connection = self._manager_default
        super().tearDown()

    async def test_queue_manager_serializes_current_observability_context(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.push = AsyncMock()
        token = observability.set_context({'correlation_id': 'queue-corr', 'tenant': 'tenant-q'})
        try:
            with patch.object(manager, 'get_driver', return_value=driver):
                await manager.push(ObservableJob(), queue='observed')
        finally:
            observability.reset_context(token)

        payload = json.loads(driver.push.await_args.args[0])
        self.assertEqual(payload['observability']['correlation_id'], 'queue-corr')
        self.assertEqual(payload['observability']['tenant'], 'tenant-q')
        self.assertEqual(payload['observability']['queue'], 'observed')
        self.assertNotIn('observability', payload['data'])

    async def test_queue_worker_restores_job_context_and_resets_after_success(self) -> None:
        job = ObservableJob()
        job.capture_observability_context({'correlation_id': 'job-corr', 'tenant': 'tenant-job'})
        worker = QueueWorker(queue_name='observed', sleep=0)
        driver = MagicMock(spec=QueueDriver)
        driver.delete = AsyncMock()
        driver.release = AsyncMock()
        driver.failed = AsyncMock()
        worker.driver = driver

        await worker._process_job({'id': 'job-1', 'payload': job.serialize(), 'attempts': 1})

        self.assertEqual(ObservableJob.seen_contexts[-1]['correlation_id'], 'job-corr')
        self.assertEqual(ObservableJob.seen_contexts[-1]['tenant'], 'tenant-job')
        self.assertEqual(ObservableJob.seen_contexts[-1]['job_id'], 'job-1')
        self.assertEqual(ObservableJob.seen_contexts[-1]['queue'], 'observed')
        self.assertIsNone(observability.get_correlation_id())


if __name__ == '__main__':
    unittest.main()
