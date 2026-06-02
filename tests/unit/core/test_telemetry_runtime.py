import asyncio
import unittest
from unittest.mock import patch

from routemq.settings import TelemetrySettings
from routemq.telemetry import (
    InMemoryTelemetryAdapter,
    TelemetryAdapter,
    TelemetryManager,
    TelemetryPoint,
    WriteFailure,
    WriteResult,
)
from routemq.telemetry.runtime import TelemetryQueueFull


def _settings(**overrides):
    values = {
        'enabled': True,
        'queue_max_size': 10,
        'queue_full_strategy': 'block',
        'batch_size': 10,
        'flush_interval': 999,
        'flush_timeout': 1,
        'max_retries': 0,
        'retry_backoff': 'none',
    }
    values.update(overrides)
    return TelemetrySettings(**values)


def _point(value=31.2):
    return TelemetryPoint(device_id='pump-7', observed_at='2026-05-30T10:15:30Z', measurements={'temperature': value})


class _FailOnceAdapter(InMemoryTelemetryAdapter):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def write_many(self, points):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError('temporary')
        return await super().write_many(points)


class _PartialAdapter(InMemoryTelemetryAdapter):
    async def write_many(self, points):
        pending = list(points)
        if not pending:
            return WriteResult()
        self.points.extend(pending[:-1])
        return WriteResult(
            accepted=len(pending),
            written=max(0, len(pending) - 1),
            failures=(WriteFailure(index=len(pending) - 1, point=pending[-1], error='partial'),),
        )


class _PartialThenSuccessAdapter(InMemoryTelemetryAdapter):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def write_many(self, points):
        self.calls += 1
        pending = list(points)
        if self.calls == 1:
            self.points.extend(pending[:-1])
            return WriteResult(
                accepted=len(pending),
                written=max(0, len(pending) - 1),
                failures=(WriteFailure(index=len(pending) - 1, point=pending[-1], error='partial'),),
            )
        return await super().write_many(points)


class _NonRetriableAdapter(InMemoryTelemetryAdapter):
    async def write_many(self, points):
        pending = list(points)
        return WriteResult(
            accepted=len(pending),
            written=0,
            failures=(WriteFailure(index=0, point=pending[0], error='no retry', retriable=False),),
        )


class _MixedFailureThenSuccessAdapter(InMemoryTelemetryAdapter):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def write_many(self, points):
        self.calls += 1
        pending = list(points)
        if self.calls == 1:
            return WriteResult(
                accepted=len(pending),
                written=0,
                failures=(
                    WriteFailure(index=0, point=pending[0], error='retry later', retriable=True),
                    WriteFailure(index=1, point=pending[1], error='bad point', retriable=False),
                ),
            )
        return await super().write_many(pending)


class TelemetryRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_returns_false_when_disabled(self) -> None:
        manager = TelemetryManager(settings=TelemetrySettings(enabled=False))

        self.assertFalse(await manager.start())
        await manager.close()

    async def test_start_accepts_new_settings_and_adapter_then_close_cancels_loop(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        manager = TelemetryManager(settings=TelemetrySettings(enabled=False))

        self.assertTrue(await manager.start(adapter=adapter, settings=_settings(flush_interval=999)))
        self.assertIs(manager.adapter, adapter)
        self.assertIsNotNone(manager._flush_task)
        await manager.close()
        self.assertIsNone(manager._flush_task)

    async def test_flush_loop_flushes_by_interval(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        manager = TelemetryManager(adapter=adapter, settings=_settings(batch_size=99, flush_interval=0.01))
        await manager.write(_point())
        await manager.start()
        for _ in range(20):
            if adapter.points:
                break
            await asyncio.sleep(0.01)
        await manager.close()

        self.assertEqual(len(adapter.points), 1)

    async def test_write_many_accepts_and_flushes_by_batch_size(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        manager = TelemetryManager(adapter=adapter, settings=_settings(batch_size=2))

        result = await manager.write_many([_point(1), _point(2)])

        self.assertEqual(result.written, 2)
        self.assertEqual(len(adapter.points), 2)

    async def test_write_delegates_to_write_many(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        manager = TelemetryManager(adapter=adapter, settings=_settings(batch_size=1))

        result = await manager.write(_point())

        self.assertTrue(result.success)

    async def test_fail_strategy_raises_when_full(self) -> None:
        manager = TelemetryManager(settings=_settings(queue_max_size=1, queue_full_strategy='fail', batch_size=99))
        await manager.write(_point(1))

        with self.assertRaises(TelemetryQueueFull):
            await manager.write(_point(2))

    async def test_drop_newest_strategy_drops_new_point(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        manager = TelemetryManager(
            adapter=adapter, settings=_settings(queue_max_size=1, queue_full_strategy='drop_newest', batch_size=99)
        )
        await manager.write(_point(1))
        await manager.write(_point(2))
        await manager.flush()

        self.assertEqual(adapter.points[0].measurements['temperature'].value, 1)

    async def test_drop_oldest_strategy_keeps_new_point(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        manager = TelemetryManager(
            adapter=adapter, settings=_settings(queue_max_size=1, queue_full_strategy='drop_oldest', batch_size=99)
        )
        await manager.write(_point(1))
        await manager.write(_point(2))
        await manager.flush()

        self.assertEqual(adapter.points[0].measurements['temperature'].value, 2)

    async def test_block_strategy_waits_for_space(self) -> None:
        manager = TelemetryManager(settings=_settings(queue_max_size=1, queue_full_strategy='block', batch_size=99))
        await manager.write(_point(1))
        task = asyncio.create_task(manager._enqueue(_point(2)))
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        manager._queue.get_nowait()
        self.assertTrue(await task)

    async def test_retry_succeeds_after_adapter_exception(self) -> None:
        adapter = _FailOnceAdapter()
        manager = TelemetryManager(adapter=adapter, settings=_settings(batch_size=1, max_retries=1))
        with patch('routemq.telemetry.runtime.asyncio.sleep', return_value=None):
            result = await manager.write(_point())

        self.assertTrue(result.success)
        self.assertEqual(adapter.calls, 2)

    async def test_partial_failures_are_reported_after_retry_exhaustion(self) -> None:
        manager = TelemetryManager(adapter=_PartialAdapter(), settings=_settings(batch_size=2, max_retries=0))

        result = await manager.write_many([_point(1), _point(2)])

        self.assertEqual(len(result.failures), 1)

    async def test_partial_failures_retry_pending_points(self) -> None:
        adapter = _PartialThenSuccessAdapter()
        manager = TelemetryManager(
            adapter=adapter, settings=_settings(batch_size=2, max_retries=1, retry_backoff='constant')
        )
        with patch('routemq.telemetry.runtime.asyncio.sleep', return_value=None):
            result = await manager.write_many([_point(1), _point(2)])

        self.assertTrue(result.success)
        self.assertEqual(result.written, 2)

    async def test_non_retriable_partial_failure_returns_immediately(self) -> None:
        manager = TelemetryManager(adapter=_NonRetriableAdapter(), settings=_settings(batch_size=1, max_retries=1))

        result = await manager.write(_point())

        self.assertEqual(len(result.failures), 1)

    async def test_mixed_failures_preserve_non_retriable_failure_after_retry_success(self) -> None:
        adapter = _MixedFailureThenSuccessAdapter()
        manager = TelemetryManager(
            adapter=adapter, settings=_settings(batch_size=2, max_retries=1, retry_backoff='constant')
        )
        with patch('routemq.telemetry.runtime.asyncio.sleep', return_value=None):
            result = await manager.write_many([_point(1), _point(2)])

        self.assertEqual(result.accepted, 2)
        self.assertEqual(result.written, 1)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].index, 1)
        self.assertFalse(result.failures[0].retriable)

    async def test_adapter_exception_reports_failures_after_exhaustion(self) -> None:
        adapter = _FailOnceAdapter()
        manager = TelemetryManager(adapter=adapter, settings=_settings(batch_size=1, max_retries=0))

        result = await manager.write(_point())

        self.assertEqual(len(result.failures), 1)

    async def test_write_after_close_raises(self) -> None:
        manager = TelemetryManager(settings=_settings())
        await manager.close()

        with self.assertRaises(RuntimeError):
            await manager.write(_point())

    async def test_flush_empty_returns_empty_result(self) -> None:
        manager = TelemetryManager(settings=_settings())

        self.assertEqual(await manager.flush(), WriteResult())

    async def test_close_flushes_pending_points_and_closes_adapter(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        adapter.close = unittest.mock.AsyncMock()
        manager = TelemetryManager(adapter=adapter, settings=_settings(batch_size=99))
        await manager.write(_point())
        await manager.close()

        self.assertEqual(len(adapter.points), 1)
        adapter.close.assert_awaited_once()

    async def test_health_check_delegates_to_adapter(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        manager = TelemetryManager(adapter=adapter, settings=_settings())

        self.assertEqual((await manager.health_check()).backend, 'memory')


if __name__ == '__main__':
    unittest.main()
