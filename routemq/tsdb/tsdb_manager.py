"""TSDBManager singleton: ENABLE_TSDB gating, bounded buffer, size/time-triggered flush loop."""

import asyncio
import logging
import os
from collections.abc import Mapping, Sequence
from typing import Any, Optional

from routemq.tsdb.clickhouse_driver import CLICKHOUSE_AVAILABLE, ClickHouseDriver
from routemq.tsdb.tsdb_driver import TSDBDriver


class TSDBManager:
    _instance: Optional['TSDBManager'] = None

    def __new__(cls) -> 'TSDBManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return

        self.logger = logging.getLogger('RouteMQ.TSDBManager')
        self.enabled = os.getenv('ENABLE_TSDB', 'false').lower() == 'true'
        self.host = os.getenv('TSDB_HOST', 'localhost')
        self.port = int(os.getenv('TSDB_PORT', '8123'))
        self.database = os.getenv('TSDB_DATABASE', 'default')
        self.username = os.getenv('TSDB_USER', 'default')
        self.password = os.getenv('TSDB_PASSWORD', '')
        self.batch_size = int(os.getenv('TSDB_BATCH_SIZE', '10000'))
        self.flush_interval = float(os.getenv('TSDB_FLUSH_INTERVAL', '1.0'))
        self.buffer_maxsize = int(os.getenv('TSDB_BUFFER_MAXSIZE', '50000'))
        self.async_insert = os.getenv('TSDB_ASYNC_INSERT', 'true').lower() == 'true'

        self._driver: TSDBDriver | None = None
        self._queue: asyncio.Queue[tuple[str, Mapping[str, Any]]] | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._initialized = True

        if self.enabled and not CLICKHOUSE_AVAILABLE:  # pragma: no cover - requires uninstalled clickhouse-connect
            self.logger.error(
                'TSDB is enabled but clickhouse-connect is not installed. Install with: uv add "routemq[clickhouse]"'
            )
            self.enabled = False

        if self.enabled:
            self.logger.info(f'TSDB integration enabled - ClickHouse at {self.host}:{self.port}')
        else:
            self.logger.info('TSDB integration is disabled')

    async def initialize(self) -> bool:
        if not self.enabled:
            return False
        try:
            self._driver = ClickHouseDriver(
                host=self.host,
                port=self.port,
                database=self.database,
                username=self.username,
                password=self.password,
                async_insert=self.async_insert,
            )
            await self._driver.connect()
            self._queue = asyncio.Queue(maxsize=self.buffer_maxsize)
            self._flush_task = asyncio.create_task(self._flush_loop())
            self.logger.info('Successfully connected to ClickHouse')
            return True
        except Exception as e:
            self.logger.warning(
                f'Failed to connect to ClickHouse at {self.host}:{self.port}: {e}',
                exc_info=True,
                extra={'tsdb_host': self.host, 'tsdb_port': self.port},
            )
            self.enabled = False
            self._driver = None
            return False

    async def ensure_schema(self, measurement: str, columns: Sequence[str]) -> None:
        if self._driver is None:
            return
        await self._driver.ensure_schema(measurement, columns)

    async def write_points(self, measurement: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if not self.is_enabled() or self._queue is None:
            return
        for row in rows:
            await self._queue.put((measurement, row))

    async def _flush_loop(self) -> None:
        assert self._queue is not None
        assert self._driver is not None
        while True:
            try:
                await self._drain_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Audit Accept: per-batch insert failures are handled/logged inside the driver retry path.
                self.logger.debug('Flush cycle raised; continuing flush loop', exc_info=True)

    async def _drain_once(self) -> None:
        assert self._queue is not None
        assert self._driver is not None
        first = await self._wait_for_first()
        if first is None:
            return
        batch = [first]
        while len(batch) < self.batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for measurement, row in batch:
            await self._driver.write_points(measurement, [row])
        await self._driver.flush()

    async def _wait_for_first(self) -> tuple[str, Mapping[str, Any]] | None:
        assert self._queue is not None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=self.flush_interval)
        except asyncio.TimeoutError:
            return None

    async def disconnect(self) -> None:
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        if self._driver is not None:
            try:
                await self._driver.flush()
            finally:
                await self._driver.close()
                self._driver = None
        self.logger.info('TSDB connections closed')

    def get_client(self) -> Any:
        if self._driver is None:
            return None
        try:
            return self._driver.client
        except RuntimeError:
            return None

    def is_enabled(self) -> bool:
        return self.enabled and self._driver is not None


tsdb_manager = TSDBManager()
