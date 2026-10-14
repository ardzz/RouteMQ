import asyncio
import errno
import io
import os
import signal
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from routemq import healthcheck
from routemq.mqtt_utils import is_network_startup_error
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager


class TestCliSubcommands(unittest.TestCase):
    def _run_with_argv(self, argv):
        from routemq.cli import main

        with patch.object(sys, 'argv', ['routemq', *argv]):
            main()

    def test_run_subcommand_calls_application_run(self):
        with patch('routemq.cli.create_app') as mock_create, patch('routemq.cli.create_env_file'):
            mock_app = MagicMock()
            mock_create.return_value = mock_app

            self._run_with_argv(['run'])

            mock_app.connect.assert_called_once()
            mock_app.run.assert_called_once()

    def test_tinker_subcommand_calls_run_tinker(self):
        with patch('routemq.cli.tinker') as mock_tinker:
            self._run_with_argv(['tinker'])

            mock_tinker.assert_called_once()

    def test_tinker_alias_calls_run_tinker(self):
        with patch('routemq.cli.tinker') as mock_tinker:
            self._run_with_argv(['--tinker'])

            mock_tinker.assert_called_once()

    def test_queue_work_subcommand_passes_args(self):
        with patch('routemq.cli.queue_work') as mock_qw:
            self._run_with_argv(['queue-work', '--queue', 'emails', '--sleep', '5'])

            mock_qw.assert_called_once()
            _, kwargs = mock_qw.call_args
            self.assertEqual(kwargs['queue'], 'emails')
            self.assertEqual(kwargs['sleep'], 5)

    def test_queue_failed_subcommand_passes_filters(self):
        with patch('routemq.cli._cmd_queue_failed') as command:
            self._run_with_argv(['queue-failed', '--queue', 'emails', '--connection', 'redis'])

        command.assert_called_once_with(queue='emails', connection='redis')

    def test_queue_failed_show_subcommand_passes_id(self):
        with patch('routemq.cli._cmd_queue_failed_show') as command:
            self._run_with_argv(['queue-failed-show', 'abc123', '--connection', 'redis'])

        command.assert_called_once_with('abc123', connection='redis')

    def test_queue_retry_subcommand_passes_id(self):
        with patch('routemq.cli._cmd_queue_retry') as command:
            self._run_with_argv(['queue-retry', 'abc123', '--connection', 'redis'])

        command.assert_called_once_with('abc123', all_jobs=False, queue='default', connection='redis')

    def test_queue_retry_all_subcommand_passes_queue(self):
        with patch('routemq.cli._cmd_queue_retry') as command:
            self._run_with_argv(['queue-retry', '--all', '--queue', 'emails'])

        command.assert_called_once_with(None, all_jobs=True, queue='emails', connection=None)

    def test_queue_forget_subcommand_passes_id(self):
        with patch('routemq.cli._cmd_queue_forget') as command:
            self._run_with_argv(['queue-forget', 'abc123', '--connection', 'database'])

        command.assert_called_once_with('abc123', connection='database')

    def test_queue_flush_subcommand_passes_queue(self):
        with patch('routemq.cli._cmd_queue_flush') as command:
            self._run_with_argv(['queue-flush', '--queue', 'emails', '--connection', 'redis'])

        command.assert_called_once_with(queue='emails', connection='redis')

    def test_new_subcommand_calls_scaffolder(self):
        with patch('routemq.scaffold.run_scaffolder', return_value=0) as mock_scaffold:
            self._run_with_argv(['new', 'demo', '--yes', '--with-redis', '--package-manager', 'pip'])

        mock_scaffold.assert_called_once_with(
            'demo',
            yes=True,
            with_mysql=False,
            with_redis=True,
            with_queue=False,
            with_docker=False,
            package_manager='pip',
            no_input=False,
        )

    def test_init_alias_routes_to_new_with_dot(self):
        with patch('routemq.scaffold.run_scaffolder', return_value=0) as mock_scaffold:
            self._run_with_argv(['--init'])

        mock_scaffold.assert_called_once_with(
            '.',
            yes=True,
            with_mysql=False,
            with_redis=False,
            with_queue=False,
            with_docker=False,
            package_manager='uv',
            no_input=True,
        )

    def test_no_args_defaults_to_run(self):
        with patch('routemq.cli.create_app') as mock_create, patch('routemq.cli.create_env_file'):
            mock_app = MagicMock()
            mock_create.return_value = mock_app

            self._run_with_argv([])

            mock_app.run.assert_called_once()

    def test_run_subcommand_exits_on_connection_refused(self):
        with (
            patch('routemq.cli.create_app') as mock_create,
            patch('routemq.cli.create_env_file'),
            patch.dict(os.environ, {'LOG_FORMATTER': 'plain'}, clear=True),
            patch('sys.stderr', new_callable=io.StringIO) as mock_stderr,
        ):
            mock_app = MagicMock()
            mock_app.connect.side_effect = ConnectionRefusedError(111, 'Connection refused')
            mock_create.return_value = mock_app

            with self.assertRaises(SystemExit) as cm:
                self._run_with_argv(['run'])

            self.assertEqual(cm.exception.code, 1)
            mock_app.connect.assert_called_once()
            mock_app.run.assert_not_called()
            stderr_output = mock_stderr.getvalue()
            self.assertIn('localhost:1883', stderr_output)
            self.assertIn('broker', stderr_output.lower())

    def test_run_subcommand_exits_on_timeout_error(self):
        with (
            patch('routemq.cli.create_app') as mock_create,
            patch('routemq.cli.create_env_file'),
            patch.dict(os.environ, {'LOG_FORMATTER': 'plain'}, clear=True),
            patch('sys.stderr', new_callable=io.StringIO),
        ):
            mock_app = MagicMock()
            mock_app.connect.side_effect = TimeoutError('Connection timed out')
            mock_create.return_value = mock_app

            with self.assertRaises(SystemExit) as cm:
                self._run_with_argv(['run'])

            self.assertEqual(cm.exception.code, 1)
            mock_app.run.assert_not_called()

    def test_run_subcommand_exits_on_socket_gaierror(self):
        with (
            patch('routemq.cli.create_app') as mock_create,
            patch('routemq.cli.create_env_file'),
            patch.dict(os.environ, {'LOG_FORMATTER': 'plain'}, clear=True),
            patch('sys.stderr', new_callable=io.StringIO),
        ):
            mock_app = MagicMock()
            mock_app.connect.side_effect = socket.gaierror(8, 'nodename nor servname provided')
            mock_create.return_value = mock_app

            with self.assertRaises(SystemExit) as cm:
                self._run_with_argv(['run'])

            self.assertEqual(cm.exception.code, 1)
            mock_app.run.assert_not_called()

    def test_run_subcommand_exits_on_network_oserror(self):
        with (
            patch('routemq.cli.create_app') as mock_create,
            patch('routemq.cli.create_env_file'),
            patch.dict(os.environ, {'LOG_FORMATTER': 'plain'}, clear=True),
            patch('sys.stderr', new_callable=io.StringIO),
        ):
            mock_app = MagicMock()
            mock_app.connect.side_effect = OSError(errno.ENETUNREACH, 'Network is unreachable')
            mock_create.return_value = mock_app

            with self.assertRaises(SystemExit) as cm:
                self._run_with_argv(['run'])

            self.assertEqual(cm.exception.code, 1)
            mock_app.run.assert_not_called()

    def test_run_subcommand_propagates_non_network_oserror(self):
        with patch('routemq.cli.create_app') as mock_create, patch('routemq.cli.create_env_file'):
            mock_app = MagicMock()
            mock_app.connect.side_effect = OSError(errno.ENOSPC, 'No space left on device')
            mock_create.return_value = mock_app

            with self.assertRaises(OSError) as cm:
                self._run_with_argv(['run'])

            self.assertEqual(cm.exception.errno, errno.ENOSPC)
            mock_app.run.assert_not_called()

    def test_run_subcommand_propagates_programmer_errors(self):
        with patch('routemq.cli.create_app') as mock_create, patch('routemq.cli.create_env_file'):
            mock_app = MagicMock()
            mock_app.connect.side_effect = AttributeError("'NoneType' object has no attribute 'foo'")
            mock_create.return_value = mock_app

            with self.assertRaises(AttributeError):
                self._run_with_argv(['run'])

            mock_app.run.assert_not_called()

    def test_no_args_defaults_to_run_exits_on_network_error(self):
        with (
            patch('routemq.cli.create_app') as mock_create,
            patch('routemq.cli.create_env_file'),
            patch.dict(os.environ, {'LOG_FORMATTER': 'plain'}, clear=True),
            patch('sys.stderr', new_callable=io.StringIO),
        ):
            mock_app = MagicMock()
            mock_app.connect.side_effect = ConnectionRefusedError(111, 'Connection refused')
            mock_create.return_value = mock_app

            with self.assertRaises(SystemExit) as cm:
                self._run_with_argv([])

            self.assertEqual(cm.exception.code, 1)
            mock_app.connect.assert_called_once()
            mock_app.run.assert_not_called()

    def test_run_subcommand_logs_network_error_when_json_logging_enabled(self):
        with (
            patch('routemq.cli.create_app') as mock_create,
            patch('routemq.cli.create_env_file'),
            patch('routemq.cli.logger.error') as log_error,
            patch.dict(os.environ, {'LOG_FORMATTER': 'json', 'MQTT_BROKER': 'mqtt', 'MQTT_PORT': '1884'}, clear=True),
            patch('sys.stderr', new_callable=io.StringIO) as mock_stderr,
        ):
            mock_app = MagicMock()
            mock_app.connect.side_effect = ConnectionRefusedError(111, 'Connection refused')
            mock_create.return_value = mock_app

            with self.assertRaises(SystemExit) as cm:
                self._run_with_argv(['run'])

            self.assertEqual(cm.exception.code, 1)
            log_error.assert_called_once()
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(log_error.call_args.kwargs['extra']['broker'], 'mqtt')

    def test_network_startup_error_classifier_preserves_cli_cases(self):
        self.assertTrue(is_network_startup_error(ConnectionRefusedError(111, 'Connection refused')))
        self.assertTrue(is_network_startup_error(TimeoutError('Connection timed out')))
        self.assertTrue(is_network_startup_error(socket.gaierror(8, 'nodename nor servname provided')))
        self.assertTrue(is_network_startup_error(OSError(errno.ENETUNREACH, 'Network is unreachable')))
        self.assertFalse(is_network_startup_error(OSError(errno.ENOSPC, 'No space left on device')))


