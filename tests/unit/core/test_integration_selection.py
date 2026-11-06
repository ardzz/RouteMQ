import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from importlib import import_module
from types import ModuleType
from unittest.mock import Mock, patch

import docker
from docker.errors import DockerException
from requests.exceptions import ConnectionError as RequestsConnectionError

import run_tests
from tests.integration import helpers


class IntegrationSelectionTests(unittest.TestCase):
    def test_empty_and_off_disable_integrations(self) -> None:
        for value in ('', 'off'):
            with (
                self.subTest(value=value),
                patch.dict(
                    os.environ,
                    {'RUN_INTEGRATION_TESTS': value},
                    clear=True,
                ),
            ):
                self.assertFalse(helpers.integration_tests_enabled())
                with self.assertRaises(unittest.SkipTest):
                    helpers.require_docker_integration('disabled pipeline')

    def test_optional_spellings_enable_available_docker(self) -> None:
        for value in ('1', 'true', 'yes', 'on'):
            client = Mock()
            client.ping.return_value = True
            with (
                self.subTest(value=value),
                patch.dict(
                    os.environ,
                    {'RUN_INTEGRATION_TESTS': value},
                    clear=True,
                ),
                patch('docker.from_env', return_value=client),
            ):
                self.assertTrue(helpers.integration_tests_enabled())
                helpers.require_docker_integration('optional pipeline')

            client.close.assert_called_once_with()

    def test_optional_mode_skips_unavailable_docker(self) -> None:
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'on'}, clear=True),
            patch(
                'docker.from_env',
                side_effect=DockerException('unavailable'),
            ),
        ):
            with self.assertRaisesRegex(unittest.SkipTest, 'Docker integration.*optional pipeline'):
                helpers.require_docker_integration('optional pipeline')

    def test_optional_mode_skips_missing_docker_dependency_with_remediation(self) -> None:
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'on'}, clear=True),
            patch(
                'tests.integration.helpers.import_module',
                side_effect=ModuleNotFoundError("No module named 'docker'"),
            ),
        ):
            with self.assertRaisesRegex(
                unittest.SkipTest,
                'Docker integration "optional pipeline" requires Python dependency "docker".*Install',
            ):
                helpers.require_docker_integration('optional pipeline')

    def test_required_mode_fails_missing_dependency_before_creating_client(self) -> None:
        docker_module = Mock()

        def import_dependency(name: str) -> Mock:
            if name == 'docker':
                return docker_module
            raise ModuleNotFoundError("No module named 'requests.exceptions'")

        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch('tests.integration.helpers.import_module', side_effect=import_dependency),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                'Docker integration "required pipeline" requires Python dependency "requests.exceptions".*Install',
            ):
                helpers.require_docker_integration('required pipeline')

        docker_module.from_env.assert_not_called()

    def test_selected_dependency_missing_has_mode_specific_remediation(self) -> None:
        for mode, error_type in (('on', unittest.SkipTest), ('required', RuntimeError)):
            with (
                self.subTest(mode=mode),
                patch.dict(
                    os.environ,
                    {'RUN_INTEGRATION_TESTS': mode},
                    clear=True,
                ),
                patch(
                    'tests.integration.helpers.import_module',
                    side_effect=ModuleNotFoundError("No module named 'redis'"),
                ),
            ):
                with self.assertRaises(error_type) as raised:
                    helpers.require_integration_dependency('redis queue tests', 'redis')

            message = str(raised.exception)
            self.assertIn('redis queue tests', message)
            self.assertIn('redis', message)
            self.assertIn('Install', message)

    def test_required_mode_is_enabled_and_fails_unavailable_docker(self) -> None:
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch(
                'docker.from_env',
                side_effect=DockerException('unavailable'),
            ),
        ):
            self.assertTrue(helpers.integration_tests_enabled())
            with self.assertRaisesRegex(RuntimeError, 'Docker integration.*required pipeline.*Start Docker'):
                helpers.require_docker_integration('required pipeline')

    def test_required_mode_closes_available_docker_client(self) -> None:
        client = Mock()
        client.ping.return_value = True
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch(
                'docker.from_env',
                return_value=client,
            ),
        ):
            helpers.require_docker_integration('required pipeline')

        client.ping.assert_called_once_with()
        client.close.assert_called_once_with()

    def test_required_mode_treats_false_ping_as_unavailable_and_closes(self) -> None:
        client = Mock()
        client.ping.return_value = False
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch(
                'docker.from_env',
                return_value=client,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'Docker integration.*required pipeline.*ping returned false'):
                helpers.require_docker_integration('required pipeline')

        client.close.assert_called_once_with()

    def test_required_mode_treats_transport_failure_as_unavailable_and_closes(self) -> None:
        client = Mock()
        client.ping.side_effect = RequestsConnectionError('transport unavailable')
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch(
                'docker.from_env',
                return_value=client,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'Docker integration.*transport unavailable'):
                helpers.require_docker_integration('required pipeline')

        client.close.assert_called_once_with()

    def test_close_failure_does_not_hide_primary_docker_failure(self) -> None:
        client = Mock()
        client.ping.side_effect = DockerException('ping failed')
        client.close.side_effect = DockerException('close failed')
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch(
                'docker.from_env',
                return_value=client,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'ping failed') as raised:
                helpers.require_docker_integration('required pipeline')

        self.assertNotIn('close failed', str(raised.exception))
        client.close.assert_called_once_with()


