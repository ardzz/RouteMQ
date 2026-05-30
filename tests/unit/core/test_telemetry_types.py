from datetime import UTC, datetime, timezone
import unittest

from routemq.telemetry import Measurement, TelemetryPoint, normalize_timestamp


class MeasurementTests(unittest.TestCase):
    def test_scalar_shorthand_becomes_measurement(self) -> None:
        measurement = Measurement.from_value(31.2)

        self.assertEqual(measurement.value, 31.2)
        self.assertIsNone(measurement.unit)

    def test_mapping_value_preserves_unit_quality_type_and_flags(self) -> None:
        measurement = Measurement.from_value(
            {'value': 31.2, 'unit': '°C', 'quality': 'good', 'type': 'float', 'flags': {'calibrated': 1}}
        )

        self.assertEqual(measurement.value, 31.2)
        self.assertEqual(measurement.unit, '°C')
        self.assertEqual(measurement.quality, 'good')
        self.assertEqual(measurement.data_type, 'float')
        self.assertEqual(measurement.flags, {'calibrated': True})

    def test_mapping_requires_value_key(self) -> None:
        with self.assertRaises(ValueError):
            Measurement.from_value({'unit': 'bar'})

    def test_rejects_unsupported_value_type(self) -> None:
        with self.assertRaises(TypeError):
            Measurement.from_value(object())


class TelemetryPointTests(unittest.TestCase):
    def test_point_normalizes_and_copies_inputs(self) -> None:
        tags = {'site': 'factory-a', 'line': 2}
        attributes = {'gateway': 'gw-1'}
        metadata = {'source_seq': 7}
        point = TelemetryPoint(
            device_id=' pump-7 ',
            observed_at='2026-05-30T10:15:30Z',
            ingested_at=datetime(2026, 5, 30, 10, 15, 31),
            measurements={'temperature': {'value': 31.2, 'unit': '°C'}, 'motor.running': True},
            tags=tags,
            attributes=attributes,
            metadata=metadata,
        )
        tags['site'] = 'mutated'
        attributes['gateway'] = 'mutated'
        metadata['source_seq'] = 9

        self.assertEqual(point.device_id, 'pump-7')
        self.assertEqual(point.observed_at, datetime(2026, 5, 30, 10, 15, 30, tzinfo=UTC))
        self.assertEqual(point.ingested_at, datetime(2026, 5, 30, 10, 15, 31, tzinfo=UTC))
        self.assertEqual(point.measurements['temperature'].unit, '°C')
        self.assertTrue(point.measurements['motor.running'].value)
        self.assertEqual(point.tags, {'site': 'factory-a', 'line': '2'})
        self.assertEqual(point.attributes, {'gateway': 'gw-1'})
        self.assertEqual(point.metadata, {'source_seq': 7})

    def test_requires_device_id(self) -> None:
        with self.assertRaises(ValueError):
            TelemetryPoint(device_id=' ', observed_at=None, measurements={'temperature': 1})

    def test_requires_measurements(self) -> None:
        with self.assertRaises(ValueError):
            TelemetryPoint(device_id='pump-7', observed_at=None, measurements={})

    def test_normalize_timestamp_handles_aware_datetime(self) -> None:
        source = datetime(2026, 5, 30, 17, 15, tzinfo=timezone.utc)

        self.assertEqual(normalize_timestamp(source), datetime(2026, 5, 30, 17, 15, tzinfo=UTC))

    def test_none_timestamps_default_to_now(self) -> None:
        before = datetime.now(UTC)
        point = TelemetryPoint(device_id='pump-7', observed_at=None, measurements={'temperature': 1})
        after = datetime.now(UTC)

        self.assertLessEqual(before, point.observed_at)
        self.assertLessEqual(point.observed_at, after)


if __name__ == '__main__':
    unittest.main()
