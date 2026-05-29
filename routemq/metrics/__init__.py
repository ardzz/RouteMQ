"""Vendor-neutral metrics seam for RouteMQ.

RouteMQ ships a stdlib-only OpenMetrics writer by default. The optional
``routemq[prometheus]`` extra adds full multiprocess support backed by the
official ``prometheus_client`` library.
"""

from __future__ import annotations

from routemq.metrics.registry import (
    Counter,
    Gauge,
    Histogram,
    HistogramObservation,
    LabelKey,
    MetricsRegistry,
    Sample,
)

__all__ = [
    'Counter',
    'Gauge',
    'Histogram',
    'HistogramObservation',
    'LabelKey',
    'MetricsRegistry',
    'Sample',
]