class RequiredSkipResultTests(unittest.TestCase):
    def _run_with_result(self, mode: str, result: Mock) -> tuple[int, str]:
        stream = io.StringIO()
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': mode}, clear=True),
            patch(
                'run_tests.unittest.defaultTestLoader.discover',
                return_value=unittest.TestSuite(),
            ),
            patch('run_tests.unittest.TextTestRunner') as runner,
            redirect_stderr(stream),
        ):
            runner.return_value.run.return_value = result
            return run_tests.run_tests(), stream.getvalue()

    def test_required_mode_fails_and_reports_every_skip(self) -> None:
        first = Mock()
        first.id.return_value = 'tests.integration.test_first'
        second = Mock()
        second.id.return_value = 'tests.integration.test_second'
        result = Mock()
        result.wasSuccessful.return_value = True
        result.skipped = [(first, 'first reason'), (second, 'second reason')]

        exit_code, output = self._run_with_result('required', result)

        self.assertEqual(exit_code, 1)
        self.assertIn('tests.integration.test_first: first reason', output)
        self.assertIn('tests.integration.test_second: second reason', output)

    def test_off_and_optional_modes_preserve_success_with_skips(self) -> None:
        skipped_test = Mock()
        skipped_test.id.return_value = 'tests.integration.test_skipped'
        for mode in ('off', '1'):
            result = Mock()
            result.wasSuccessful.return_value = True
            result.skipped = [(skipped_test, 'not required')]

            with self.subTest(mode=mode):
                exit_code, output = self._run_with_result(mode, result)

            self.assertEqual(exit_code, 0)
            self.assertEqual(output, '')


class TestcontainersReaperCleanupTests(unittest.TestCase):
    def test_class_cleanup_closes_loaded_reaper(self) -> None:
        reaper = Mock()
        container_module = ModuleType('testcontainers.core.container')
        setattr(container_module, 'Reaper', reaper)

        class ReaperCleanupCase(helpers.DockerIntegrationTestCase):
            pass

        with (
            patch.object(helpers, 'require_docker_integration'),
            patch.dict(sys.modules, {'testcontainers.core.container': container_module}),
        ):
            try:
                ReaperCleanupCase.setUpClass()
            finally:
                ReaperCleanupCase.doClassCleanups()

        reaper.delete_instance.assert_called_once_with()


class BenchmarkSelectionTests(unittest.TestCase):
    def test_mysql_call_sites_gate_exact_module(self) -> None:
        mysql_module = Mock()
        mysql_container = Mock()
        mysql_module.MySqlContainer.return_value = mysql_container
        queue_backends = import_module('tests.integration.test_queue_backends')
        benchmark = import_module('benchmarks.test_database_queue')
        matrix = import_module('benchmarks.db_matrix')

        with (
            patch.object(queue_backends.DockerIntegrationTestCase, 'setUpClass'),
            patch.object(queue_backends.DatabaseQueueIntegrationTests, 'addClassCleanup'),
            patch.object(queue_backends, 'require_integration_dependency', return_value=mysql_module) as queue_gate,
        ):
            queue_backends.DatabaseQueueIntegrationTests.setUpClass()

        queue_gate.assert_called_once_with('DatabaseQueueIntegrationTests', 'testcontainers.mysql')

        with patch.object(benchmark, 'require_integration_dependency', return_value=mysql_module) as benchmark_gate:
            fixture = benchmark.mysql_url.__wrapped__()
            next(fixture)
            fixture.close()

        benchmark_gate.assert_called_once_with('database queue benchmarks', 'testcontainers.mysql')

        expected = RuntimeError('stop after MySQL gate')
        with (
            patch.object(matrix, 'integration_tests_enabled', return_value=True),
            patch.object(matrix, 'require_docker_integration'),
            patch.object(matrix, 'require_integration_dependency', side_effect=expected) as matrix_gate,
        ):
            with self.assertRaisesRegex(RuntimeError, 'stop after MySQL gate'):
                matrix._run_matrix()

        matrix_gate.assert_called_once_with('database queue pool matrix', 'testcontainers.mysql')

    def test_database_queue_benchmark_delegates_to_shared_docker_gate(self) -> None:
        benchmark = import_module('benchmarks.test_database_queue')
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch.object(benchmark, 'require_docker_integration') as require_docker,
        ):
            self.assertTrue(benchmark._docker_available())

        require_docker.assert_called_once_with('database queue benchmarks')

    def test_pool_matrix_required_mode_reaches_shared_docker_gate(self) -> None:
        matrix = import_module('benchmarks.db_matrix')
        expected = RuntimeError('stop after selector gate')
        with (
            patch.dict(os.environ, {'RUN_INTEGRATION_TESTS': 'required'}, clear=True),
            patch.object(matrix, 'require_docker_integration', side_effect=expected) as require_docker,
        ):
            with self.assertRaisesRegex(RuntimeError, 'stop after selector gate'):
                matrix._run_matrix()

        require_docker.assert_called_once_with('database queue pool matrix')


if __name__ == '__main__':
    unittest.main()
