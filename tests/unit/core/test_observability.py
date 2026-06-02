import json
import os
import unittest
from importlib import import_module
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.middleware.rate_limit import RateLimitMiddleware
from bootstrap.app import Application
from routemq.job import Job
from routemq.middleware import Middleware
from routemq.model import Model
from routemq.queue.database_queue import DatabaseQueue
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager
from routemq.queue.queue_worker import QueueWorker
from routemq.queue.redis_queue import RedisQueue
from routemq.redis_manager import RedisManager
from routemq.router import Router
from routemq.worker_manager import WorkerProcess

observability = import_module('routemq.observability')


class ObservableJob(Job):
    seen_contexts: list[dict[str, Any]] = []

    async def handle(self) -> None:
        self.__class__.seen_contexts.append(observability.snapshot_context())


Job.register(ObservableJob)


class ObservabilityTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._tracing_env = patch.dict(os.environ, {'ENABLE_TRACING': 'true'})
        self._tracing_env.start()

    def tearDown(self) -> None:
        observability.clear_hooks()
        self._tracing_env.stop()
        super().tearDown()


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

    def test_span_context_ids_snapshot_and_copied_hook_payloads(self) -> None:
        first_hook: list[Any] = []
        second_hook: list[Any] = []

        def mutate_snapshot(snapshot: Any) -> None:
            snapshot.attributes['mutated'] = True
            first_hook.append(snapshot)

        def capture_snapshot(snapshot: Any) -> None:
            second_hook.append(snapshot)

        observability.register_span_hook(mutate_snapshot)
        observability.register_span_hook(capture_snapshot)

        with observability.start_span('test.span', {'component': 'unit'}, kind='consumer') as span:
            self.assertIsNotNone(span)
            active = observability.current_span()
            self.assertIs(active, span)
            context = observability.snapshot_context()
            self.assertEqual(context['trace_id'], span.trace_id)
            self.assertEqual(context['span_id'], span.span_id)
            self.assertEqual(context['trace_flags'], '01')
            self.assertIsNone(context['parent_span_id'])

        self.assertIsNone(observability.current_span())
        self.assertEqual(len(first_hook), 1)
        self.assertEqual(len(second_hook), 1)
        emitted = second_hook[0]
        self.assertEqual(emitted.name, 'test.span')
        self.assertEqual(emitted.status, 'OK')
        self.assertEqual(len(emitted.trace_id), 32)
        self.assertEqual(len(emitted.span_id), 16)
        self.assertEqual(emitted.attributes['component'], 'unit')
        self.assertNotIn('mutated', emitted.attributes)

    def test_span_records_exception_status_and_isolates_hook_failures(self) -> None:
        spans: list[Any] = []

        def broken_hook(snapshot: Any) -> None:
            raise RuntimeError('span hook failed')

        observability.register_span_hook(broken_hook)
        observability.register_span_hook(spans.append)

        with self.assertRaisesRegex(ValueError, 'boom'):
            with observability.start_span('test.error'):
                raise ValueError('boom')

        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status, 'ERROR')
        self.assertEqual(spans[0].status_message, 'ValueError')
        self.assertEqual(spans[0].attributes['error.type'], 'ValueError')
        self.assertEqual(spans[0].events[0].attributes['error.type'], 'ValueError')

    def test_start_span_is_noop_when_tracing_is_disabled(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        with patch.dict(os.environ, {'ENABLE_TRACING': 'false'}):
            with observability.start_span('disabled') as span:
                self.assertIsNone(span)
                self.assertIsNone(observability.current_span())
                self.assertNotIn('trace_id', observability.snapshot_context())

        self.assertEqual(spans, [])

    def test_span_handles_preexisting_collections_and_lazy_initialization(self) -> None:
        seeded_events = (observability.SpanEvent(name='seeded', attributes={'k': 'v'}, timestamp_ns=1),)
        span = observability.Span(
            name='preset',
            trace_id='a' * 32,
            span_id='b' * 16,
            parent_span_id=None,
            attributes={'preset': True},
            events=list(seeded_events),
        )
        self.assertEqual(span.attributes, {'preset': True})
        self.assertEqual(len(span.events or []), 1)

        span.attributes = None  # type: ignore[assignment]
        span.set_attribute('lazy_attr', 1)
        self.assertEqual(span.attributes, {'lazy_attr': 1})

        span.events = None  # type: ignore[assignment]
        span.add_event('lazy_event')
        self.assertEqual(len((span.events or [])), 1)

        explicit_end = span.start_time_ns + 5
        span.end_time_ns = explicit_end
        snapshot = span.end()
        self.assertEqual(snapshot.end_time_ns, explicit_end)

    def test_validators_reject_non_hex_input_and_short_flags(self) -> None:
        self.assertFalse(observability._valid_hex('nothex' * 5 + 'xx', 32))
        self.assertFalse(observability._valid_hex(123, 32))  # type: ignore[arg-type]
        self.assertFalse(observability._valid_trace_flags('zz'))
        self.assertFalse(observability._valid_trace_flags('012'))
        self.assertFalse(observability._valid_trace_flags(None))  # type: ignore[arg-type]

    def test_correlation_helpers_set_and_reset_explicit_values(self) -> None:
        token = observability.set_correlation_id('explicit-corr')
        try:
            self.assertEqual(observability.get_correlation_id(), 'explicit-corr')
        finally:
            observability.reset_correlation_id(token)
        self.assertIsNone(observability.get_correlation_id())

    def test_job_context_from_payload_handles_bad_payloads(self) -> None:
        self.assertEqual(observability.job_context_from_payload('not json'), {})
        self.assertEqual(observability.job_context_from_payload(json.dumps({})), {})
        self.assertEqual(
            observability.job_context_from_payload(json.dumps({'observability': 'string'})),
            {},
        )
        good = json.dumps({'observability': {'trace_id': 'x'}})
        self.assertEqual(observability.job_context_from_payload(good), {'trace_id': 'x'})

    def test_hook_unregister_idempotent_across_kinds(self) -> None:
        events: list[str] = []
        unregister_trace = observability.register_trace_hook(lambda name, attrs: events.append(f't:{name}'))
        unregister_metric = observability.register_metric_hook(
            lambda name, value, attrs: events.append(f'm:{name}:{value}')
        )
        unregister_span = observability.register_span_hook(lambda snapshot: events.append(f's:{snapshot.name}'))

        observability.lifecycle('once', {'k': 'v'})
        with observability.start_span('unreg.span'):
            pass

        unregister_trace()
        unregister_metric()
        unregister_span()
        unregister_trace()
        unregister_metric()
        unregister_span()

        observability.lifecycle('twice', {'k': 'v'})
        with observability.start_span('unreg.span.2'):
            pass

        self.assertEqual(events, ['t:once', 'm:once:1.0', 's:unreg.span'])


class RouterObservabilityTests(ObservabilityTestCase):
    async def test_router_enriches_middleware_context_and_resets_after_dispatch(self) -> None:
        router = Router()
        client = MagicMock()
        seen_context: dict[str, Any] = {}
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

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
        self.assertEqual([span.name for span in spans], ['router.handler', 'router.middleware', 'router.dispatch'])
        handler_span, middleware_span, dispatch_span = spans
        self.assertEqual(handler_span.trace_id, dispatch_span.trace_id)
        self.assertEqual(middleware_span.trace_id, dispatch_span.trace_id)
        self.assertEqual(middleware_span.parent_span_id, dispatch_span.span_id)
        self.assertEqual(handler_span.parent_span_id, middleware_span.span_id)
        self.assertEqual(dispatch_span.attributes['messaging.destination.template'], 'devices/{device_id}/status')
        self.assertEqual(handler_span.attributes['routemq.handler.name'], handler.__qualname__)
        self.assertEqual(middleware_span.attributes['routemq.middleware.name'], 'CaptureMiddleware')

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
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        async def dispatch(topic: str, payload: Any, client: Any) -> None:
            seen.update(observability.snapshot_context())

        app.router.dispatch = dispatch

        await app._dispatch_mqtt_message('devices/1', {'ok': True}, MagicMock(), {'mqtt_topic': 'devices/1'})

        self.assertEqual(seen['mqtt_topic'], 'devices/1')
        self.assertIsInstance(seen['correlation_id'], str)
        self.assertEqual(seen['trace_id'], spans[0].trace_id)
        self.assertEqual(seen['span_id'], spans[0].span_id)
        self.assertEqual(spans[0].name, 'mqtt.receive')
        self.assertEqual(spans[0].kind, 'consumer')
        self.assertEqual(spans[0].attributes['messaging.system'], 'mqtt')
        self.assertEqual(spans[0].attributes['messaging.operation.type'], 'receive')
        self.assertEqual(spans[0].attributes['messaging.destination'], 'devices/1')
        self.assertEqual(spans[0].attributes['routemq.process.role'], 'main')
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
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

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
        self.assertEqual(seen['trace_id'], spans[0].trace_id)
        self.assertEqual(seen['span_id'], spans[0].span_id)
        self.assertEqual(spans[0].name, 'mqtt.receive')
        self.assertEqual(spans[0].attributes['messaging.operation.type'], 'receive')
        self.assertEqual(spans[0].attributes['routemq.process.role'], 'worker')
        self.assertEqual(spans[0].attributes['routemq.worker.id'], 7)
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
        spans: list[Any] = []
        observability.register_span_hook(spans.append)
        token = observability.set_context({'correlation_id': 'queue-corr', 'tenant': 'tenant-q'})
        try:
            with patch.object(manager, 'get_driver', return_value=driver):
                await manager.push(ObservableJob(), queue='observed')
        finally:
            observability.reset_context(token)

        payload = json.loads(driver.push.await_args.args[0])
        enqueue_span = spans[0]
        self.assertEqual(payload['observability']['correlation_id'], 'queue-corr')
        self.assertEqual(payload['observability']['tenant'], 'tenant-q')
        self.assertEqual(payload['observability']['queue'], 'observed')
        self.assertEqual(payload['observability']['trace_id'], enqueue_span.trace_id)
        self.assertEqual(payload['observability']['span_id'], enqueue_span.span_id)
        self.assertEqual(enqueue_span.name, 'queue.enqueue')
        self.assertEqual(enqueue_span.kind, 'producer')
        self.assertEqual(enqueue_span.attributes['messaging.destination'], 'observed')
        self.assertEqual(enqueue_span.attributes['routemq.job.name'], 'ObservableJob')
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

    async def test_queue_worker_creates_job_span_from_enqueued_trace_context(self) -> None:
        manager = QueueManager()
        driver = MagicMock(spec=QueueDriver)
        driver.push = AsyncMock()
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        with patch.object(manager, 'get_driver', return_value=driver):
            await manager.push(ObservableJob(), queue='observed')

        payload = driver.push.await_args.args[0]
        worker = QueueWorker(queue_name='observed', sleep=0)
        worker_driver = MagicMock(spec=QueueDriver)
        worker_driver.delete = AsyncMock()
        worker_driver.release = AsyncMock()
        worker_driver.failed = AsyncMock()
        worker.driver = worker_driver

        await worker._process_job({'id': 'job-linked', 'payload': payload, 'attempts': 1})

        enqueue_span = next(span for span in spans if span.name == 'queue.enqueue')
        job_span = next(span for span in spans if span.name == 'queue.job')
        self.assertNotEqual(job_span.span_id, enqueue_span.span_id)
        self.assertIsNone(job_span.parent_span_id)
        self.assertEqual(len(job_span.links), 1)
        self.assertEqual(job_span.links[0].trace_id, enqueue_span.trace_id)
        self.assertEqual(job_span.links[0].span_id, enqueue_span.span_id)
        self.assertEqual(job_span.links[0].attributes['routemq.link.type'], 'queue.enqueue')
        self.assertEqual(job_span.attributes['messaging.destination'], 'observed')
        self.assertEqual(job_span.attributes['routemq.job.name'], 'ObservableJob')
        self.assertEqual(ObservableJob.seen_contexts[-1]['trace_id'], job_span.trace_id)
        self.assertEqual(ObservableJob.seen_contexts[-1]['span_id'], job_span.span_id)
        self.assertIsNone(ObservableJob.seen_contexts[-1]['parent_span_id'])


class DbSpanTests(ObservabilityTestCase):
    async def test_model_create_tables_emits_client_span(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        original_enabled = Model._is_enabled
        original_engine = Model._engine
        Model._is_enabled = True
        Model._db_system = 'postgresql'
        Model._server_address = 'db.example.com'
        Model._server_port = 5432

        mock_engine = AsyncMock()
        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin = MagicMock(return_value=mock_cm)
        Model._engine = mock_engine

        try:
            await Model.create_tables()

            span = next(s for s in spans if s.name == 'postgresql')
            self.assertEqual(span.kind, 'client')
            self.assertEqual(span.attributes['db.system'], 'postgresql')
            self.assertEqual(span.attributes['db.operation'], 'create')
            self.assertEqual(span.attributes['db.query.text'], 'CREATE TABLE <metadata>')
            self.assertEqual(span.attributes['server.address'], 'db.example.com')
            self.assertEqual(span.attributes['server.port'], 5432)
            self.assertNotIn('db.collection.name', span.attributes)
        finally:
            Model._is_enabled = original_enabled
            Model._engine = original_engine

    async def test_database_queue_push_emits_client_span(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        original_enabled = Model._is_enabled
        original_factory = Model._session_factory
        Model._is_enabled = True
        Model._db_system = 'mysql'
        Model._server_address = 'localhost'
        Model._server_port = 3306

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        Model._session_factory = MagicMock(return_value=mock_session)

        queue = DatabaseQueue()

        try:
            await queue.push('{"class": "test", "data": {}}', queue='default')

            span = next(s for s in spans if s.name == 'insert queue_jobs')
            self.assertEqual(span.kind, 'client')
            self.assertEqual(span.attributes['db.system'], 'mysql')
            self.assertEqual(span.attributes['db.operation'], 'insert')
            self.assertEqual(span.attributes['db.collection.name'], 'queue_jobs')
            self.assertEqual(
                span.attributes['db.query.text'],
                'INSERT INTO queue_jobs (queue, payload, attempts, available_at, created_at) VALUES (:queue, :payload, :attempts, :available_at, :created_at)',
            )
            self.assertEqual(span.attributes['server.address'], 'localhost')
            self.assertEqual(span.attributes['server.port'], 3306)
        finally:
            Model._is_enabled = original_enabled
            Model._session_factory = original_factory

    async def test_database_queue_pop_emits_client_span(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        original_enabled = Model._is_enabled
        original_factory = Model._session_factory
        Model._is_enabled = True
        Model._db_system = 'postgresql'

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        Model._session_factory = MagicMock(return_value=mock_session)

        queue = DatabaseQueue()

        try:
            await queue.pop('default')

            span = next(s for s in spans if s.name == 'select queue_jobs')
            self.assertEqual(span.kind, 'client')
            self.assertEqual(span.attributes['db.system'], 'postgresql')
            self.assertEqual(span.attributes['db.operation'], 'select')
            self.assertEqual(span.attributes['db.collection.name'], 'queue_jobs')
            self.assertEqual(
                span.attributes['db.query.text'],
                'SELECT * FROM queue_jobs WHERE queue = :queue AND reserved_at IS NULL AND available_at <= :now ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED',
            )
        finally:
            Model._is_enabled = original_enabled
            Model._session_factory = original_factory

    def test_db_span_helpers_produce_correct_attrs_and_name(self) -> None:
        from routemq.model import _db_span_attributes, _db_span_name

        Model._db_system = 'postgresql'
        Model._server_address = 'db.example.com'
        Model._server_port = 5432

        attrs = _db_span_attributes('select', 'devices', 'SELECT * FROM devices WHERE id = :id')
        self.assertEqual(attrs['db.system'], 'postgresql')
        self.assertEqual(attrs['db.operation'], 'select')
        self.assertEqual(attrs['db.collection.name'], 'devices')
        self.assertEqual(attrs['db.query.text'], 'SELECT * FROM devices WHERE id = :id')
        self.assertEqual(attrs['server.address'], 'db.example.com')
        self.assertEqual(attrs['server.port'], 5432)

        self.assertEqual(_db_span_name('select', 'devices'), 'select devices')
        self.assertEqual(_db_span_name('create', None), 'postgresql')


class RedisSpanTests(ObservabilityTestCase):
    async def test_redis_manager_get_emits_client_span(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        manager = RedisManager()
        original_enabled = manager.enabled
        original_host = manager.host
        original_port = manager.port
        original_client = manager._redis_client

        manager.enabled = True
        manager.host = 'redis.example.com'
        manager.port = 6379

        mock_client = AsyncMock()
        mock_client.get.return_value = 'myvalue'
        manager._redis_client = mock_client

        try:
            result = await manager.get('mykey')
            self.assertEqual(result, 'myvalue')

            span = next(s for s in spans if s.name == 'redis.get')
            self.assertEqual(span.kind, 'client')
            self.assertEqual(span.attributes['db.system'], 'redis')
            self.assertEqual(span.attributes['db.operation'], 'GET')
            self.assertEqual(span.attributes['db.query.text'], 'GET ?')
            self.assertEqual(span.attributes['server.address'], 'redis.example.com')
            self.assertEqual(span.attributes['server.port'], 6379)
        finally:
            manager.enabled = original_enabled
            manager.host = original_host
            manager.port = original_port
            manager._redis_client = original_client

    async def test_redis_queue_push_emits_client_span(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        manager = RedisManager()
        original_enabled = manager.enabled
        original_host = manager.host
        original_port = manager.port
        original_client = manager._redis_client

        manager.enabled = True
        manager.host = 'redis.local'
        manager.port = 6380

        mock_client = AsyncMock()
        mock_client.rpush.return_value = 1
        manager._redis_client = mock_client

        queue = RedisQueue()

        try:
            await queue.push('{"class": "test"}', queue='default')

            span = next(s for s in spans if s.name == 'redis.rpush')
            self.assertEqual(span.kind, 'client')
            self.assertEqual(span.attributes['db.system'], 'redis')
            self.assertEqual(span.attributes['db.operation'], 'RPUSH')
            self.assertEqual(span.attributes['db.query.text'], 'RPUSH ? ?')
            self.assertEqual(span.attributes['server.address'], 'redis.local')
            self.assertEqual(span.attributes['server.port'], 6380)
        finally:
            manager.enabled = original_enabled
            manager.host = original_host
            manager.port = original_port
            manager._redis_client = original_client

    def test_redis_span_helpers_produce_correct_attrs_and_text(self) -> None:
        from routemq.redis_manager import _redis_span_attributes, _redis_command_text

        class FakeManager:
            host = 'redis.local'
            port = 6379

        attrs = _redis_span_attributes(FakeManager(), 'GET', 'GET ?')
        self.assertEqual(attrs['db.system'], 'redis')
        self.assertEqual(attrs['db.operation'], 'GET')
        self.assertEqual(attrs['db.query.text'], 'GET ?')
        self.assertEqual(attrs['server.address'], 'redis.local')
        self.assertEqual(attrs['server.port'], 6379)

        self.assertEqual(_redis_command_text('SET', 2), 'SET ? ?')
        self.assertEqual(_redis_command_text('PING'), 'PING')


class RateLimitSpanTests(ObservabilityTestCase):
    async def test_rate_limit_middleware_emits_span_with_all_attrs(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        middleware = RateLimitMiddleware(max_requests=10, window_seconds=60, strategy='sliding_window')

        async def next_handler(context: dict[str, Any]) -> dict[str, Any]:
            return {'ok': True}

        result = await middleware.handle({'topic': 'devices/1/status'}, next_handler)

        self.assertEqual(result, {'ok': True})

        span = next(s for s in spans if s.name == 'middleware.rate_limit')
        self.assertEqual(span.kind, 'internal')
        self.assertEqual(span.attributes['routemq.rate_limit.strategy'], 'sliding_window')
        self.assertEqual(span.attributes['routemq.rate_limit.max_requests'], 10)
        self.assertEqual(span.attributes['routemq.rate_limit.window_seconds'], 60)
        self.assertEqual(span.attributes['routemq.rate_limit.allowed'], True)
        self.assertIn('routemq.rate_limit.remaining', span.attributes)
        self.assertIn('routemq.rate_limit.reset_time', span.attributes)

    async def test_rate_limit_middleware_denied_request_records_allowed_false(self) -> None:
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        middleware = RateLimitMiddleware(max_requests=1, window_seconds=60, strategy='fixed_window')

        async def next_handler(context: dict[str, Any]) -> dict[str, Any]:
            return {'ok': True}

        await middleware.handle({'topic': 'devices/1/status'}, next_handler)
        result = await middleware.handle({'topic': 'devices/1/status'}, next_handler)

        self.assertEqual(result['error'], 'rate_limit_exceeded')

        denied_span = next(
            s
            for s in spans
            if s.name == 'middleware.rate_limit' and s.attributes.get('routemq.rate_limit.allowed') is False
        )
        self.assertEqual(denied_span.kind, 'internal')
        self.assertEqual(denied_span.attributes['routemq.rate_limit.allowed'], False)
        self.assertEqual(denied_span.attributes['routemq.rate_limit.remaining'], 0)


if __name__ == '__main__':
    unittest.main()
