import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

from routemq.metrics import MetricsRegistry
from routemq.metrics.prometheus import OPENMETRICS_CONTENT_TYPE, PrometheusAdapter, mark_worker_dead

prometheus_client_importable = importlib.util.find_spec('prometheus_client') is not None


@unittest.skipUnless(prometheus_client_importable, 'prometheus_client is not installed')
class PrometheusAdapterTests(unittest.TestCase):
    def test_single_process_render_returns_prometheus_text(self) -> None:
        adapter = PrometheusAdapter()

        content_type, body = adapter.render(None)

        self.assertIn('text/plain; version=0.0.4', content_type)
        self.assertIn(b'# HELP', body)

    def test_openmetrics_negotiation_returns_openmetrics_payload(self) -> None:
        adapter = PrometheusAdapter()

        content_type, body = adapter.render('text/plain, application/openmetrics-text; version=1.0.0')

        self.assertEqual(content_type, OPENMETRICS_CONTENT_TYPE)
        self.assertTrue(body.endswith(b'# EOF\n'))

    def test_multiprocess_mode_is_detected_from_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'PROMETHEUS_MULTIPROC_DIR': tmpdir}, clear=True):
                adapter = PrometheusAdapter()

                self.assertTrue(adapter.is_multiprocess_enabled())

    def test_multiprocess_mode_requires_existing_directory(self) -> None:
        with patch.dict(os.environ, {'PROMETHEUS_MULTIPROC_DIR': '/missing/routemq-prom'}, clear=True):
            adapter = PrometheusAdapter()

            self.assertFalse(adapter.is_multiprocess_enabled())

    def test_mark_worker_dead_noops_when_env_empty(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            mark_worker_dead(12345)

    def test_install_default_hooks_delegates_to_builtin_hooks(self) -> None:
        registry = MetricsRegistry()
        adapter = PrometheusAdapter(namespace='custom')
        handle = adapter.install_default_hooks(registry)
        self.addCleanup(handle.unregister)

        self.assertTrue(callable(handle.unregister))


if __name__ == '__main__':
    unittest.main()
