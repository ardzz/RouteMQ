import io
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import check_install_profile


class InstallProfileTests(unittest.TestCase):
    def _write_wheel(self, directory: Path, *, extras: tuple[str, ...] = ()) -> Path:
        wheel = directory / 'routemq-0.24.0-py3-none-any.whl'
        metadata = '\n'.join(
            [
                'Metadata-Version: 2.4',
                'Name: routemq',
                'Version: 0.24.0',
                *(f'Provides-Extra: {extra}' for extra in extras),
                '',
            ]
        )
        with zipfile.ZipFile(wheel, 'w') as archive:
            archive.writestr('routemq-0.24.0.dist-info/METADATA', metadata)
        return wheel

    def test_validate_profile_accepts_only_supported_profiles(self) -> None:
        for profile in ('base', 'redis', 'postgres', 'clickhouse', 'all'):
            with self.subTest(profile=profile):
                self.assertEqual(check_install_profile.validate_profile(profile), profile)

        with self.assertRaisesRegex(ValueError, 'Unsupported install profile.*unknown'):
            check_install_profile.validate_profile('unknown')

    def test_resolve_wheel_requires_exactly_one_wheel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dist = Path(tmpdir)
            with self.assertRaisesRegex(RuntimeError, 'exactly one.*dist/.*found 0'):
                check_install_profile.resolve_wheel(dist)

            expected = self._write_wheel(dist)
            self.assertEqual(check_install_profile.resolve_wheel(dist), expected)

            (dist / 'another.whl').touch()
            with self.assertRaisesRegex(RuntimeError, 'exactly one.*dist/.*found 2'):
                check_install_profile.resolve_wheel(dist)

    def test_validate_wheel_profile_uses_provides_extra_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dist = Path(tmpdir)
            wheel = self._write_wheel(dist, extras=('redis', 'all'))

            check_install_profile.validate_wheel_profile(wheel, 'base')
            check_install_profile.validate_wheel_profile(wheel, 'redis')
            with self.assertRaisesRegex(RuntimeError, 'postgres.*Provides-Extra'):
                check_install_profile.validate_wheel_profile(wheel, 'postgres')

    def test_requirement_uses_one_named_direct_wheel_profile(self) -> None:
        wheel = Path('/tmp/routemq build/routemq.whl')
        uri = wheel.resolve().as_uri()

        self.assertEqual(check_install_profile.install_requirement(wheel, 'base'), f'routemq @ {uri}')
        for profile in ('redis', 'postgres', 'clickhouse', 'all'):
            with self.subTest(profile=profile):
                self.assertEqual(
                    check_install_profile.install_requirement(wheel, profile),
                    f'routemq[{profile}] @ {uri}',
                )

    def test_run_checked_contextualizes_subprocess_failure(self) -> None:
        command = ['uv', 'venv', '--python', 'python3.12', '/tmp/profile']
        failure = subprocess.CalledProcessError(2, command)
        with patch('scripts.check_install_profile.subprocess.run', side_effect=failure) as run:
            with self.assertRaisesRegex(RuntimeError, 'create isolated environment.*uv venv.*exit code 2'):
                check_install_profile.run_checked(command, 'create isolated environment')

        run.assert_called_once_with(command, check=True)

    def test_run_checked_contextualizes_missing_executable(self) -> None:
        command = ['uv', 'venv', '--python', 'python3.12', '/tmp/profile']
        failure = FileNotFoundError('uv not found')
        with patch('scripts.check_install_profile.subprocess.run', side_effect=failure) as run:
            with self.assertRaisesRegex(RuntimeError, 'create isolated environment.*uv.*not found'):
                check_install_profile.run_checked(command, 'create isolated environment')

        run.assert_called_once_with(command, check=True)

    def test_check_profile_uses_isolated_venv_python_and_exact_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dist = Path(tmpdir)
            wheel = self._write_wheel(dist, extras=('redis',))

            def completed(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                stdout = '3.12.9\n' if kwargs.get('stdout') == subprocess.PIPE else None
                return subprocess.CompletedProcess(command, 0, stdout=stdout)

            output = io.StringIO()
            with (
                patch('scripts.check_install_profile.subprocess.run', side_effect=completed) as run,
                redirect_stdout(output),
            ):
                check_install_profile.check_profile('redis', 'python3.12', dist)

        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][0:4], ['uv', 'venv', '--python', 'python3.12'])
        venv_python = Path(commands[1][4])
        self.assertEqual(commands[1][0:3], ['uv', 'pip', 'install'])
        self.assertEqual(commands[1][3], '--python')
        self.assertEqual(commands[1][5], check_install_profile.install_requirement(wheel, 'redis'))
        self.assertNotIn('--no-deps', commands[1])
        self.assertEqual(commands[2][0:2], [str(venv_python), '-I'])
        self.assertIn('import redis', commands[2][3])
        self.assertEqual(commands[3][0:2], [str(venv_python), '-I'])
        self.assertTrue(all(call.kwargs.get('check') is True for call in run.call_args_list))
        self.assertEqual(output.getvalue().strip(), 'install-profile redis Python 3.12.9: PASS')

    def test_smoke_contract_covers_required_modules_and_features(self) -> None:
        smokes = check_install_profile.SMOKES
        for module in ('routemq.router', 'routemq.job', 'routemq.queue', 'routemq.model'):
            self.assertIn(f'import {module}', smokes['base'])
        for module in ('redis', 'routemq.redis_manager', 'routemq.queue.redis_queue'):
            self.assertIn(f'import {module}', smokes['redis'])
        self.assertIn('import asyncpg', smokes['postgres'])
        self.assertIn('DATABASE_URL', smokes['postgres'])
        self.assertIn('postgresql+asyncpg://', smokes['postgres'])
        self.assertIn('import clickhouse_connect', smokes['clickhouse'])
        self.assertIn('import routemq.tsdb.telemetry_adapters', smokes['clickhouse'])
        for smoke in (smokes['base'], smokes['redis'], smokes['postgres'], smokes['clickhouse']):
            self.assertIn(smoke, smokes['all'])
        self.assertIn('from routemq.telemetry import', smokes['all'])


if __name__ == '__main__':
    unittest.main()
