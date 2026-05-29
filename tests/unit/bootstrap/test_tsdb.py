import unittest
from typing import Any

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


if __name__ == '__main__':
    unittest.main()
