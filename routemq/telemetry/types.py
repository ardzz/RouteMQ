from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

TelemetryScalar = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class Measurement:
    """A named IoT reading value plus optional quality/context metadata."""

    value: TelemetryScalar
    unit: str | None = None
    quality: str | None = None
    data_type: str | None = None
    flags: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _is_supported_scalar(self.value):
            raise TypeError(f'unsupported measurement value type: {type(self.value).__name__}')
        object.__setattr__(self, 'flags', dict(self.flags))

    @classmethod
    def from_value(cls, value: Any) -> 'Measurement':
        if isinstance(value, Measurement):
            return value
        if isinstance(value, Mapping):
            if 'value' not in value:
                raise ValueError("measurement mapping must include a 'value' key")
            return cls(
                value=value.get('value'),
                unit=_optional_string(value.get('unit')),
                quality=_optional_string(value.get('quality')),
                data_type=_optional_string(value.get('data_type') or value.get('type')),
                flags=_bool_mapping(value.get('flags')),
            )
        if not _is_supported_scalar(value):
            raise TypeError(f'unsupported measurement value type: {type(value).__name__}')
        return cls(value=value)


@dataclass(frozen=True, slots=True)
class TelemetryPoint:
    """One IoT observation event from one device."""

    device_id: str
    observed_at: datetime | str | None
    measurements: Mapping[str, Measurement | Mapping[str, Any] | TelemetryScalar]
    tags: Mapping[str, Any] = field(default_factory=dict)
    attributes: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    ingested_at: datetime | str | None = None

    def __post_init__(self) -> None:
        device_id = str(self.device_id).strip()
        if not device_id:
            raise ValueError('device_id is required')
        normalized_measurements = _normalize_measurements(self.measurements)
        if not normalized_measurements:
            raise ValueError('measurements must not be empty')

        object.__setattr__(self, 'device_id', device_id)
        object.__setattr__(self, 'observed_at', normalize_timestamp(self.observed_at))
        object.__setattr__(self, 'ingested_at', normalize_timestamp(self.ingested_at))
        object.__setattr__(self, 'measurements', normalized_measurements)
        object.__setattr__(self, 'tags', _string_mapping(self.tags))
        object.__setattr__(self, 'attributes', dict(self.attributes))
        object.__setattr__(self, 'metadata', dict(self.metadata))


def normalize_timestamp(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    normalized = value.strip()
    if normalized.endswith('Z'):
        normalized = normalized[:-1] + '+00:00'
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_measurements(values: Mapping[str, Any]) -> dict[str, Measurement]:
    measurements: dict[str, Measurement] = {}
    for name, value in dict(values).items():
        normalized_name = str(name).strip()
        if not normalized_name:
            raise ValueError('measurement names must not be empty')
        measurements[normalized_name] = Measurement.from_value(value)
    return measurements


def _string_mapping(values: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(values).items()}


def _bool_mapping(value: Any) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError('measurement flags must be a mapping')
    return {str(key): bool(flag) for key, flag in value.items()}


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _is_supported_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
