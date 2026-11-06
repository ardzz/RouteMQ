import argparse
import os
import shlex
import subprocess
import tempfile
import zipfile
from email.parser import Parser
from pathlib import Path


PROFILES = ('base', 'redis', 'postgres', 'clickhouse', 'all')

BASE_SMOKE = """import routemq.router
import routemq.job
import routemq.queue
import routemq.model"""

REDIS_SMOKE = """import redis
import routemq.redis_manager
import routemq.queue.redis_queue"""

POSTGRES_SMOKE = """import asyncpg
from routemq.settings import load_database_connection_settings
database = load_database_connection_settings({'DATABASE_URL': 'postgres://route:secret@localhost:5432/app'})
assert database.enabled
assert database.connection == 'postgres'
assert database.url == 'postgresql+asyncpg://route:secret@localhost:5432/app' """

CLICKHOUSE_SMOKE = """import clickhouse_connect
import routemq.tsdb.telemetry_adapters"""

TELEMETRY_SMOKE = """from routemq.telemetry import (
    InMemoryTelemetryAdapter,
    Measurement,
    NoopTelemetryAdapter,
    SchemaValidationIssue,
    SchemaValidationResult,
    TelemetryAdapter,
    TelemetryHealthStatus,
    TelemetryManager,
    TelemetryPoint,
    TelemetryQueueFull,
    WriteFailure,
    WriteResult,
    normalize_timestamp,
    telemetry,
)"""

SMOKES = {
    'base': BASE_SMOKE,
    'redis': REDIS_SMOKE,
    'postgres': POSTGRES_SMOKE,
    'clickhouse': CLICKHOUSE_SMOKE,
    'all': '\n'.join((BASE_SMOKE, REDIS_SMOKE, POSTGRES_SMOKE, CLICKHOUSE_SMOKE, TELEMETRY_SMOKE)),
}


def validate_profile(profile: str) -> str:
    if profile not in PROFILES:
        raise ValueError(f'Unsupported install profile {profile!r}; choose one of: {", ".join(PROFILES)}')
    return profile


def resolve_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob('*.whl'))
    if len(wheels) != 1:
        raise RuntimeError(f'Expected exactly one dist/*.whl in {dist_dir}, found {len(wheels)}')
    return wheels[0]


def _provided_extras(wheel: Path) -> set[str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_files = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
            if len(metadata_files) != 1:
                raise RuntimeError(f'Expected exactly one .dist-info/METADATA in {wheel}, found {len(metadata_files)}')
            metadata = Parser().parsestr(archive.read(metadata_files[0]).decode('utf-8'))
    except (OSError, UnicodeError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f'Unable to read wheel metadata from {wheel}: {exc}') from exc
    return {extra.lower() for extra in metadata.get_all('Provides-Extra', [])}


def validate_wheel_profile(wheel: Path, profile: str) -> None:
    validate_profile(profile)
    provided_extras = _provided_extras(wheel)
    if profile != 'base' and profile not in provided_extras:
        raise RuntimeError(f'Profile {profile!r} is absent from {wheel.name} Provides-Extra metadata')


def install_requirement(wheel: Path, profile: str) -> str:
    validate_profile(profile)
    extra = '' if profile == 'base' else f'[{profile}]'
    return f'routemq{extra} @ {wheel.resolve().as_uri()}'


def _subprocess_error(command: list[str], context: str, exc: subprocess.CalledProcessError | OSError) -> RuntimeError:
    rendered = shlex.join(command)
    if isinstance(exc, OSError):
        return RuntimeError(f'Failed to {context}: {rendered} could not be executed: {exc}')
    return RuntimeError(f'Failed to {context}: {rendered} exited with exit code {exc.returncode}')


def run_checked(command: list[str], context: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise _subprocess_error(command, context, exc) from exc


def run_checked_output(command: list[str], context: str) -> str:
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise _subprocess_error(command, context, exc) from exc
    return result.stdout.strip()


def check_profile(profile: str, python: str, dist_dir: Path | None = None) -> None:
    profile = validate_profile(profile)
    dist_dir = dist_dir or Path('dist')
    wheel = resolve_wheel(dist_dir)
    validate_wheel_profile(wheel, profile)

    with tempfile.TemporaryDirectory(prefix=f'routemq-{profile}-') as tmpdir:
        venv = Path(tmpdir) / '.venv'
        run_checked(['uv', 'venv', '--python', python, str(venv)], 'create isolated environment')
        venv_python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        requirement = install_requirement(wheel, profile)
        run_checked(
            ['uv', 'pip', 'install', '--python', str(venv_python), requirement],
            f'install profile {profile}',
        )
        run_checked(
            [str(venv_python), '-I', '-c', SMOKES[profile]],
            f'run profile {profile} smoke',
        )
        version = run_checked_output(
            [str(venv_python), '-I', '-c', 'import platform; print(platform.python_version())'],
            f'read profile {profile} Python version',
        )

    print(f'install-profile {profile} Python {version}: PASS')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    parser.add_argument('--python', required=True)
    args = parser.parse_args()
    try:
        check_profile(args.profile, args.python)
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f'install-profile {args.profile}: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
