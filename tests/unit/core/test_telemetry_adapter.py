import unittest

from routemq.telemetry import (
    InMemoryTelemetryAdapter,
    NoopTelemetryAdapter,
    SchemaValidationResult,
    TelemetryHealthStatus,
    TelemetryPoint,
    WriteFailure,
    WriteResult,
)


def _point(device_id: str = 'pump-7') -> TelemetryPoint:
    return TelemetryPoint(device_id=device_id, observed_at='2026-05-30T10:15:30Z', measurements={'temperature': 31.2})


class WriteResultTests(unittest.TestCase):
    def test_success_requires_no_failures_and_matching_counts(self) -> None:
        point = _point()
        failure = WriteFailure(index=0, point=point, error='boom')

        self.assertTrue(WriteResult(accepted=1, written=1).success)
        self.assertFalse(WriteResult(accepted=1, written=0).success)
        self.assertFalse(WriteResult(accepted=1, written=0, failures=(failure,)).success)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_noop_adapter_reports_written_count(self) -> None:
        adapter = NoopTelemetryAdapter()
        result = await adapter.write_many([_point(), _point('pump-8')])

        self.assertEqual(result.accepted, 2)
        self.assertEqual(result.written, 2)
        self.assertIsInstance(await adapter.validate_schema(), SchemaValidationResult)
        self.assertEqual(await adapter.health_check(), TelemetryHealthStatus(ok=True, backend='noop'))
        await adapter.close()

    async def test_in_memory_adapter_stores_points(self) -> None:
        adapter = InMemoryTelemetryAdapter()
        point = _point()
        result = await adapter.write_many([point])

        self.assertTrue(result.success)
        self.assertEqual(adapter.points, [point])
        self.assertEqual((await adapter.health_check()).backend, 'memory')


if __name__ == '__main__':
    unittest.main()
