"""Stdlib-only observability seam for RouteMQ.

The module intentionally has no mandatory telemetry backend. It keeps
correlation state in ``contextvars`` and exposes safe no-op hooks that callers
can replace or fan out to later integrations.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger('RouteMQ.Observability')

CORRELATION_ID: ContextVar[str | None] = ContextVar('routemq_correlation_id', default=None)
CONTEXT_ATTRIBUTES: ContextVar[dict[str, Any]] = ContextVar('routemq_context_attributes', default={})
CURRENT_SPAN: ContextVar['Span | None'] = ContextVar('routemq_current_span', default=None)

TraceHook = Callable[[str, dict[str, Any]], None]
MetricHook = Callable[[str, float, dict[str, Any]], None]
SpanHook = Callable[['SpanSnapshot'], None]

_trace_hooks: list[TraceHook] = []
_metric_hooks: list[MetricHook] = []
_span_hooks: list[SpanHook] = []

_TRACE_ID_HEX_LENGTH = 32
_SPAN_ID_HEX_LENGTH = 16
_DEFAULT_TRACE_FLAGS = '01'


@dataclass(frozen=True)
class SpanEvent:
    """A timestamped annotation attached to a span."""

    name: str
    attributes: dict[str, Any]
    timestamp_ns: int


@dataclass(frozen=True)
class SpanLink:
    """Reference to another span context."""

    trace_id: str
    span_id: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class SpanSnapshot:
    """Immutable span envelope passed to hooks after a span ends."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    trace_flags: str
    kind: str
    start_time_ns: int
    end_time_ns: int
    duration_ms: float
    status: str
    status_message: str | None
    attributes: dict[str, Any]
    events: tuple[SpanEvent, ...]
    links: tuple[SpanLink, ...]


