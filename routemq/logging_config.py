"""Logging configuration helpers for RouteMQ.

The module keeps RouteMQ's core logging backend-neutral. JSON output is plain
NDJSON that log shippers can parse, transform, and route to the backend chosen
by the application owner.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from . import observability


_LOG_RECORD_RESERVED = set(
    logging.LogRecord(
        name='',
        level=logging.INFO,
        pathname='',
        lineno=0,
        msg='',
        args=(),
        exc_info=None,
    ).__dict__
) | {'message', 'asctime'}

_SEVERITY_NUMBER = {
    logging.DEBUG: 5,
    logging.INFO: 9,
    logging.WARNING: 13,
    logging.ERROR: 17,
    logging.CRITICAL: 21,
}

_SEVERITY_TEXT = {
    logging.DEBUG: 'DEBUG',
    logging.INFO: 'INFO',
    logging.WARNING: 'WARN',
    logging.ERROR: 'ERROR',
    logging.CRITICAL: 'FATAL',
}

_KNOWN_CONTEXT_FIELDS = {
    'actual_topic',
    'attempts',
    'bulk',
    'connection',
    'correlation_id',
    'delay',
    'duration_ms',
    'error',
    'event.domain',
    'event.name',
    'group_name',
    'job_class',
    'job_id',
    'mqtt_subscription_topic',
    'mqtt_topic',
    'parent_span_id',
    'process',
    'queue',
    'reason',
    'route_pattern',
    'route_shared',
    'source',
    'span_id',
    'trace_flags',
    'trace_id',
    'worker_id',
}

_ROUTEMQ_FIELD_ALIASES = {
    'actual_topic': 'routemq.mqtt.actual_topic',
    'attempts': 'routemq.job.attempt',
    'bulk': 'routemq.queue.bulk',
    'connection': 'routemq.connection',
    'delay': 'routemq.job.delay',
    'group_name': 'routemq.mqtt.group_name',
    'job_class': 'routemq.job.class',
    'job_id': 'routemq.job.id',
    'mqtt_subscription_topic': 'routemq.mqtt.subscription_topic',
    'mqtt_topic': 'routemq.mqtt.topic',
    'process': 'routemq.process',
    'queue': 'routemq.queue',
    'reason': 'routemq.reason',
    'route_pattern': 'routemq.route.pattern',
    'route_shared': 'routemq.route.shared',
    'source': 'routemq.source',
    'worker_id': 'routemq.worker.id',
}

_LIFECYCLE_EVENTS = {
    'mqtt.connect.retry',
    'mqtt.connect.succeeded',
    'mqtt.message.received',
    'mqtt.message.succeeded',
    'mqtt.message.failed',
    'router.dispatch.started',
    'router.dispatch.succeeded',
    'router.dispatch.failed',
    'router.dispatch.missed',
    'queue.enqueue.started',
    'queue.enqueue.succeeded',
    'queue.enqueue.failed',
    'queue.job.started',
    'queue.job.succeeded',
    'queue.job.timed_out',
    'queue.job.retried',
    'queue.job.failed',
    'queue.job.dead_lettered',
}

_lifecycle_unregister: Any = None


@dataclass(frozen=True)
class LoggingSettings:
    formatter: str
    field_profile: str
    level: int
    lifecycle_events: bool
    lifecycle_level: int


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def get_formatter_name() -> str:
    """Return the configured formatter name.

    ``LOG_FORMATTER`` is authoritative. For backward compatibility, a legacy
    custom ``LOG_FORMAT`` pattern without ``LOG_FORMATTER`` opts into plain
    formatting instead of silently switching old apps to JSON.
    """

    explicit = os.getenv('LOG_FORMATTER')
    if explicit:
        return explicit.strip().lower()

    legacy_format = os.getenv('LOG_FORMAT')
    if legacy_format:
        if legacy_format.strip().lower() in {'json', 'plain'}:
            return legacy_format.strip().lower()
        return 'plain'

    return 'json'


def _level_from_env(name: str, default: str = 'INFO') -> int:
    value = os.getenv(name, default).upper()
    resolved = getattr(logging, value, logging.INFO)
    return resolved if isinstance(resolved, int) else logging.INFO


def _utc_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace('+00:00', 'Z')


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _route_context_fields(values: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    known: dict[str, Any] = {}
    attributes: dict[str, Any] = {}
    for key, value in values.items():
        if key == 'attributes' and isinstance(value, Mapping):
            attributes.update({str(attr_key): _json_safe(attr_value) for attr_key, attr_value in value.items()})
        elif key in _KNOWN_CONTEXT_FIELDS:
            known[key] = _json_safe(value)
        else:
            attributes[str(key)] = _json_safe(value)
    return known, attributes


def _record_extra(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in record.__dict__.items() if key not in _LOG_RECORD_RESERVED}


def _service_version() -> str | None:
    explicit = os.getenv('SERVICE_VERSION') or os.getenv('DD_VERSION') or os.getenv('VERSION')
    if explicit:
        return explicit
    try:
        return version('routemq')
    except PackageNotFoundError:
        # Audit Accept: source checkout fallback when package metadata is unavailable.
        return '0.0.0+dev'


class RouteMQJsonFormatter(logging.Formatter):
    """Formatter that emits one JSON object per log record."""

    def __init__(self, *, field_profile: str = 'otel', include_context: bool = True):
        super().__init__()
        self.field_profile = field_profile.lower()
        self.include_context = include_context

    def format(self, record: logging.LogRecord) -> str:
        context = observability.snapshot_context() if self.include_context else {}
        context_known, context_attributes = _route_context_fields(context)
        extra_known, extra_attributes = _route_context_fields(_record_extra(record))

        known = {**context_known, **extra_known}
        attributes = {**context_attributes, **extra_attributes}
        event_name = known.get('event.name')
        event_domain = known.get('event.domain')
        exception = self._exception_fields(record, known)

        base = self._otel_record(record, known, attributes, event_name, event_domain, exception)
        if self.field_profile == 'ecs':
            payload = self._ecs_record(base, known, attributes, exception)
        elif self.field_profile == 'datadog':
            payload = self._datadog_record(base, known, attributes, exception)
        elif self.field_profile == 'loki':
            payload = self._loki_record(base, known, attributes, exception)
        elif self.field_profile == 'routemq':
            payload = self._routemq_record(base, known, attributes, exception)
        else:
            payload = base

        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    def _exception_fields(self, record: logging.LogRecord, known: Mapping[str, Any]) -> dict[str, Any]:
        exc_type = None
        exc_message = None
        exc_stacktrace = None
        if record.exc_info:
            exception_type, exception_value, _ = record.exc_info
            exc_type = exception_type.__name__ if exception_type else None
            exc_message = str(exception_value) if exception_value else None
            exc_stacktrace = ''.join(traceback.format_exception(*record.exc_info))
        elif known.get('error') is not None:
            exc_type = str(known['error'])

        return {
            'exception.type': exc_type,
            'exception.message': exc_message,
            'exception.stacktrace': exc_stacktrace,
        }

    def _otel_record(
        self,
        record: logging.LogRecord,
        known: Mapping[str, Any],
        attributes: Mapping[str, Any],
        event_name: Any,
        event_domain: Any,
        exception: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'timestamp': _utc_from_timestamp(record.created),
            'observed_timestamp': _utc_now(),
            'severity_text': _SEVERITY_TEXT.get(record.levelno, record.levelname),
            'severity_number': _SEVERITY_NUMBER.get(record.levelno, record.levelno),
            'logger': record.name,
            'message': record.getMessage(),
            'service.name': os.getenv('SERVICE_NAME') or os.getenv('DD_SERVICE') or 'routemq-app',
            'service.namespace': os.getenv('SERVICE_NAMESPACE'),
            'service.version': _service_version(),
            'service.instance.id': os.getenv('SERVICE_INSTANCE_ID') or os.getenv('HOSTNAME'),
            'deployment.environment.name': os.getenv('DEPLOYMENT_ENVIRONMENT')
            or os.getenv('DD_ENV')
            or os.getenv('APP_ENV')
            or os.getenv('ENV')
            or 'development',
            'correlation_id': known.get('correlation_id'),
            'trace_id': known.get('trace_id'),
            'span_id': known.get('span_id'),
            'trace_flags': known.get('trace_flags'),
            'parent_span_id': known.get('parent_span_id'),
            'event.name': event_name,
            'event.domain': event_domain,
            'exception.type': exception.get('exception.type'),
            'exception.message': exception.get('exception.message'),
            'exception.stacktrace': exception.get('exception.stacktrace'),
            'attributes': dict(attributes),
        }
        for source_field, log_field in _ROUTEMQ_FIELD_ALIASES.items():
            payload[log_field] = known.get(source_field)
        if known.get('duration_ms') is not None:
            payload['duration_ms'] = known.get('duration_ms')
        return payload

    def _ecs_record(
        self,
        base: Mapping[str, Any],
        known: Mapping[str, Any],
        attributes: Mapping[str, Any],
        exception: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = {
            '@timestamp': base['timestamp'],
            'message': base['message'],
            'log.level': str(base['severity_text']).lower(),
            'log.logger': base['logger'],
            'event.action': base.get('event.name'),
            'event.dataset': base.get('event.domain') or 'routemq',
            'service.name': base['service.name'],
            'service.environment': base['deployment.environment.name'],
            'service.version': base['service.version'],
            'trace.id': base.get('trace_id'),
            'span.id': base.get('span_id'),
            'error.type': exception.get('exception.type'),
            'error.message': exception.get('exception.message'),
            'error.stack_trace': exception.get('exception.stacktrace'),
            'labels': {'correlation_id': known.get('correlation_id')},
            'routemq': self._nested_routemq_fields(known),
            'attributes': dict(attributes),
        }
        return payload

    def _datadog_record(
        self,
        base: Mapping[str, Any],
        known: Mapping[str, Any],
        attributes: Mapping[str, Any],
        exception: Mapping[str, Any],
    ) -> dict[str, Any]:
        service_name = base['service.name']
        env = base['deployment.environment.name']
        version_value = base['service.version']
        return {
            'timestamp': base['timestamp'],
            'message': base['message'],
            'status': str(base['severity_text']).lower(),
            'logger': base['logger'],
            'service': service_name,
            'env': env,
            'version': version_value,
            'dd.service': service_name,
            'dd.env': env,
            'dd.version': version_value,
            'dd.trace_id': base.get('trace_id'),
            'dd.span_id': base.get('span_id'),
            'correlation_id': known.get('correlation_id'),
            'event.name': base.get('event.name'),
            'event.domain': base.get('event.domain'),
            'error.type': exception.get('exception.type'),
            'error.message': exception.get('exception.message'),
            'error.stack': exception.get('exception.stacktrace'),
            'routemq': self._nested_routemq_fields(known),
            'attributes': dict(attributes),
        }

    def _loki_record(
        self,
        base: Mapping[str, Any],
        known: Mapping[str, Any],
        attributes: Mapping[str, Any],
        exception: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = dict(base)
        component = known.get('source') or base.get('routemq.process')
        labels = {
            'service.name': base.get('service.name'),
            'deployment.environment.name': base.get('deployment.environment.name'),
            'severity_text': base.get('severity_text'),
        }
        if component is not None:
            labels['routemq.component'] = component
        if known.get('queue') is not None:
            labels['routemq.queue'] = known.get('queue')
        payload['labels'] = labels
        return payload

    def _routemq_record(
        self,
        base: Mapping[str, Any],
        known: Mapping[str, Any],
        attributes: Mapping[str, Any],
        exception: Mapping[str, Any],
    ) -> dict[str, Any]:
        error = None
        if (
            exception.get('exception.type')
            or exception.get('exception.message')
            or exception.get('exception.stacktrace')
        ):
            error = {
                'type': exception.get('exception.type'),
                'message': exception.get('exception.message'),
                'stacktrace': exception.get('exception.stacktrace'),
            }
        return {
            'timestamp': base['timestamp'],
            'level': str(base['severity_text']).lower(),
            'logger': base['logger'],
            'message': base['message'],
            'correlation_id': known.get('correlation_id'),
            'trace_id': base.get('trace_id'),
            'span_id': base.get('span_id'),
            'service': {
                'name': base['service.name'],
                'namespace': base['service.namespace'],
                'version': base['service.version'],
                'env': base['deployment.environment.name'],
            },
            'event': {'name': base.get('event.name'), 'domain': base.get('event.domain')},
            'routemq': self._nested_routemq_fields(known),
            'error': error,
            'attributes': dict(attributes),
        }

    def _nested_routemq_fields(self, known: Mapping[str, Any]) -> dict[str, Any]:
        return {
            'source': known.get('source'),
            'process': known.get('process'),
            'mqtt_topic': known.get('mqtt_topic'),
            'actual_topic': known.get('actual_topic'),
            'group_name': known.get('group_name'),
            'worker_id': known.get('worker_id'),
            'route_pattern': known.get('route_pattern'),
            'mqtt_subscription_topic': known.get('mqtt_subscription_topic'),
            'route_shared': known.get('route_shared'),
            'queue': known.get('queue'),
            'connection': known.get('connection'),
            'job_id': known.get('job_id'),
            'job_class': known.get('job_class'),
            'attempts': known.get('attempts'),
            'delay': known.get('delay'),
            'bulk': known.get('bulk'),
            'reason': known.get('reason'),
        }


def build_formatter(formatter_name: str | None = None, field_profile: str | None = None) -> logging.Formatter:
    name = (formatter_name or get_formatter_name()).lower()
    if name == 'json':
        resolved_profile: str = field_profile or os.getenv('LOG_FIELD_PROFILE') or 'otel'
        return RouteMQJsonFormatter(
            field_profile=resolved_profile,
            include_context=env_bool('LOG_INCLUDE_CONTEXT', True),
        )
    log_format = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    return logging.Formatter(log_format)


def _build_file_handler(log_file: str) -> logging.Handler:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rotation_type = os.getenv('LOG_ROTATION_TYPE', 'size').lower()
    backup_count = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    if rotation_type == 'time':
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_file,
            when=os.getenv('LOG_ROTATION_WHEN', 'midnight').lower(),
            interval=int(os.getenv('LOG_ROTATION_INTERVAL', '1')),
            backupCount=backup_count,
            encoding='utf-8',
        )
        handler.suffix = os.getenv('LOG_DATE_FORMAT', '%Y-%m-%d')
        return handler
    return logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=int(os.getenv('LOG_MAX_BYTES', '10485760')),
        backupCount=backup_count,
        encoding='utf-8',
    )


def configure_logging(*, log_to_console: bool = True) -> LoggingSettings:
    """Configure process logging from environment variables."""

    formatter_name = get_formatter_name()
    field_profile = os.getenv('LOG_FIELD_PROFILE', 'otel').lower()
    level = _level_from_env('LOG_LEVEL')
    formatter = build_formatter(formatter_name, field_profile)
    handlers: list[logging.Handler] = []

    if log_to_console and env_bool('LOG_TO_CONSOLE', True):
        stream_name = os.getenv('LOG_STREAM', 'stdout').lower()
        stream = sys.stderr if stream_name == 'stderr' else sys.stdout
        console_handler = logging.StreamHandler(stream)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    if env_bool('LOG_TO_FILE', False):
        try:
            file_handler = _build_file_handler(os.getenv('LOG_FILE', 'logs/app.log'))
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except OSError:
            # Keep startup resilient when file logging is not writable. The
            # configured console/NullHandler path still applies below.
            logging.getLogger('RouteMQ.Logging').debug('Could not setup file logging', exc_info=True)

    if not handlers:
        handlers.append(logging.NullHandler())

    logging.basicConfig(level=level, handlers=handlers, force=True)
    lifecycle_events = env_bool('LOG_LIFECYCLE_EVENTS', True)
    lifecycle_level = _level_from_env('LOG_LIFECYCLE_LEVEL')
    configure_lifecycle_logging(enabled=lifecycle_events, level=lifecycle_level)
    return LoggingSettings(formatter_name, field_profile, level, lifecycle_events, lifecycle_level)


def configure_lifecycle_logging(*, enabled: bool, level: int = logging.INFO) -> None:
    """Mirror known RouteMQ lifecycle events to structured logs."""

    global _lifecycle_unregister
    if _lifecycle_unregister is not None:
        _lifecycle_unregister()
        _lifecycle_unregister = None

    if not enabled:
        return

    lifecycle_logger = logging.getLogger('RouteMQ.Lifecycle')

    def log_lifecycle(name: str, attributes: dict[str, Any]) -> None:
        if name not in _LIFECYCLE_EVENTS:
            return
        event_domain = name.split('.', 1)[0] if '.' in name else name
        extra = dict(attributes)
        extra['event.name'] = name
        extra['event.domain'] = event_domain
        lifecycle_logger.log(level, 'RouteMQ lifecycle event', extra=extra)

    _lifecycle_unregister = observability.register_trace_hook(log_lifecycle)


def json_logging_enabled() -> bool:
    return get_formatter_name() == 'json'
