import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from routemq.metrics import MetricsRegistry
from routemq.metrics import prometheus as prometheus_module
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

    def test_multiprocess_render_uses_fresh_collector_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'PROMETHEUS_MULTIPROC_DIR': tmpdir}, clear=True):
                adapter = PrometheusAdapter()

                content_type, body = adapter.render(None)

        self.assertEqual(content_type, 'text/plain; version=0.0.4; charset=utf-8')
        self.assertIsInstance(body, bytes)

    def test_multiprocess_mode_requires_existing_directory(self) -> None:
        with patch.dict(os.environ, {'PROMETHEUS_MULTIPROC_DIR': '/missing/routemq-prom'}, clear=True):
            adapter = PrometheusAdapter()

            self.assertFalse(adapter.is_multiprocess_enabled())

    def test_mark_worker_dead_noops_when_env_empty(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            mark_worker_dead(12345)

    def test_mark_worker_dead_delegates_when_env_directory_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {'PROMETHEUS_MULTIPROC_DIR': tmpdir}, clear=True),
                patch('routemq.metrics.prometheus.multiprocess.mark_process_dead') as mark_process_dead,
            ):
                mark_worker_dead(12345)

        mark_process_dead.assert_called_once_with(12345)

    def test_install_default_hooks_delegates_to_builtin_hooks(self) -> None:
        registry = MetricsRegistry()
        adapter = PrometheusAdapter(namespace='custom')
        handle = adapter.install_default_hooks(registry)
        self.addCleanup(handle.unregister)

        self.assertTrue(callable(handle.unregister))


class PrometheusMissingDependencyTests(unittest.TestCase):
    def test_render_raises_clear_error_when_extra_missing(self) -> None:
        module_path = Path(prometheus_module.__file__)
        spec = importlib.util.spec_from_file_location('routemq.metrics.prometheus_missing_test', module_path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None

        with patch.dict(sys.modules, {'prometheus_client': None}):
            spec.loader.exec_module(module)

        with self.assertRaisesRegex(RuntimeError, r'routemq\[prometheus\] extra is not installed'):
            module.PrometheusAdapter().render(None)
        module.mark_worker_dead(12345)


class PrometheusFakeClientTests(unittest.TestCase):
    def _load_with_fake_client(self):
        prometheus_module_file = prometheus_module.__file__
        module_path = Path(prometheus_module_file)
        spec = importlib.util.spec_from_file_location('routemq.metrics.prometheus_fake_test', module_path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None

        fake_client = types.ModuleType('prometheus_client')
        setattr(fake_client, 'REGISTRY', object())

        class CollectorRegistry:
            pass

        setattr(fake_client, 'CollectorRegistry', CollectorRegistry)
        setattr(fake_client, 'generate_latest', lambda registry: b'prometheus-payload')

        fake_multiprocess = types.ModuleType('prometheus_client.multiprocess')
        multiprocess_state: dict[str, object] = {'registry_seen': None, 'dead_pid': None}

        class MultiProcessCollector:
            def __init__(self, registry, path=None):
                multiprocess_state['registry_seen'] = (registry, path)

        setattr(fake_multiprocess, 'MultiProcessCollector', MultiProcessCollector)
        setattr(fake_multiprocess, 'mark_process_dead', lambda pid: multiprocess_state.__setitem__('dead_pid', pid))
        setattr(fake_multiprocess, '_state', multiprocess_state)

        fake_openmetrics = types.ModuleType('prometheus_client.openmetrics.exposition')
        setattr(fake_openmetrics, 'generate_latest', lambda registry: b'openmetrics-payload\n# EOF\n')

        with patch.dict(
            sys.modules,
            {
                'prometheus_client': fake_client,
                'prometheus_client.multiprocess': fake_multiprocess,
                'prometheus_client.openmetrics.exposition': fake_openmetrics,
            },
        ):
            spec.loader.exec_module(module)

        self.assertEqual(module.__file__, prometheus_module_file)
        return module, fake_multiprocess

    def test_fake_prometheus_client_renders_text_and_openmetrics(self) -> None:
        module, _fake_multiprocess = self._load_with_fake_client()
        adapter = module.PrometheusAdapter()

        self.assertEqual(adapter.render(None), (module.PROMETHEUS_CONTENT_TYPE, b'prometheus-payload'))
        self.assertEqual(
            adapter.render('application/openmetrics-text; version=1.0.0'),
            (module.OPENMETRICS_CONTENT_TYPE, b'openmetrics-payload\n# EOF\n'),
        )

    def test_fake_prometheus_client_uses_multiprocess_registry_and_dead_marker(self) -> None:
        module, fake_multiprocess = self._load_with_fake_client()

        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = module.PrometheusAdapter(multiproc_dir=tmpdir)
            self.assertTrue(adapter.is_multiprocess_enabled())

            content_type, body = adapter.render(None)
            with patch.dict(os.environ, {'PROMETHEUS_MULTIPROC_DIR': tmpdir}, clear=True):
                module.mark_worker_dead(4321)

        self.assertEqual(content_type, module.PROMETHEUS_CONTENT_TYPE)
        self.assertEqual(body, b'prometheus-payload')
        state = getattr(fake_multiprocess, '_state')
        registry_seen = state['registry_seen']
        assert isinstance(registry_seen, tuple)
        self.assertEqual(state['registry_seen'][1], tmpdir)
        self.assertEqual(state['dead_pid'], 4321)


if __name__ == '__main__':
    unittest.main()