@dataclass
class Span:
    """In-process span state used by RouteMQ's stdlib tracing seam."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    trace_flags: str = _DEFAULT_TRACE_FLAGS
    kind: str = 'internal'
    attributes: dict[str, Any] | None = None
    links: tuple[SpanLink, ...] = ()
    start_time_ns: int = 0
    end_time_ns: int | None = None
    status: str = 'UNSET'
    status_message: str | None = None
    events: list[SpanEvent] | None = None

    def __post_init__(self) -> None:
        if self.start_time_ns == 0:
            self.start_time_ns = time.time_ns()
        if self.attributes is None:
            self.attributes = {}
        else:
            self.attributes = dict(self.attributes)
        if self.events is None:
            self.events = []
        else:
            self.events = list(self.events)

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""

        if self.attributes is None:
            self.attributes = {}
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Mapping[str, Any] | None = None) -> None:
        """Append an event to the span."""

        if self.events is None:
            self.events = []
        self.events.append(SpanEvent(name=name, attributes=dict(attributes or {}), timestamp_ns=time.time_ns()))

    def set_status(self, status: str, message: str | None = None) -> None:
        """Set the final span status."""

        self.status = status
        self.status_message = message

    def record_exception(self, exception: BaseException) -> None:
        """Record exception type and mark the span as failed."""

        error_type = exception.__class__.__name__
        self.set_attribute('error.type', error_type)
        self.add_event('exception', {'error.type': error_type})
        self.set_status('ERROR', error_type)

    def end(self) -> SpanSnapshot:
        """End the span and return a detached snapshot."""

        if self.end_time_ns is None:
            self.end_time_ns = time.time_ns()
        if self.status == 'UNSET':
            self.status = 'OK'
        duration_ms = (self.end_time_ns - self.start_time_ns) / 1_000_000
        return SpanSnapshot(
            name=self.name,
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            trace_flags=self.trace_flags,
            kind=self.kind,
            start_time_ns=self.start_time_ns,
            end_time_ns=self.end_time_ns,
            duration_ms=duration_ms,
            status=self.status,
            status_message=self.status_message,
            attributes=dict(self.attributes or {}),
            events=tuple(_copy_span_event(event) for event in (self.events or [])),
            links=tuple(_copy_span_link(link) for link in self.links),
        )


@dataclass(frozen=True)
class ObservabilityToken:
    """Tokens needed to restore a previous observability context."""

    correlation_id: Token[str | None]
    attributes: Token[dict[str, Any]]


class _NoopSpanScope:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        return None


class _SpanScope:
    def __init__(self, span: Span):
        self.span = span
        self._token: Token[Span | None] | None = None

    def __enter__(self) -> Span:
        self._token = CURRENT_SPAN.set(self.span)
        return self.span

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        try:
            if isinstance(exc_value, BaseException):
                self.span.record_exception(exc_value)
            snapshot = self.span.end()
            _emit_span(snapshot)
        finally:
            if self._token is not None:
                CURRENT_SPAN.reset(self._token)
        return None


def _tracing_enabled() -> bool:
    value = os.getenv('ENABLE_TRACING')
    if value is None:
        return True
    return value.strip().lower() not in {'0', 'false', 'no', 'off'}


def _new_hex_id(length: int) -> str:
    while True:
        value = secrets.token_hex(length // 2)
        if value != '0' * length:
            return value


def _valid_hex(value: Any, length: int) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value != '0' * length


def _valid_trace_flags(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 2:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _copy_span_event(event: SpanEvent) -> SpanEvent:
    return SpanEvent(name=event.name, attributes=dict(event.attributes), timestamp_ns=event.timestamp_ns)


def _copy_span_link(link: SpanLink) -> SpanLink:
    return SpanLink(trace_id=link.trace_id, span_id=link.span_id, attributes=dict(link.attributes))


def _copy_span_snapshot(snapshot: SpanSnapshot) -> SpanSnapshot:
    return SpanSnapshot(
        name=snapshot.name,
        trace_id=snapshot.trace_id,
        span_id=snapshot.span_id,
        parent_span_id=snapshot.parent_span_id,
        trace_flags=snapshot.trace_flags,
        kind=snapshot.kind,
        start_time_ns=snapshot.start_time_ns,
        end_time_ns=snapshot.end_time_ns,
        duration_ms=snapshot.duration_ms,
        status=snapshot.status,
        status_message=snapshot.status_message,
        attributes=dict(snapshot.attributes),
        events=tuple(_copy_span_event(event) for event in snapshot.events),
        links=tuple(_copy_span_link(link) for link in snapshot.links),
    )


def _emit_span(snapshot: SpanSnapshot) -> None:
    for hook in list(_span_hooks):
        try:
            hook(_copy_span_snapshot(snapshot))
        except Exception:
            logger.debug('Observability span hook failed', exc_info=True)


def _parent_context() -> tuple[str, str | None, str]:
    parent = CURRENT_SPAN.get()
    if parent is not None:
        return parent.trace_id, parent.span_id, parent.trace_flags

    context = CONTEXT_ATTRIBUTES.get()
    trace_value = context.get('trace_id')
    span_value = context.get('span_id')
    flags_value = context.get('trace_flags')

    if _valid_hex(trace_value, _TRACE_ID_HEX_LENGTH) and isinstance(trace_value, str):
        trace_id = trace_value
        parent_span_id = (
            span_value if _valid_hex(span_value, _SPAN_ID_HEX_LENGTH) and isinstance(span_value, str) else None
        )
    else:
        trace_id = _new_hex_id(_TRACE_ID_HEX_LENGTH)
        parent_span_id = None

    trace_flags = (
        flags_value if _valid_trace_flags(flags_value) and isinstance(flags_value, str) else _DEFAULT_TRACE_FLAGS
    )
    return trace_id, parent_span_id, trace_flags


def current_span() -> Span | None:
    """Return the active span, if tracing is enabled and a span is active."""

    if not _tracing_enabled():
        return None
    return CURRENT_SPAN.get()


def start_span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
    *,
    kind: str = 'internal',
    links: tuple[SpanLink, ...] | None = None,
) -> _SpanScope | _NoopSpanScope:
    """Start a span context manager using W3C-shaped trace/span IDs."""

    if not _tracing_enabled():
        return _NoopSpanScope()

    trace_id, parent_span_id, trace_flags = _parent_context()
    span = Span(
        name=name,
        trace_id=trace_id,
        span_id=_new_hex_id(_SPAN_ID_HEX_LENGTH),
        parent_span_id=parent_span_id,
        trace_flags=trace_flags,
        kind=kind,
        attributes=dict(attributes or {}),
        links=tuple(links or ()),
    )
    return _SpanScope(span)


def generate_correlation_id() -> str:
    """Return a fresh correlation identifier safe for logs and payloads."""

    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    """Return the current correlation id, if one is active."""

    return CORRELATION_ID.get()


def set_correlation_id(correlation_id: str | None = None) -> Token[str | None]:
    """Set the current correlation id and return a reset token."""

    return CORRELATION_ID.set(correlation_id or generate_correlation_id())


def reset_correlation_id(token: Token[str | None]) -> None:
    """Reset the correlation id with a token returned by set_correlation_id."""

    CORRELATION_ID.reset(token)


def get_context_attributes() -> dict[str, Any]:
    """Return a copy of current non-correlation observability attributes."""

    return dict(CONTEXT_ATTRIBUTES.get())


def snapshot_context(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Capture the current correlation context as a serializable mapping."""

    snapshot = get_context_attributes()
    correlation_id = get_correlation_id()
    if correlation_id is not None:
        snapshot['correlation_id'] = correlation_id
    span = current_span()
    if span is not None:
        snapshot['trace_id'] = span.trace_id
        snapshot['span_id'] = span.span_id
        snapshot['trace_flags'] = span.trace_flags
        snapshot['parent_span_id'] = span.parent_span_id
    if extra:
        snapshot.update(dict(extra))
    return snapshot


