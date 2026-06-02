from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from routemq.telemetry.types import Measurement, TelemetryPoint


@dataclass(frozen=True, slots=True)
class InfluxLine:
    measurement: str
    tags: dict[str, str]
    fields: dict[str, Any]
    timestamp_ns: int


@dataclass(frozen=True, slots=True)
class IoTDBRecord:
    device_path: str
    timestamp_ms: int
    measurements: dict[str, Any]
    attributes: dict[str, Any]
    metadata: dict[str, Any]


def clickhouse_rows(points: list[TelemetryPoint]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in points:
        for name, measurement in _measurement_items(point):
            rows.append(
                {
                    'observed_at': point.observed_at,
                    'ingested_at': point.ingested_at,
                    'device_id': point.device_id,
                    'measurement': name,
                    **_typed_value_columns(measurement),
                    'unit': measurement.unit,
                    'quality': measurement.quality,
                    'tags': dict(point.tags),
                    'attributes': dict(point.attributes),
                    'metadata': dict(point.metadata),
                }
            )
    return rows


def timescale_rows(points: list[TelemetryPoint]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in points:
        for name, measurement in _measurement_items(point):
            value = measurement.value
            rows.append(
                {
                    'observed_at': point.observed_at,
                    'ingested_at': point.ingested_at,
                    'device_id': point.device_id,
                    'measurement': name,
                    'value_double': float(value)
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                    else None,
                    'value_text': value if isinstance(value, str) else None,
                    'value_bool': value if isinstance(value, bool) else None,
                    'unit': measurement.unit,
                    'quality': measurement.quality,
                    'tags': dict(point.tags),
                    'attributes': dict(point.attributes),
                    'metadata': dict(point.metadata),
                }
            )
    return rows


def influx_lines(points: list[TelemetryPoint], *, measurement_name: str = 'telemetry') -> list[InfluxLine]:
    lines: list[InfluxLine] = []
    for point in points:
        tags = {'device_id': point.device_id} | dict(point.tags)
        fields: dict[str, Any] = {
            name: measurement.value for name, measurement in _measurement_items(point) if measurement.value is not None
        }
        for prefix, values in {'attribute': point.attributes, 'metadata': point.metadata}.items():
            for key, value in values.items():
                field_value = _field_value(value)
                if field_value is not None:
                    fields[f'{prefix}.{key}'] = field_value
        lines.append(
            InfluxLine(
                measurement=measurement_name,
                tags=tags,
                fields=fields,
                timestamp_ns=_timestamp_ns(_observed_at(point)),
            )
        )
    return lines


def iotdb_records(points: list[TelemetryPoint], *, root: str = 'root.routemq') -> list[IoTDBRecord]:
    records: list[IoTDBRecord] = []
    for point in points:
        device_path = f'{root}.{_sanitize_iotdb_path_part(point.device_id)}'
        records.append(
            IoTDBRecord(
                device_path=device_path,
                timestamp_ms=_timestamp_ms(_observed_at(point)),
                measurements={name: measurement.value for name, measurement in _measurement_items(point)},
                attributes=dict(point.attributes),
                metadata=dict(point.metadata),
            )
        )
    return records


def influx_line_protocol(line: InfluxLine) -> str:
    tags = ','.join(f'{_escape_key(key)}={_escape_key(value)}' for key, value in sorted(line.tags.items()))
    fields = ','.join(f'{_escape_key(key)}={_format_influx_value(value)}' for key, value in sorted(line.fields.items()))
    tag_suffix = f',{tags}' if tags else ''
    return f'{_escape_key(line.measurement)}{tag_suffix} {fields} {line.timestamp_ns}'


def _typed_value_columns(measurement: Measurement) -> dict[str, Any]:
    value = measurement.value
    columns: dict[str, Any] = {'value_float': None, 'value_int': None, 'value_string': None, 'value_bool': None}
    if isinstance(value, bool):
        columns['value_bool'] = value
    elif isinstance(value, int):
        columns['value_int'] = value
    elif isinstance(value, float):
        columns['value_float'] = value
    elif value is not None:
        columns['value_string'] = str(value)
    return columns


def _measurement_items(point: TelemetryPoint) -> Iterable[tuple[str, Measurement]]:
    return cast(dict[str, Measurement], point.measurements).items()


def _observed_at(point: TelemetryPoint) -> datetime:
    return cast(datetime, point.observed_at)


def _field_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, sort_keys=True)


def _timestamp_ns(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def _timestamp_ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _sanitize_iotdb_path_part(value: str) -> str:
    return ''.join(char if char.isalnum() or char == '_' else '_' for char in value)


def _escape_key(value: str) -> str:
    return str(value).replace(' ', r'\ ').replace(',', r'\,').replace('=', r'\=')


def _format_influx_value(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return f'{value}i'
    if isinstance(value, float):
        return repr(value)
    escaped = str(value).replace('"', r'\"')
    return f'"{escaped}"'