class _CliQueueDriver(QueueDriver):
    async def push(self, payload: str, queue: str = 'default', delay: int = 0) -> None:
        return None

    async def pop(self, queue: str = 'default') -> dict | None:
        return None

    async def release(self, job_id: int | str, queue: str, delay: int = 0) -> None:
        return None

    async def delete(self, job_id: int | str, queue: str) -> None:
        return None

    async def failed(self, connection: str, queue: str, payload: str, exception: str) -> None:
        return None

    async def size(self, queue: str = 'default') -> int:
        return 0


class TestQueueWorkHealthLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        original_cwd = os.getcwd()
        os.chdir(workdir.name)
        self.addCleanup(os.chdir, original_cwd)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.env = {'HEALTH_HTTP_ENABLED': 'true', 'HEALTH_HTTP_HOST': '0.0.0.0', 'HEALTH_HTTP_PORT': str(self.port)}
        self.app = MagicMock()
        self.app._initialize_connections = AsyncMock()
        self.app._cleanup_connections = AsyncMock()
        self.signal_handlers: dict[int, object] = {}
        self._manager_instance = QueueManager._instance
        self._manager_driver = QueueManager._driver
        QueueManager._instance = None
        QueueManager._driver = None
        self.addCleanup(setattr, QueueManager, '_instance', self._manager_instance)
        self.addCleanup(setattr, QueueManager, '_driver', self._manager_driver)

    def _run_queue_work(self, *, get_driver: MagicMock) -> None:
        from routemq.cli import main

        # Fresh singleton (reset in setUp); the CLI worker's QueueManager() returns this same instance.
        queue_manager = QueueManager()
        # --max-time bounds the worker if the scripted driver/signal path is never reached.
        argv = ['routemq', 'queue-work', '--queue', 'emails', '--sleep', '1', '--max-time', '10']
        with (
            patch('routemq.cli.create_app', return_value=self.app),
            patch('routemq.cli.create_env_file'),
            patch('signal.signal', side_effect=self.signal_handlers.__setitem__),
            patch('routemq.queue.queue_worker.mark_worker_dead'),
            patch.object(queue_manager, 'get_driver', get_driver),
            patch.object(queue_manager, 'validate_connection', AsyncMock(return_value='redis')),
            patch.dict(os.environ, self.env),
            patch.object(sys, 'argv', argv),
        ):
            main()

    def _assert_port_closed(self) -> None:
        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(('127.0.0.1', self.port), timeout=1).close()

    def test_queue_work_serves_worker_readiness_until_sigterm_shutdown(self) -> None:
        probes: list[int] = []
        handlers = self.signal_handlers

        class ProbingDriver(_CliQueueDriver):
            async def pop(self, queue: str = 'default') -> dict | None:
                probes.append(await asyncio.to_thread(healthcheck.main))
                handler = handlers.get(signal.SIGTERM)
                if callable(handler):
                    handler(signal.SIGTERM, None)
                probes.append(await asyncio.to_thread(healthcheck.main))
                return None

        self._run_queue_work(get_driver=MagicMock(return_value=ProbingDriver()))

        self.assertEqual(probes, [0, 1])
        self.app._initialize_connections.assert_awaited_once()
        self.app._cleanup_connections.assert_awaited_once()
        self._assert_port_closed()

    def test_queue_work_reports_not_ready_during_startup_and_stops_server_on_startup_failure(self) -> None:
        probes: list[int] = []

        def failing_get_driver(connection: str | None = None) -> QueueDriver:
            probes.append(healthcheck.main())
            raise RuntimeError('database disabled')

        with self.assertRaisesRegex(RuntimeError, 'database disabled'):
            self._run_queue_work(get_driver=MagicMock(side_effect=failing_get_driver))

        self.assertEqual(probes, [1])
        self.app._cleanup_connections.assert_awaited_once()
        self._assert_port_closed()


if __name__ == '__main__':
    unittest.main()