def set_context(
    context: Mapping[str, Any] | None = None,
    *,
    correlation_id: str | None = None,
    ensure_correlation_id: bool = True,
    **attributes: Any,
) -> ObservabilityToken:
    """Replace the current observability context and return reset tokens."""

    incoming = dict(context or {})
    selected_correlation_id = correlation_id or incoming.pop('correlation_id', None)
    if selected_correlation_id is None and ensure_correlation_id:
        selected_correlation_id = generate_correlation_id()

    incoming.update(attributes)
    correlation_token = CORRELATION_ID.set(selected_correlation_id)
    attributes_token = CONTEXT_ATTRIBUTES.set(incoming)
    return ObservabilityToken(correlation_token, attributes_token)


def enrich_context(**attributes: Any) -> ObservabilityToken:
    """Merge attributes into the current context and ensure correlation exists."""

    context = get_context_attributes()
    context.update(attributes)
    return set_context(context, correlation_id=get_correlation_id(), ensure_correlation_id=True)


def reset_context(token: ObservabilityToken) -> None:
    """Restore a previous observability context."""

    CONTEXT_ATTRIBUTES.reset(token.attributes)
    CORRELATION_ID.reset(token.correlation_id)


def job_context_from_payload(payload: str) -> dict[str, Any]:
    """Extract serialized observability metadata from a job payload."""

    import json

    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return {}
    observability = data.get('observability', {})
    return observability if isinstance(observability, dict) else {}


def register_trace_hook(hook: TraceHook) -> Callable[[], None]:
    """Register a tracing hook and return an unregister callback."""

    _trace_hooks.append(hook)

    def unregister() -> None:
        try:
            _trace_hooks.remove(hook)
        except ValueError:
            pass

    return unregister


def register_metric_hook(hook: MetricHook) -> Callable[[], None]:
    """Register a metrics hook and return an unregister callback."""

    _metric_hooks.append(hook)

    def unregister() -> None:
        try:
            _metric_hooks.remove(hook)
        except ValueError:
            pass

    return unregister


def register_span_hook(hook: SpanHook) -> Callable[[], None]:
    """Register a span hook and return an unregister callback."""

    _span_hooks.append(hook)

    def unregister() -> None:
        try:
            _span_hooks.remove(hook)
        except ValueError:
            pass

    return unregister


def clear_hooks() -> None:
    """Remove all registered hooks. Intended for tests and process teardown."""

    _trace_hooks.clear()
    _metric_hooks.clear()
    _span_hooks.clear()


def trace(name: str, attributes: Mapping[str, Any] | None = None) -> None:
    """Emit a trace lifecycle event to registered hooks.

    Hook failures are logged at debug level and swallowed so they never mask
    framework or user handler errors.
    """

    hook_attributes = snapshot_context(attributes)
    for hook in list(_trace_hooks):
        try:
            hook(name, dict(hook_attributes))
        except Exception:
            logger.debug('Observability trace hook failed', exc_info=True)


def metric(name: str, value: float = 1.0, attributes: Mapping[str, Any] | None = None) -> None:
    """Emit a metric event to registered hooks without requiring a backend."""

    hook_attributes = snapshot_context(attributes)
    for hook in list(_metric_hooks):
        try:
            hook(name, value, dict(hook_attributes))
        except Exception:
            logger.debug('Observability metric hook failed', exc_info=True)


def lifecycle(event: str, attributes: Mapping[str, Any] | None = None, *, value: float = 1.0) -> None:
    """Emit matching trace and metric lifecycle events."""

    trace(event, attributes)
    metric(event, value, attributes)
