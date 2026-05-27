"""Stdlib-only observability seam for RouteMQ.

The module intentionally has no mandatory telemetry backend. It keeps
correlation state in ``contextvars`` and exposes safe no-op hooks that callers
can replace or fan out to later integrations.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger('RouteMQ.Observability')

CORRELATION_ID: ContextVar[str | None] = ContextVar('routemq_correlation_id', default=None)
CONTEXT_ATTRIBUTES: ContextVar[dict[str, Any]] = ContextVar('routemq_context_attributes', default={})

TraceHook = Callable[[str, dict[str, Any]], None]
MetricHook = Callable[[str, float, dict[str, Any]], None]

_trace_hooks: list[TraceHook] = []
_metric_hooks: list[MetricHook] = []


@dataclass(frozen=True)
class ObservabilityToken:
    """Tokens needed to restore a previous observability context."""

    correlation_id: Token[str | None]
    attributes: Token[dict[str, Any]]


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


def clear_hooks() -> None:
    """Remove all registered hooks. Intended for tests and process teardown."""

    _trace_hooks.clear()
    _metric_hooks.clear()


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
