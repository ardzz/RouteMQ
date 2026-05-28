import errno
import io
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

from routemq.mqtt_utils import is_network_startup_error


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

    def test_network_startup_error_classifier_preserves_cli_cases(self):
        self.assertTrue(is_network_startup_error(ConnectionRefusedError(111, 'Connection refused')))
        self.assertTrue(is_network_startup_error(TimeoutError('Connection timed out')))
        self.assertTrue(is_network_startup_error(socket.gaierror(8, 'nodename nor servname provided')))
        self.assertTrue(is_network_startup_error(OSError(errno.ENETUNREACH, 'Network is unreachable')))
        self.assertFalse(is_network_startup_error(OSError(errno.ENOSPC, 'No space left on device')))


if __name__ == '__main__':
    unittest.main()
