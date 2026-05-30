from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence

from routemq.observability import lifecycle, start_span
from routemq.settings import TelemetrySettings
from routemq.telemetry.adapter import NoopTelemetryAdapter, TelemetryAdapter, TelemetryHealthStatus, WriteFailure, WriteResult
from routemq.telemetry.types import TelemetryPoint


class TelemetryQueueFull(RuntimeError):
    """Raised when telemetry queue-full strategy is ``fail``."""


class TelemetryManager:
    def __init__(self, *, adapter: TelemetryAdapter | None = None, settings: TelemetrySettings | None = None) -> None:
        self.settings = settings or TelemetrySettings(enabled=False)
        self.adapter: TelemetryAdapter = adapter or NoopTelemetryAdapter()
        self._queue: asyncio.Queue[TelemetryPoint] = asyncio.Queue(maxsize=self.settings.queue_max_size)
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self, *, adapter: TelemetryAdapter | None = None, settings: TelemetrySettings | None = None) -> bool:
        if settings is not None:
            self.settings = settings
            self._queue = asyncio.Queue(maxsize=self.settings.queue_max_size)
        if adapter is not None:
            self.adapter = adapter
        self._closed = False
        if not self.settings.enabled:
            return False
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())
        return True

    async def write(self, point: TelemetryPoint) -> WriteResult:
        return await self.write_many([point])

    async def write_many(self, points: Iterable[TelemetryPoint]) -> WriteResult:
        if self._closed:
            raise RuntimeError('telemetry manager is closed')
        accepted = 0
        dropped = 0
        for point in points:
            outcome = await self._enqueue(point)
            if outcome == 'accepted':
                accepted += 1
            else:
                dropped += 1
        if accepted:
            lifecycle('telemetry.points.accepted', {'count': accepted})
        if dropped:
            lifecycle('telemetry.points.dropped', {'count': dropped, 'strategy': self.settings.queue_full_strategy})
        lifecycle('telemetry.queue.depth', {'depth': self._queue.qsize()})
        flushed = WriteResult()
        if self._queue.qsize() >= self.settings.batch_size:
            flushed = await self._flush_ready_batches()
        return WriteResult(accepted=accepted, written=flushed.written, failures=flushed.failures)

    async def flush(self) -> WriteResult:
        batch = self._drain_batch(self.settings.batch_size)
        if not batch:
            return WriteResult()
        with start_span('telemetry.flush', {'telemetry.batch.size': len(batch)}, kind='client'):
            result = await self._write_with_retries(batch)
        lifecycle('telemetry.write.batches', {'count': 1})
        lifecycle('telemetry.points.flushed', {'count': result.written})
        if result.failures:
            lifecycle('telemetry.write.errors', {'count': len(result.failures)})
        lifecycle('telemetry.queue.depth', {'depth': self._queue.qsize()})
        return result

    async def close(self) -> None:
        self._closed = True
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        while not self._queue.empty():
            await self.flush()
        await self.adapter.close()

    async def health_check(self) -> TelemetryHealthStatus:
        return await self.adapter.health_check()

    async def _enqueue(self, point: TelemetryPoint) -> str:
        if not self._queue.full():
            await self._queue.put(point)
            return 'accepted'
        strategy = self.settings.queue_full_strategy
        if strategy == 'block':
            await self._queue.put(point)
            return 'accepted'
        if strategy == 'fail':
            raise TelemetryQueueFull('telemetry queue is full')
        if strategy == 'drop_oldest':
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await self._queue.put(point)
            return 'dropped'
        return 'dropped'

    async def _flush_ready_batches(self) -> WriteResult:
        written = 0
        failures: list[WriteFailure] = []
        while self._queue.qsize() >= self.settings.batch_size:
            result = await self.flush()
            written += result.written
            failures.extend(result.failures)
        return WriteResult(accepted=0, written=written, failures=tuple(failures))

    def _drain_batch(self, limit: int) -> list[TelemetryPoint]:
        batch: list[TelemetryPoint] = []
        while len(batch) < limit:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _write_with_retries(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        pending = list(enumerate(points))
        failures: list[WriteFailure] = []
        written_total = 0
        for attempt in range(self.settings.max_retries + 1):
            pending_points = [point for _, point in pending]
            try:
                result = await asyncio.wait_for(self.adapter.write_many(pending_points), timeout=self.settings.flush_timeout)
            except Exception as exc:
                if attempt >= self.settings.max_retries:
                    failures.extend(WriteFailure(index=index, point=point, error=str(exc)) for index, point in pending)
                    return WriteResult(accepted=len(points), written=written_total, failures=tuple(failures))
                await self._sleep_before_retry(attempt)
                continue

            if not result.failures:
                return WriteResult(accepted=len(points), written=written_total + result.written, failures=tuple(failures))
            written_total += result.written
            next_pending: list[tuple[int, TelemetryPoint]] = []
            for failure in result.failures:
                original_index, original_point = self._map_failure_to_original(pending, failure)
                mapped_failure = WriteFailure(
                    index=original_index,
                    point=failure.point or original_point,
                    error=failure.error,
                    retriable=failure.retriable,
                )
                if mapped_failure.retriable and attempt < self.settings.max_retries:
                    next_pending.append((original_index, mapped_failure.point))
                else:
                    failures.append(mapped_failure)
            if attempt >= self.settings.max_retries:
                return WriteResult(accepted=len(points), written=written_total, failures=tuple(failures))
            if not next_pending:
                return WriteResult(accepted=len(points), written=written_total, failures=tuple(failures))
            pending = next_pending
            await self._sleep_before_retry(attempt)
        return WriteResult(accepted=len(points), written=written_total, failures=tuple(failures))

    @staticmethod
    def _map_failure_to_original(pending: Sequence[tuple[int, TelemetryPoint]], failure: WriteFailure) -> tuple[int, TelemetryPoint]:
        if 0 <= failure.index < len(pending):
            return pending[failure.index]
        return failure.index, failure.point

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.settings.retry_backoff == 'none':
            return
        delay = 0.05
        if self.settings.retry_backoff == 'exponential':
            delay *= 2**attempt
        await asyncio.sleep(delay)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.flush_interval)
            await self.flush()


telemetry = TelemetryManager()
