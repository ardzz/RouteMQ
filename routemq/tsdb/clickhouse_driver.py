"""ClickHouse TSDB driver: validate-only schema, batched async insert, retry, CLIENT spans."""

import asyncio
import logging
import random
from collections.abc import Mapping, Sequence
from typing import Any

from routemq.observability import lifecycle, start_span
from routemq.tsdb.tsdb_driver import TSDBDriver, TSDBSchemaError

try:
    import clickhouse_connect

    CLICKHOUSE_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency fallback
    # Audit Accept: ClickHouse is optional; manager logs if enabled without the package.
    CLICKHOUSE_AVAILABLE = False
    clickhouse_connect = None  # type: ignore[assignment]


class ClickHouseDriver(TSDBDriver):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        async_insert: bool = True,
        max_retries: int = 3,
        retry_base_delay: float = 0.1,
    ) -> None:
        self.logger = logging.getLogger('RouteMQ.TSDBDriver')
        self._host = host
        self._port = port
        self._database = database
        self._username = username
        self._password = password
        self._async_insert = async_insert
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._client: Any = None
        self._buffers: dict[str, list[Mapping[str, Any]]] = {}
        self._columns: dict[str, tuple[str, ...]] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if not CLICKHOUSE_AVAILABLE or clickhouse_connect is None:  # pragma: no cover - guarded upstream
            raise RuntimeError('clickhouse-connect is not installed. Install with: uv add "routemq[clickhouse]"')
        settings = {
            'async_insert': 1 if self._async_insert else 0,
            'wait_for_async_insert': 1,
        }
        self._client = await clickhouse_connect.get_async_client(
            host=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            database=self._database,
            settings=settings,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def ensure_schema(self, measurement: str, columns: Sequence[str]) -> None:
        if self._client is None:  # pragma: no cover - guarded by manager lifecycle
            raise RuntimeError('ClickHouse driver is not connected')

        exists = await self._client.command(
            'SELECT count() FROM system.tables WHERE database = {db:String} AND name = {table:String}',
            parameters={'db': self._database, 'table': measurement},
        )
        if not exists:
            raise TSDBSchemaError(
                f"Table '{self._database}.{measurement}' does not exist. "
                f'The application owns DDL; create it before enabling TSDB writes.'
            )

        result = await self._client.query(
            'SELECT name FROM system.columns WHERE database = {db:String} AND table = {table:String}',
            parameters={'db': self._database, 'table': measurement},
        )
        actual = {row[0] for row in result.result_rows}
        missing = [column for column in columns if column not in actual]
        if missing:
            raise TSDBSchemaError(
                f"Table '{self._database}.{measurement}' is missing expected columns: {missing}. "
                f'Present columns: {sorted(actual)}.'
            )
        self._columns[measurement] = tuple(columns)

    async def write_points(self, measurement: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            return
        async with self._lock:
            self._buffers.setdefault(measurement, []).extend(rows)

    def buffered_count(self) -> int:
        return sum(len(rows) for rows in self._buffers.values())

    async def flush(self) -> None:
        async with self._lock:
            pending = {measurement: rows for measurement, rows in self._buffers.items() if rows}
            self._buffers = {}
        for measurement, rows in pending.items():
            await self._flush_measurement(measurement, rows)

    async def _flush_measurement(self, measurement: str, rows: list[Mapping[str, Any]]) -> None:
        column_names = self._columns.get(measurement) or tuple(rows[0].keys())
        data = [tuple(row.get(column) for column in column_names) for row in rows]
        span_attributes = {
            'db.system': 'clickhouse',
            'db.operation': 'insert',
            'db.collection.name': measurement,
            'server.address': f'{self._host}:{self._port}',
            'db.operation.batch.size': len(data),
            'tsdb.buffer.depth': len(data),
        }
        with start_span('tsdb.write.flush', span_attributes, kind='client'):
            await self._insert_with_retry(measurement, data, column_names)

    async def _insert_with_retry(
        self,
        measurement: str,
        data: list[tuple[Any, ...]],
        column_names: tuple[str, ...],
    ) -> None:
        attempt = 0
        while True:
            try:
                await self._client.insert(measurement, data, column_names=list(column_names))
                lifecycle('tsdb.write.batches', {'db.collection.name': measurement})
                return
            except Exception as exc:
                attempt += 1
                if attempt > self._max_retries:
                    lifecycle(
                        'tsdb.write.errors',
                        {'db.collection.name': measurement, 'error': exc.__class__.__name__},
                    )
                    self.logger.error(
                        f"Dropping {len(data)} rows for '{measurement}' after {self._max_retries} retries: {exc}",
                        exc_info=True,
                        extra={'measurement': measurement, 'batch_size': len(data)},
                    )
                    raise
                delay = self._retry_base_delay * (4 ** (attempt - 1))
                delay += random.uniform(0, delay)  # nosec B311 - retry jitter, not security-sensitive
                self.logger.warning(
                    f"ClickHouse insert for '{measurement}' failed (attempt {attempt}/{self._max_retries}); "
                    f'retrying in {delay:.2f}s: {exc}'
                )
                await asyncio.sleep(delay)

    async def health(self) -> bool:
        if self._client is None:
            return False
        return bool(await self._client.ping())

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError('ClickHouse driver is not connected')
        return self._client
