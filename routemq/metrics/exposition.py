"""Stdlib OpenMetrics/Prometheus text exposition for ``MetricsRegistry``.

Implements the line-oriented exposition formats described by the Prometheus
text exposition spec and the OpenMetrics 1.0 spec. Operators choose the format
through HTTP content negotiation; both formats share the same underlying
``MetricsRegistry`` collection.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from routemq.metrics.registry import LabelKey, MetricsRegistry, Sample

PROMETHEUS_CONTENT_TYPE = 'text/plain; version=0.0.4; charset=utf-8'
OPENMETRICS_CONTENT_TYPE = 'application/openmetrics-text; version=1.0.0; charset=utf-8'


def negotiate_content_type(accept_header: str | None) -> str:
    """Return the content type to render for a given ``Accept`` request header.

    OpenMetrics is preferred when the client advertises it. Anything else,
    including missing/empty headers, falls back to the Prometheus text format
    that every modern scraper understands.
    """

    if not accept_header:
        return PROMETHEUS_CONTENT_TYPE
    for media in accept_header.split(','):
        token = media.strip().split(';', 1)[0].strip().lower()
        if token == 'application/openmetrics-text':  # nosec B105
            return OPENMETRICS_CONTENT_TYPE
    return PROMETHEUS_CONTENT_TYPE


def render(
    registry: MetricsRegistry,
    *,
    content_type: str = PROMETHEUS_CONTENT_TYPE,
    static_labels: Mapping[str, Any] | None = None,
) -> bytes:
    """Render ``registry`` as exposition-format bytes for ``content_type``.

    ``static_labels`` is merged into every emitted sample so deployments can
    surface env/service/instance tags without registering them per metric.
    """

    if content_type not in {PROMETHEUS_CONTENT_TYPE, OPENMETRICS_CONTENT_TYPE}:
        raise ValueError(f'Unsupported metrics content type: {content_type!r}')
    is_openmetrics = content_type == OPENMETRICS_CONTENT_TYPE
    static = _normalize_static_labels(static_labels)
    lines: list[str] = []
    for name, family_type, help_text, samples in registry.collect():
        rendered_type = 'counter' if is_openmetrics and family_type == 'counter' else family_type
        lines.append(f'# HELP {name} {_escape_help(help_text)}')
        lines.append(f'# TYPE {name} {rendered_type}')
        for sample in samples:
            lines.append(_format_sample_line(name, sample, static, is_openmetrics))
    if is_openmetrics:
        lines.append('# EOF')
    payload = '\n'.join(lines)
    if not payload.endswith('\n'):
        payload = payload + '\n'
    return payload.encode('utf-8')


def _normalize_static_labels(static_labels: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    if not static_labels:
        return ()
    return tuple((str(key), str(value)) for key, value in static_labels.items())


def _format_sample_line(
    name: str,
    sample: Sample,
    static: tuple[tuple[str, str], ...],
    is_openmetrics: bool,
) -> str:
    metric_name = name
    suffix = sample.name_suffix
    if is_openmetrics and suffix == '_total':
        metric_name = f'{name}_total'
        labels = sample.label_key
    else:
        metric_name = f'{name}{suffix}'
        labels = sample.label_key
    merged_labels = static + labels
    label_text = _format_labels(merged_labels)
    value_text = _format_value(sample.value, is_openmetrics)
    if label_text:
        return f'{metric_name}{{{label_text}}} {value_text}'
    return f'{metric_name} {value_text}'


def _format_labels(labels: Iterable[tuple[str, str]]) -> str:
    parts: list[str] = []
    for key, value in labels:
        parts.append(f'{key}="{_escape_label_value(value)}"')
    return ','.join(parts)


def _escape_label_value(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def _escape_help(value: str) -> str:
    return value.replace('\\', '\\\\').replace('\n', '\\n')


def _format_value(value: float, is_openmetrics: bool) -> str:
    if value != value:
        return 'NaN'
    if value == float('inf'):
        return '+Inf'
    if value == float('-inf'):
        return '-Inf'
    if is_openmetrics:
        formatted = f'{value:.10g}'
        if '.' not in formatted and 'e' not in formatted and 'E' not in formatted:
            return formatted
        return formatted
    if value.is_integer() and abs(value) < 1e16:
        return f'{int(value)}'
    return f'{value:.10g}'


def _label_key_to_text(label_key: LabelKey) -> str:
    return _format_labels(label_key)
