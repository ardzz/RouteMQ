import sys
import unittest
from unittest.mock import MagicMock, patch


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

    def test_queue_work_subcommand_passes_args(self):
        with patch('routemq.cli.queue_work') as mock_qw:
            self._run_with_argv(['queue-work', '--queue', 'emails', '--sleep', '5'])

            mock_qw.assert_called_once()
            _, kwargs = mock_qw.call_args
            self.assertEqual(kwargs['queue'], 'emails')
            self.assertEqual(kwargs['sleep'], 5)

    def test_new_subcommand_stub_prints_message(self):
        with patch('builtins.print') as mock_print:
            self._run_with_argv(['new', 'demo'])

            outputs = ' '.join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
            self.assertIn('Phase C', outputs)

    def test_init_alias_routes_to_new_with_dot(self):
        with patch('routemq.cli.setup_example') as mock_setup, patch('routemq.cli.create_env_file') as mock_env:
            self._run_with_argv(['--init'])

            mock_env.assert_called_once()
            mock_setup.assert_called_once()

    def test_no_args_defaults_to_run(self):
        with patch('routemq.cli.create_app') as mock_create, patch('routemq.cli.create_env_file'):
            mock_app = MagicMock()
            mock_create.return_value = mock_app

            self._run_with_argv([])

            mock_app.run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
