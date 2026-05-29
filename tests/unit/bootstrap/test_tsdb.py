import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from routemq.observability import register_span_hook, register_trace_hook
from routemq.tsdb.clickhouse_driver import ClickHouseDriver
from routemq.tsdb.tsdb_driver import TSDBSchemaError
from routemq.tsdb.tsdb_manager import TSDBManager


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.result_rows = rows


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, list[tuple[Any, ...]], list[str]]] = []
        self.closed = False
        self.tables: set[str] = {'pump_telemetry'}
        self.columns: dict[str, list[str]] = {'pump_telemetry': ['ts', 'pump_id', 'flow']}
        self.fail_times = 0
        self._calls = 0

    async def command(self, sql: str, parameters: dict[str, Any] | None = None) -> int:
        table = (parameters or {}).get('table', '')
        return 1 if table in self.tables else 0

    async def query(self, sql: str, parameters: dict[str, Any] | None = None) -> _FakeResult:
        table = (parameters or {}).get('table', '')
        return _FakeResult([(name,) for name in self.columns.get(table, [])])

    async def insert(self, table: str, data: Any, column_names: list[str] | None = None) -> None:
        self._calls += 1
        if self._calls <= self.fail_times:
            raise RuntimeError('simulated insert failure')
        self.inserts.append((table, list(data), list(column_names or [])))

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self.closed = True


def _connected_driver(client: _FakeAsyncClient, **kwargs: Any) -> ClickHouseDriver:
    driver = ClickHouseDriver(
        host='localhost',
        port=8123,
        database='default',
        username='default',
        password='',
        **kwargs,
    )
    driver._client = client
    return driver


class ClickHouseDriverSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_schema_passes_for_matching_table(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])

    async def test_ensure_schema_fails_for_missing_table(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        with self.assertRaises(TSDBSchemaError):
            await driver.ensure_schema('missing_table', ['ts'])

    async def test_ensure_schema_fails_for_missing_column(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        with self.assertRaises(TSDBSchemaError):
            await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'nonexistent'])


class ClickHouseDriverFlushTests(unittest.IsolatedAsyncioTestCase):
    async def test_flush_inserts_ordered_row_tuples(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])
        await driver.write_points('pump_telemetry', [{'flow': 1.5, 'ts': 't0', 'pump_id': 'p1'}])
        await driver.flush()
        self.assertEqual(len(client.inserts), 1)
        table, rows, columns = client.inserts[0]
        self.assertEqual(table, 'pump_telemetry')
        self.assertEqual(columns, ['ts', 'pump_id', 'flow'])
        self.assertEqual(rows, [('t0', 'p1', 1.5)])

    async def test_flush_noop_when_empty(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.flush()
        self.assertEqual(client.inserts, [])

    async def test_flush_emits_client_span_with_otel_attributes(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])
        await driver.write_points('pump_telemetry', [{'ts': 't0', 'pump_id': 'p1', 'flow': 1.0}])

        captured: list[Any] = []
        unregister = register_span_hook(captured.append)
        try:
            await driver.flush()
        finally:
            unregister()

        flush_spans = [s for s in captured if s.name == 'tsdb.write.flush']
        self.assertEqual(len(flush_spans), 1)
        span = flush_spans[0]
        self.assertEqual(span.kind, 'client')
        self.assertEqual(span.attributes['db.system'], 'clickhouse')
        self.assertEqual(span.attributes['db.operation'], 'insert')
        self.assertEqual(span.attributes['db.collection.name'], 'pump_telemetry')
        self.assertEqual(span.attributes['db.operation.batch.size'], 1)
        self.assertEqual(span.attributes['tsdb.buffer.depth'], 1)


class ClickHouseDriverRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_insert_retries_then_succeeds(self) -> None:
        client = _FakeAsyncClient()
        client.fail_times = 2
        driver = _connected_driver(client, max_retries=3, retry_base_delay=0.0)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])
        await driver.write_points('pump_telemetry', [{'ts': 't0', 'pump_id': 'p1', 'flow': 1.0}])
        await driver.flush()
        self.assertEqual(len(client.inserts), 1)

    async def test_insert_drops_and_emits_error_after_exhaustion(self) -> None:
        client = _FakeAsyncClient()
        client.fail_times = 99
        driver = _connected_driver(client, max_retries=2, retry_base_delay=0.0)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])
        await driver.write_points('pump_telemetry', [{'ts': 't0', 'pump_id': 'p1', 'flow': 1.0}])

        events: list[str] = []
        unregister = register_trace_hook(lambda name, attrs: events.append(name))
        try:
            with self.assertRaises(RuntimeError):
                await driver.flush()
        finally:
            unregister()

        self.assertIn('tsdb.write.errors', events)
        self.assertEqual(client.inserts, [])


class TSDBManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        TSDBManager._instance = None

    def tearDown(self) -> None:
        TSDBManager._instance = None

    def _disabled_manager(self) -> TSDBManager:
        manager = object.__new__(TSDBManager)
        manager.enabled = False
        manager._driver = None
        manager._queue = None
        manager._flush_task = None
        return manager

    async def test_write_points_noop_when_disabled(self) -> None:
        manager = self._disabled_manager()
        await manager.write_points('pump_telemetry', [{'ts': 't0'}])
        self.assertFalse(manager.is_enabled())

    async def test_is_enabled_false_without_driver(self) -> None:
        manager = self._disabled_manager()
        manager.enabled = True
        self.assertFalse(manager.is_enabled())

    async def test_buffer_flushes_on_size_trigger(self) -> None:
        import asyncio

        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])

        manager = object.__new__(TSDBManager)
        manager.enabled = True
        manager._driver = driver
        manager._queue = asyncio.Queue(maxsize=100)
        manager._flush_task = None
        manager.batch_size = 3
        manager.flush_interval = 5.0

        for i in range(3):
            await manager._queue.put(('pump_telemetry', {'ts': f't{i}', 'pump_id': 'p1', 'flow': float(i)}))
        await manager._drain_once()

        self.assertEqual(len(client.inserts), 1)
        _table, rows, _columns = client.inserts[0]
        self.assertEqual(len(rows), 3)

    async def test_buffer_flushes_on_time_trigger(self) -> None:
        import asyncio

        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])

        manager = object.__new__(TSDBManager)
        manager.enabled = True
        manager._driver = driver
        manager._queue = asyncio.Queue(maxsize=100)
        manager._flush_task = None
        manager.batch_size = 10000
        manager.flush_interval = 0.05

        await manager._queue.put(('pump_telemetry', {'ts': 't0', 'pump_id': 'p1', 'flow': 1.0}))
        await manager._drain_once()

        self.assertEqual(len(client.inserts), 1)

    async def test_disconnect_drains_and_closes(self) -> None:
        import asyncio

        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])
        await driver.write_points('pump_telemetry', [{'ts': 't0', 'pump_id': 'p1', 'flow': 1.0}])

        manager = object.__new__(TSDBManager)
        manager.enabled = True
        manager.logger = __import__('logging').getLogger('test')
        manager._driver = driver
        manager._queue = asyncio.Queue(maxsize=100)
        manager._flush_task = None

        await manager.disconnect()
        self.assertEqual(len(client.inserts), 1)
        self.assertTrue(client.closed)


class TSDBDriverContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_abstract_methods_are_invokable_via_super(self) -> None:
        from routemq.tsdb.tsdb_driver import TSDBDriver

        class _Concrete(TSDBDriver):
            async def connect(self) -> None:
                await super().connect()

            async def close(self) -> None:
                await super().close()

            async def ensure_schema(self, measurement, columns) -> None:
                await super().ensure_schema(measurement, columns)

            async def write_points(self, measurement, rows) -> None:
                await super().write_points(measurement, rows)

            async def flush(self) -> None:
                await super().flush()

            async def health(self) -> bool:
                await super().health()
                return True

            @property
            def client(self):
                return super().client

        driver = _Concrete()
        await driver.connect()
        await driver.close()
        await driver.ensure_schema('m', ['c'])
        await driver.write_points('m', [{'c': 1}])
        await driver.flush()
        self.assertTrue(await driver.health())
        self.assertIsNone(driver.client)


class ClickHouseDriverUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_builds_async_client_with_settings(self) -> None:
        client = _FakeAsyncClient()
        get_async = AsyncMock(return_value=client)
        driver = ClickHouseDriver(host='h', port=8123, database='db', username='u', password='p', async_insert=True)
        with patch('routemq.tsdb.clickhouse_driver.clickhouse_connect.get_async_client', new=get_async):
            await driver.connect()
        self.assertIs(driver._client, client)
        _args, kwargs = get_async.call_args
        self.assertEqual(kwargs['settings']['async_insert'], 1)
        self.assertEqual(kwargs['settings']['wait_for_async_insert'], 1)

    async def test_close_clears_client(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.close()
        self.assertTrue(client.closed)
        self.assertIsNone(driver._client)

    async def test_write_points_ignores_empty_rows(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.write_points('pump_telemetry', [])
        self.assertEqual(driver.buffered_count(), 0)

    async def test_buffered_count_tracks_pending_rows(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.write_points('pump_telemetry', [{'ts': 't0'}, {'ts': 't1'}])
        self.assertEqual(driver.buffered_count(), 2)

    async def test_health_false_without_client(self) -> None:
        driver = ClickHouseDriver(host='h', port=8123, database='db', username='u', password='p')
        self.assertFalse(await driver.health())

    async def test_health_true_when_connected(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        self.assertTrue(await driver.health())

    def test_client_property_raises_when_not_connected(self) -> None:
        driver = ClickHouseDriver(host='h', port=8123, database='db', username='u', password='p')
        with self.assertRaises(RuntimeError):
            _ = driver.client

    def test_client_property_returns_connected_client(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        self.assertIs(driver.client, client)


class TSDBManagerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        TSDBManager._instance = None

    def tearDown(self) -> None:
        TSDBManager._instance = None

    def _make_manager(self, env: dict[str, str]) -> TSDBManager:
        TSDBManager._instance = None
        with patch.dict('os.environ', env, clear=False):
            return TSDBManager()

    def test_init_reads_env_when_enabled(self) -> None:
        manager = self._make_manager(
            {
                'ENABLE_TSDB': 'true',
                'TSDB_HOST': 'ch-host',
                'TSDB_PORT': '9001',
                'TSDB_DATABASE': 'metrics',
                'TSDB_USER': 'admin',
                'TSDB_PASSWORD': 'secret',
                'TSDB_BATCH_SIZE': '500',
                'TSDB_FLUSH_INTERVAL': '2.5',
                'TSDB_BUFFER_MAXSIZE': '1000',
                'TSDB_ASYNC_INSERT': 'false',
            }
        )
        self.assertTrue(manager.enabled)
        self.assertEqual(manager.host, 'ch-host')
        self.assertEqual(manager.port, 9001)
        self.assertEqual(manager.database, 'metrics')
        self.assertEqual(manager.username, 'admin')
        self.assertEqual(manager.password, 'secret')
        self.assertEqual(manager.batch_size, 500)
        self.assertEqual(manager.flush_interval, 2.5)
        self.assertEqual(manager.buffer_maxsize, 1000)
        self.assertFalse(manager.async_insert)

    def test_init_defaults_when_disabled(self) -> None:
        manager = self._make_manager({'ENABLE_TSDB': 'false'})
        self.assertFalse(manager.enabled)
        self.assertEqual(manager.host, 'localhost')
        self.assertEqual(manager.port, 8123)
        self.assertIsNone(manager.get_client())

    async def test_initialize_returns_false_when_disabled(self) -> None:
        manager = self._make_manager({'ENABLE_TSDB': 'false'})
        self.assertFalse(await manager.initialize())

    async def test_initialize_success_starts_flush_task(self) -> None:
        manager = self._make_manager({'ENABLE_TSDB': 'true'})
        with patch.object(ClickHouseDriver, 'connect', new=AsyncMock()):
            ok = await manager.initialize()
        self.assertTrue(ok)
        self.assertTrue(manager.is_enabled())
        self.assertIsNotNone(manager._flush_task)
        await manager.disconnect()
        self.assertFalse(manager.is_enabled())

    async def test_initialize_failure_disables_manager(self) -> None:
        manager = self._make_manager({'ENABLE_TSDB': 'true'})
        with patch.object(ClickHouseDriver, 'connect', new=AsyncMock(side_effect=RuntimeError('no server'))):
            ok = await manager.initialize()
        self.assertFalse(ok)
        self.assertFalse(manager.enabled)
        self.assertIsNone(manager._driver)

    async def test_ensure_schema_noop_without_driver(self) -> None:
        manager = self._make_manager({'ENABLE_TSDB': 'false'})
        await manager.ensure_schema('pump_telemetry', ['ts'])

    async def test_flush_loop_drains_enqueued_rows(self) -> None:
        client = _FakeAsyncClient()
        driver = _connected_driver(client)
        await driver.ensure_schema('pump_telemetry', ['ts', 'pump_id', 'flow'])

        manager = self._make_manager({'ENABLE_TSDB': 'true'})
        manager._driver = driver
        manager._queue = asyncio.Queue(maxsize=100)
        manager.batch_size = 10000
        manager.flush_interval = 0.02
        manager._flush_task = asyncio.create_task(manager._flush_loop())

        await manager.write_points('pump_telemetry', [{'ts': 't0', 'pump_id': 'p1', 'flow': 1.0}])
        for _ in range(50):
            await asyncio.sleep(0.01)
            if client.inserts:
                break

        manager._flush_task.cancel()
        try:
            await manager._flush_task
        except asyncio.CancelledError:
            pass

        self.assertEqual(len(client.inserts), 1)

    async def test_wait_for_first_returns_none_on_timeout(self) -> None:
        manager = self._make_manager({'ENABLE_TSDB': 'true'})
        manager._queue = asyncio.Queue(maxsize=10)
        manager.flush_interval = 0.01
        self.assertIsNone(await manager._wait_for_first())


if __name__ == '__main__':
    unittest.main()
