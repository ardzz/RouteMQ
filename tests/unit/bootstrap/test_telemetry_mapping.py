from datetime import UTC, datetime
import unittest

from routemq.telemetry import Measurement, TelemetryPoint
from routemq.tsdb.telemetry_mapping import (
    clickhouse_rows,
    influx_line_protocol,
    influx_lines,
    iotdb_records,
    timescale_rows,
)


def _point() -> TelemetryPoint:
    return TelemetryPoint(
        device_id='pump-7',
        observed_at='2026-05-30T10:15:30Z',
        ingested_at='2026-05-30T10:15:31Z',
        measurements={
            'temperature': Measurement(value=31.2, unit='°C', quality='good'),
            'cycles': 7,
            'state': 'running',
            'motor.running': True,
        },
        tags={'site': 'factory a'},
        attributes={'gateway_id': 'gw-1'},
        metadata={'source_seq': 18492},
    )


class TelemetryMappingTests(unittest.TestCase):
    def test_clickhouse_rows_use_narrow_typed_columns(self) -> None:
        rows = clickhouse_rows([_point()])

        self.assertEqual(len(rows), 4)
        by_name = {row['measurement']: row for row in rows}
        self.assertEqual(by_name['temperature']['value_float'], 31.2)
        self.assertEqual(by_name['temperature']['unit'], '°C')
        self.assertEqual(by_name['cycles']['value_int'], 7)
        self.assertEqual(by_name['state']['value_string'], 'running')
        self.assertTrue(by_name['motor.running']['value_bool'])
        self.assertIsNone(by_name['motor.running']['value_int'])
        self.assertEqual(by_name['temperature']['tags'], {'site': 'factory a'})

    def test_timescale_rows_use_json_context_and_double_value(self) -> None:
        row = next(row for row in timescale_rows([_point()]) if row['measurement'] == 'temperature')

        self.assertEqual(row['value_double'], 31.2)
        self.assertEqual(row['tags'], {'site': 'factory a'})
        self.assertEqual(row['attributes'], {'gateway_id': 'gw-1'})
        self.assertEqual(row['metadata'], {'source_seq': 18492})

    def test_influx_lines_map_device_and_tags_to_tags(self) -> None:
        line = influx_lines([_point()])[0]

        self.assertEqual(line.tags['device_id'], 'pump-7')
        self.assertEqual(line.tags['site'], 'factory a')
        self.assertEqual(line.fields['temperature'], 31.2)
        self.assertEqual(
            line.timestamp_ns, int(datetime(2026, 5, 30, 10, 15, 30, tzinfo=UTC).timestamp() * 1_000_000_000)
        )
        self.assertIn('device_id=pump-7', influx_line_protocol(line))

    def test_iotdb_records_map_device_to_path(self) -> None:
        record = iotdb_records([_point()], root='root.factory')[0]

        self.assertEqual(record.device_path, 'root.factory.pump_7')
        self.assertEqual(record.measurements['temperature'], 31.2)
        self.assertEqual(record.attributes, {'gateway_id': 'gw-1'})


if __name__ == '__main__':
    unittest.main()
