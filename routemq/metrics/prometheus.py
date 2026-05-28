"""Optional prometheus_client adapter for RouteMQ metrics exposition.

The module never requires ``prometheus_client`` at import time. Runtime methods
that need the official client raise an actionable error when the optional
``routemq[prometheus]`` extra is not installed.
"""

from __future__ import annotations

import os
from importlib import import_module
from typing import Any

from routemq.metrics.hooks import DefaultHooksHandle, install_default_hooks
from routemq.metrics.registry import MetricsRegistry

try:
    prometheus_client: Any = import_module('prometheus_client')
    multiprocess: Any = import_module('prometheus_client.multiprocess')
    openmetrics_exposition: Any = import_module('prometheus_client.openmetrics.exposition')

    _AVAILABLE = True
except ImportError:
    prometheus_client = None
    multiprocess = None
    openmetrics_exposition = None
    _AVAILABLE = False


_MISSING_EXTRA_MESSAGE = 'routemq[prometheus] extra is not installed. Install with: pip install "routemq[prometheus]"'
PROMETHEUS_CONTENT_TYPE = 'text/plain; version=0.0.4; charset=utf-8'
OPENMETRICS_CONTENT_TYPE = 'application/openmetrics-text; version=1.0.0; charset=utf-8'


class PrometheusAdapter:
    """Adapter around the optional official Prometheus Python client."""

    def __init__(self, *, namespace: str = 'routemq', multiproc_dir: str | None = None) -> None:
        self.namespace = namespace
        self.multiproc_dir = multiproc_dir

    def is_multiprocess_enabled(self) -> bool:
        """Return whether prometheus_client multiprocess collection is available."""

        directory = self._multiprocess_directory()
        return _AVAILABLE and directory is not None and os.path.isdir(directory)

    def render(self, accept: str | None) -> tuple[str, bytes]:
        """Render official Prometheus client metrics for the request Accept header."""

        self._require_prometheus_client()
        assert prometheus_client is not None
        use_openmetrics = _accepts_openmetrics(accept)
        if self.is_multiprocess_enabled():
            registry = prometheus_client.CollectorRegistry()
            assert multiprocess is not None
            multiprocess.MultiProcessCollector(registry, path=self._multiprocess_directory())
        else:
            registry = prometheus_client.REGISTRY
        if use_openmetrics:
            assert openmetrics_exposition is not None
            return OPENMETRICS_CONTENT_TYPE, openmetrics_exposition.generate_latest(registry)
        return PROMETHEUS_CONTENT_TYPE, prometheus_client.generate_latest(registry)

    def install_default_hooks(self, registry: MetricsRegistry) -> DefaultHooksHandle:
        """Install RouteMQ's built-in metrics hooks using this adapter's namespace."""

        return install_default_hooks(registry, namespace=self.namespace)

    def _multiprocess_directory(self) -> str | None:
        return self.multiproc_dir or os.environ.get('PROMETHEUS_MULTIPROC_DIR')

    def _require_prometheus_client(self) -> None:
        if not _AVAILABLE:
            raise RuntimeError(_MISSING_EXTRA_MESSAGE)


def mark_worker_dead(pid: int) -> None:
    """Notify prometheus_client that a multiprocess worker exited."""

    if not _AVAILABLE or multiprocess is None:
        return
    multiproc_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')
    if not multiproc_dir or not os.path.isdir(multiproc_dir):
        return
    multiprocess.mark_process_dead(pid)


def _accepts_openmetrics(accept: str | None) -> bool:
    if not accept:
        return False
    return any(
        media.strip().split(';', 1)[0].strip().lower() == 'application/openmetrics-text'  # nosec B105
        for media in accept.split(',')
    )


__all__ = ['OPENMETRICS_CONTENT_TYPE', 'PROMETHEUS_CONTENT_TYPE', 'PrometheusAdapter', 'mark_worker_dead']
