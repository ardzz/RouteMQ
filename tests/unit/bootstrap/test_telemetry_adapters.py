import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.telemetry import TelemetryPoint
from routemq.tsdb.telemetry_adapters import (
    CLICKHOUSE_TELEMETRY_COLUMNS,
    ClickHouseTelemetryAdapter,
    InfluxTelemetryAdapter,
    IoTDBTelemetryAdapter,
    TimescaleTelemetryAdapter,
    adapter_from_settings,
)


class _FakeClickHouseClient:
    def __init__(self) -> None:
        self.inserts: list[Any] = []
        self.closed = False
        self.fail = False

    async def insert(self, table, data, column_names=None):
        if self.fail:
            raise RuntimeError('insert failed')
        self.inserts.append((table, data, column_names))

    async def command(self, sql, parameters=None):
        return 1

    async def query(self, sql, parameters=None):
        result = MagicMock()
        result.result_rows = [(column,) for column in CLICKHOUSE_TELEMETRY_COLUMNS]
        return result

    async def ping(self):
        return True

    async def close(self):
        self.closed = True


def _point() -> TelemetryPoint:
    return TelemetryPoint(device_id='pump-7', observed_at='2026-05-30T10:15:30Z', measurements={'temperature': 31.2})


class ClickHouseTelemetryAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_many_inserts_narrow_rows(self) -> None:
        client = _FakeClickHouseClient()
        adapter = ClickHouseTelemetryAdapter('http://default:@localhost:8123/iot')
        adapter._client = client

        result = await adapter.write_many([_point()])

        self.assertTrue(result.success)
        table, data, columns = client.inserts[0]
        self.assertEqual(table, 'telemetry_observations')
        self.assertEqual(columns, list(CLICKHOUSE_TELEMETRY_COLUMNS))
        self.assertEqual(data[0][columns.index('device_id')], 'pump-7')

    async def test_write_many_reports_partial_batch_failure(self) -> None:
        client = _FakeClickHouseClient()
        client.fail = True
        adapter = ClickHouseTelemetryAdapter('http://localhost:8123/iot')
        adapter._client = client

        result = await adapter.write_many([_point()])

        self.assertFalse(result.success)
        self.assertEqual(len(result.failures), 1)

    async def test_write_many_connects_when_needed_and_handles_empty(self) -> None:
        adapter = ClickHouseTelemetryAdapter('http://localhost:8123/iot')
        with patch.object(adapter, 'connect', new=AsyncMock()) as connect:
            empty = await adapter.write_many([])
        connect.assert_not_called()
        self.assertEqual(empty.accepted, 0)

        client = _FakeClickHouseClient()
        adapter._client = None
        with patch.object(adapter, 'connect', new=AsyncMock(side_effect=lambda: setattr(adapter, '_client', client))):
            result = await adapter.write_many([_point()])
        self.assertTrue(result.success)

    async def test_validate_schema_reports_ok_for_expected_columns(self) -> None:
        adapter = ClickHouseTelemetryAdapter('http://localhost:8123/iot')
        adapter._client = _FakeClickHouseClient()

        result = await adapter.validate_schema()

        self.assertTrue(result.ok)

    async def test_validate_schema_reports_missing_table_and_columns(self) -> None:
        missing_table = _FakeClickHouseClient()
        missing_table.command = AsyncMock(return_value=0)
        adapter = ClickHouseTelemetryAdapter('http://localhost:8123/iot')
        adapter._client = missing_table

        self.assertFalse((await adapter.validate_schema()).ok)

        missing_columns = _FakeClickHouseClient()
        result = MagicMock()
        result.result_rows = [('observed_at',)]
        missing_columns.query = AsyncMock(return_value=result)
        adapter._client = missing_columns

        validation = await adapter.validate_schema()
        self.assertFalse(validation.ok)
        self.assertGreater(len(validation.issues), 1)

    async def test_health_false_when_not_connected_and_close_noop(self) -> None:
        adapter = ClickHouseTelemetryAdapter('http://localhost:8123/iot')

        self.assertFalse((await adapter.health_check()).ok)
        await adapter.close()

    async def test_health_and_close_use_client(self) -> None:
        client = _FakeClickHouseClient()
        adapter = ClickHouseTelemetryAdapter('http://localhost:8123/iot')
        adapter._client = client

        self.assertTrue((await adapter.health_check()).ok)
        await adapter.close()
        self.assertTrue(client.closed)

    async def test_connect_uses_clickhouse_url_parts(self) -> None:
        client = _FakeClickHouseClient()
        get_async = AsyncMock(return_value=client)
        adapter = ClickHouseTelemetryAdapter('http://user:pass@clickhouse:9000/iot')
        with patch('routemq.tsdb.telemetry_adapters.clickhouse_connect.get_async_client', new=get_async):
            await adapter.connect()

        self.assertIs(adapter._client, client)
        self.assertEqual(get_async.call_args.kwargs['host'], 'clickhouse')
        self.assertEqual(get_async.call_args.kwargs['port'], 9000)
        self.assertEqual(get_async.call_args.kwargs['database'], 'iot')


class OtherTelemetryAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_timescale_adapter_executes_insert(self) -> None:
        connection = MagicMock()
        connection.execute = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=connection)
        context.__aexit__ = AsyncMock(return_value=None)
        engine = MagicMock()
        engine.begin.return_value = context
        adapter = TimescaleTelemetryAdapter('postgresql+asyncpg://u:p@db/app')
        adapter._engine = engine

        result = await adapter.write_many([_point()])

        self.assertTrue(result.success)
        connection.execute.assert_awaited_once()

    async def test_timescale_adapter_connects_handles_empty_failure_and_close(self) -> None:
        adapter = TimescaleTelemetryAdapter('postgresql+asyncpg://u:p@db/app')
        empty = await adapter.write_many([])
        self.assertEqual(empty.accepted, 0)
        self.assertFalse((await adapter.health_check()).ok)

        engine = MagicMock()
        adapter._engine = None
        with patch('routemq.tsdb.telemetry_adapters.create_async_engine', return_value=engine):
            await adapter.connect()
        self.assertIs(adapter._engine, engine)

        bad_engine = MagicMock()
        bad_context = MagicMock()
        bad_context.__aenter__ = AsyncMock(side_effect=RuntimeError('db down'))
        bad_context.__aexit__ = AsyncMock(return_value=None)
        bad_engine.begin.return_value = bad_context
        bad_engine.dispose = AsyncMock()
        adapter._engine = bad_engine
        result = await adapter.write_many([_point()])
        self.assertEqual(len(result.failures), 1)
        self.assertTrue((await adapter.validate_schema()).ok)
        self.assertTrue((await adapter.health_check()).ok)
        await adapter.close()
        bad_engine.dispose.assert_awaited_once()

    async def test_influx_adapter_posts_line_protocol(self) -> None:
        adapter = InfluxTelemetryAdapter('http://influx/write')
        with patch('routemq.tsdb.telemetry_adapters._post_bytes') as post_bytes:
            result = await adapter.write_many([_point()])

        self.assertTrue(result.success)
        self.assertIn(b'temperature=31.2', post_bytes.call_args.args[1])

    async def test_influx_adapter_handles_empty_failure_health_close(self) -> None:
        adapter = InfluxTelemetryAdapter('http://influx/write')
        empty = await adapter.write_many([])
        self.assertEqual(empty.accepted, 0)
        with patch('routemq.tsdb.telemetry_adapters._post_bytes', side_effect=RuntimeError('http down')):
            result = await adapter.write_many([_point()])
        self.assertEqual(len(result.failures), 1)
        self.assertTrue((await adapter.validate_schema()).ok)
        self.assertTrue((await adapter.health_check()).ok)
        await adapter.close()

    async def test_iotdb_adapter_posts_json_records(self) -> None:
        adapter = IoTDBTelemetryAdapter('http://iotdb/write')
        with patch('routemq.tsdb.telemetry_adapters._post_bytes') as post_bytes:
            result = await adapter.write_many([_point()])

        self.assertTrue(result.success)
        self.assertIn(b'pump_7', post_bytes.call_args.args[1])

    async def test_iotdb_adapter_handles_empty_failure_health_close(self) -> None:
        adapter = IoTDBTelemetryAdapter('http://iotdb/write')
        empty = await adapter.write_many([])
        self.assertEqual(empty.accepted, 0)
        with patch('routemq.tsdb.telemetry_adapters._post_bytes', side_effect=RuntimeError('http down')):
            result = await adapter.write_many([_point()])
        self.assertEqual(len(result.failures), 1)
        self.assertTrue((await adapter.validate_schema()).ok)
        self.assertTrue((await adapter.health_check()).ok)
        await adapter.close()

    def test_factory_selects_adapter(self) -> None:
        self.assertIsInstance(adapter_from_settings('timescaledb', 'postgresql+asyncpg://u:p@db/app'), TimescaleTelemetryAdapter)
        self.assertIsInstance(adapter_from_settings('influxdb', 'http://influx:8086?bucket=iot'), InfluxTelemetryAdapter)
        self.assertIsInstance(adapter_from_settings('iotdb', 'http://iotdb/write'), IoTDBTelemetryAdapter)
        self.assertIsInstance(adapter_from_settings('clickhouse', 'http://clickhouse:8123/iot'), ClickHouseTelemetryAdapter)

    def test_factory_passes_async_insert_to_clickhouse_adapter(self) -> None:
        adapter = adapter_from_settings('clickhouse', 'http://clickhouse:8123/iot', async_insert=False)

        self.assertIsInstance(adapter, ClickHouseTelemetryAdapter)
        self.assertFalse(cast(ClickHouseTelemetryAdapter, adapter).async_insert)

    def test_factory_preserves_existing_influx_write_url(self) -> None:
        adapter = adapter_from_settings('influxdb', 'http://influx:8086/api/v2/write?bucket=iot&org=o')

        self.assertEqual(cast(InfluxTelemetryAdapter, adapter).url, 'http://influx:8086/api/v2/write?bucket=iot&org=o')


if __name__ == '__main__':
    unittest.main()
