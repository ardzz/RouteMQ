from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from routemq.telemetry.adapter import (
    SchemaValidationIssue,
    SchemaValidationResult,
    TelemetryAdapter,
    TelemetryHealthStatus,
    WriteFailure,
    WriteResult,
)
from routemq.telemetry.types import TelemetryPoint
from routemq.tsdb.clickhouse_driver import CLICKHOUSE_AVAILABLE, clickhouse_connect
from routemq.tsdb.telemetry_mapping import (
    clickhouse_rows,
    influx_line_protocol,
    influx_lines,
    iotdb_records,
    timescale_rows,
)


_SAFE_TABLE_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _ensure_safe_table_name(table: str) -> str:
    # Table identifiers cannot be bound parameters, so restrict them to an allowlist.
    if not _SAFE_TABLE_IDENTIFIER.match(table):
        raise ValueError(f'Unsafe telemetry table identifier: {table!r}')
    return table


CLICKHOUSE_TELEMETRY_COLUMNS = (
    'observed_at',
    'ingested_at',
    'device_id',
    'measurement',
    'value_float',
    'value_int',
    'value_string',
    'value_bool',
    'unit',
    'quality',
    'tags',
    'attributes',
    'metadata',
)


class ClickHouseTelemetryAdapter(TelemetryAdapter):
    def __init__(self, url: str, *, table: str = 'telemetry_observations', async_insert: bool = True) -> None:
        self.url = url
        self.table = table
        self.async_insert = async_insert
        self._client: Any = None

    async def connect(self) -> None:
        if not CLICKHOUSE_AVAILABLE or clickhouse_connect is None:
            raise RuntimeError('clickhouse-connect is not installed. Install with: uv add "routemq[clickhouse]"')
        parsed = urlparse(self.url)
        settings = {'async_insert': 1 if self.async_insert else 0, 'wait_for_async_insert': 1}
        self._client = await clickhouse_connect.get_async_client(
            host=parsed.hostname or 'localhost',
            port=parsed.port or 8123,
            username=parsed.username or 'default',
            password=parsed.password or '',
            database=parsed.path.strip('/') or 'default',
            settings=settings,
        )

    async def write_many(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        pending = list(points)
        if not pending:
            return WriteResult()
        if self._client is None:
            await self.connect()
        rows = clickhouse_rows(pending)
        data = [tuple(row.get(column) for column in CLICKHOUSE_TELEMETRY_COLUMNS) for row in rows]
        try:
            await self._client.insert(self.table, data, column_names=list(CLICKHOUSE_TELEMETRY_COLUMNS))
        except Exception as exc:
            failures = tuple(
                WriteFailure(index=index, point=point, error=str(exc)) for index, point in enumerate(pending)
            )
            return WriteResult(accepted=len(pending), written=0, failures=failures)
        return WriteResult(accepted=len(pending), written=len(pending))

    async def validate_schema(self) -> SchemaValidationResult:
        if self._client is None:
            await self.connect()
        parsed = urlparse(self.url)
        database = parsed.path.strip('/') or 'default'
        exists = await self._client.command(
            'SELECT count() FROM system.tables WHERE database = {db:String} AND name = {table:String}',
            parameters={'db': database, 'table': self.table},
        )
        if not exists:
            return SchemaValidationResult(
                ok=False,
                issues=(
                    SchemaValidationIssue(
                        backend='clickhouse', object_name=self.table, message='telemetry table is missing'
                    ),
                ),
            )
        result = await self._client.query(
            'SELECT name FROM system.columns WHERE database = {db:String} AND table = {table:String}',
            parameters={'db': database, 'table': self.table},
        )
        actual = {row[0] for row in result.result_rows}
        missing = [column for column in CLICKHOUSE_TELEMETRY_COLUMNS if column not in actual]
        issues = tuple(
            SchemaValidationIssue(backend='clickhouse', object_name=self.table, message=f'missing column: {column}')
            for column in missing
        )
        return SchemaValidationResult(ok=not issues, issues=issues)

    async def health_check(self) -> TelemetryHealthStatus:
        if self._client is None:
            return TelemetryHealthStatus(ok=False, backend='clickhouse', message='not connected')
        return TelemetryHealthStatus(ok=bool(await self._client.ping()), backend='clickhouse')

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


class TimescaleTelemetryAdapter(TelemetryAdapter):
    def __init__(self, url: str, *, table: str = 'telemetry_observations') -> None:
        self.url = url
        self.table = _ensure_safe_table_name(table)
        self._engine: Any = None

    async def connect(self) -> None:
        self._engine = create_async_engine(self.url)

    async def write_many(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        pending = list(points)
        if not pending:
            return WriteResult()
        if self._engine is None:
            await self.connect()
        rows = timescale_rows(pending)
        statement = text(
            f'INSERT INTO {self.table} (observed_at, ingested_at, device_id, measurement, value_double, value_text, '  # nosec B608 - table validated by _ensure_safe_table_name
            'value_bool, unit, quality, tags, attributes, metadata) VALUES (:observed_at, :ingested_at, :device_id, '
            ':measurement, :value_double, :value_text, :value_bool, :unit, :quality, :tags, :attributes, :metadata)'
        )
        try:
            async with self._engine.begin() as connection:
                await connection.execute(statement, rows)
        except Exception as exc:
            failures = tuple(
                WriteFailure(index=index, point=point, error=str(exc)) for index, point in enumerate(pending)
            )
            return WriteResult(accepted=len(pending), written=0, failures=failures)
        return WriteResult(accepted=len(pending), written=len(pending))

    async def validate_schema(self) -> SchemaValidationResult:
        return SchemaValidationResult()

    async def health_check(self) -> TelemetryHealthStatus:
        return TelemetryHealthStatus(ok=self._engine is not None, backend='timescaledb')

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None


class InfluxTelemetryAdapter(TelemetryAdapter):
    def __init__(self, url: str) -> None:
        self.url = url

    async def write_many(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        pending = list(points)
        if not pending:
            return WriteResult()
        lines = '\n'.join(influx_line_protocol(line) for line in influx_lines(pending))
        try:
            await asyncio.to_thread(_post_bytes, self.url, lines.encode())
        except Exception as exc:
            failures = tuple(
                WriteFailure(index=index, point=point, error=str(exc)) for index, point in enumerate(pending)
            )
            return WriteResult(accepted=len(pending), written=0, failures=failures)
        return WriteResult(accepted=len(pending), written=len(pending))

    async def validate_schema(self) -> SchemaValidationResult:
        return SchemaValidationResult()

    async def health_check(self) -> TelemetryHealthStatus:
        return TelemetryHealthStatus(ok=True, backend='influxdb')

    async def close(self) -> None:
        return None


class IoTDBTelemetryAdapter(TelemetryAdapter):
    def __init__(self, url: str) -> None:
        self.url = url

    async def write_many(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        pending = list(points)
        if not pending:
            return WriteResult()
        payload = [asdict(record) for record in iotdb_records(pending)]
        try:
            await asyncio.to_thread(_post_bytes, self.url, json.dumps(payload, default=str).encode())
        except Exception as exc:
            failures = tuple(
                WriteFailure(index=index, point=point, error=str(exc)) for index, point in enumerate(pending)
            )
            return WriteResult(accepted=len(pending), written=0, failures=failures)
        return WriteResult(accepted=len(pending), written=len(pending))

    async def validate_schema(self) -> SchemaValidationResult:
        return SchemaValidationResult()

    async def health_check(self) -> TelemetryHealthStatus:
        return TelemetryHealthStatus(ok=True, backend='iotdb')

    async def close(self) -> None:
        return None


def adapter_from_settings(connection: str, url: str, *, async_insert: bool = True) -> TelemetryAdapter:
    if connection == 'timescaledb':
        return TimescaleTelemetryAdapter(url)
    if connection == 'influxdb':
        return InfluxTelemetryAdapter(_influx_write_url(url))
    if connection == 'iotdb':
        return IoTDBTelemetryAdapter(url)
    return ClickHouseTelemetryAdapter(url, async_insert=async_insert)


def _influx_write_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if '/api/v2/write' in parsed.path:
        return url
    bucket = query.get('bucket', ['telemetry'])[0]
    org = query.get('org', ['routemq'])[0]
    base = f'{parsed.scheme}://{parsed.netloc}'
    return f'{base}/api/v2/write?bucket={bucket}&org={org}&precision=ns'


def _post_bytes(url: str, body: bytes) -> None:
    request = Request(url, data=body, method='POST')
    request.add_header('Content-Type', 'application/json' if body.startswith(b'[') else 'text/plain')
    with urlopen(request, timeout=10) as response:  # nosec B310 - destination is explicit telemetry config
        response.read()
