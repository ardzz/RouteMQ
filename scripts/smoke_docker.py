#!/usr/bin/env python3
"""Strict runtime smoke test for the RouteMQ production Docker image.

Usage:
    python scripts/smoke_docker.py --image <image-tag>

The image must already exist locally; this script never builds or pulls it. The image's default command and a
queue worker run against private Mosquitto, Redis, and MySQL containers on an internal Docker network with no
published ports, no host .env, and no internet route, so any runtime install or download fails. The read-only
fixture in tests/docker_smoke registers an MQTT route that dispatches a job; the worker stores a MySQL row keyed
by the message ID. Redis and database queue modes run serially and assert real results, readiness after idling
past the Redis worker metadata TTL, unready and recovered states across owned backend outages, and clean SIGTERM
shutdown. Every container and network carries this run's label and is removed on exit. Missing prerequisites,
failed assertions, and timeouts exit non-zero; nothing is skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[1] / 'tests' / 'docker_smoke'

# Immutable manifest-index digests observed with `docker buildx imagetools inspect <tag>`.
MOSQUITTO_IMAGE = 'eclipse-mosquitto@sha256:199ea8ef2e35ec2b1b37e59cfd1dbae538ed4dfa4a2251a121a52215a6248a21'  # 2.0.22
REDIS_IMAGE = 'redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499'  # 7.4.11-alpine
MYSQL_IMAGE = 'mysql@sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b'  # 8.0.46

# Hard memory caps with swap equal to memory, so no container can grow into swap.
MEMORY = {'mqtt': '64m', 'redis': '128m', 'mysql': '1g', 'runtime': '256m'}

RUN_LABEL = 'io.routemq.smoke-run'
TOTAL_TIMEOUT = 1500
PULL_TIMEOUT = 600
SERVICE_TIMEOUT = 90
MYSQL_TIMEOUT = 240
READY_TIMEOUT = 120
TRANSITION_TIMEOUT = 60
RESULT_TIMEOUT = 60
STOP_TIMEOUT = 30
IDLE_SECONDS = 35  # Longer than the 30-second expiry of idle Redis worker metadata.
POLL_SECONDS = 1.0

# Faster Docker health polling than the image default; the image's own HEALTHCHECK command is kept.
HEALTH_OPTIONS = ('--health-interval=2s', '--health-timeout=10s', '--health-retries=2')

DB_NAME = 'routemq_smoke'
DB_USER = 'routemq'
TOPIC_TEMPLATE = 'routemq-smoke/messages/{message_id}'
WORKER_COMMAND = ('/opt/venv/bin/routemq', '--queue-work', '--queue', 'default', '--sleep', '3')
SCHEMA_SQL = (
    'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() '
    "AND table_name IN ('queue_jobs', 'queue_failed_jobs', 'smoke_results')"
)

IMAGE_REPORT = '\n'.join(
    [
        'import importlib.util, json, os, shutil, sys',
        'find = importlib.util.find_spec',
        'report = {',
        "    'uid': os.getuid(),",
        "    'venv': sys.prefix != sys.base_prefix,",
        "    'missing_extras': [m for m in ('redis', 'clickhouse_connect', 'prometheus_client') if find(m) is None],",
        "    'dev_packages': [m for m in ('pytest', 'ruff', 'mypy') if find(m) is not None],",
        "    'uv': [p for p in (shutil.which('uv'), shutil.which('uvx')) if p],",
        '}',
        'print(json.dumps(report))',
    ]
)


def log(message: str) -> None:
    print(f'[smoke {time.strftime("%H:%M:%S")}] {message}', flush=True)


class SmokeFailure(Exception):
    """A smoke prerequisite, assertion, or deadline failed."""


class DockerSmoke:
    def __init__(self, image: str) -> None:
        self.image = image
        run_id = f'{os.getpid()}-{secrets.token_hex(4)}'
        self.prefix = f'routemq-smoke-{run_id}'
        self.label = f'{RUN_LABEL}={run_id}'
        self.network = f'{self.prefix}-net'
        self.deadline = time.monotonic() + TOTAL_TIMEOUT
        self.staging: Path | None = None
        self.fixtures = Path()
        self.probe_command: list[str] = []
        db_password = secrets.token_hex(16)
        # Secrets reach containers by name (`--env NAME`), so they never appear in process arguments.
        self.env = {
            **os.environ,
            'MYSQL_ROOT_PASSWORD': secrets.token_hex(16),
            'MYSQL_PASSWORD': db_password,
            'MYSQL_PWD': db_password,
            'DB_PASS': db_password,
        }

    def name(self, role: str) -> str:
        return f'{self.prefix}-{role}'

    def docker(
        self, *args: str, timeout: float = 60, check: bool = True, bounded: bool = True
    ) -> subprocess.CompletedProcess[str]:
        if bounded:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise SmokeFailure(f'overall {TOTAL_TIMEOUT}s smoke deadline exceeded')
            timeout = min(timeout, remaining)
        try:
            result = subprocess.run(
                ['docker', *args], env=self.env, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise SmokeFailure(f'docker {args[0]} timed out after {timeout:.0f}s') from exc
        except OSError as exc:
            raise SmokeFailure(f'cannot run docker: {exc}') from exc
        if check and result.returncode != 0:
            raise SmokeFailure(f'docker {" ".join(args[:2])} exited {result.returncode}: {result.stderr.strip()}')
        return result

    def wait_until(self, description: str, condition: Callable[[], bool], timeout: float) -> None:
        limit = min(time.monotonic() + timeout, self.deadline)
        while not condition():
            if time.monotonic() >= limit:
                raise SmokeFailure(f'timed out after {timeout:.0f}s waiting for {description}')
            time.sleep(POLL_SECONDS)
        log(f'ok: {description}')

    def run(self) -> None:
        self.check_prerequisites()
        self.check_image()
        self.stage_fixtures()
        self.start_services()
        self.exercise_redis_mode()
        self.exercise_database_mode()

    def check_prerequisites(self) -> None:
        if shutil.which('docker') is None:
            raise SmokeFailure('docker CLI not found on PATH')
        if not FIXTURE_DIR.is_dir():
            raise SmokeFailure(f'smoke fixture directory is missing: {FIXTURE_DIR}')
        server = self.docker('version', '--format', '{{.Server.Version}}', timeout=30).stdout.strip()
        log(f'Docker server {server}')

    def check_image(self) -> None:
        inspected = self.docker('image', 'inspect', '--format', '{{json .Config}}', self.image, timeout=30)
        test = (json.loads(inspected.stdout).get('Healthcheck') or {}).get('Test') or []
        if len(test) > 1 and test[0] == 'CMD':
            self.probe_command = test[1:]
        elif len(test) == 2 and test[0] == 'CMD-SHELL':
            self.probe_command = ['/bin/sh', '-c', test[1]]
        else:
            raise SmokeFailure(f'{self.image} defines no usable HEALTHCHECK: {test!r}')

        args = ['run', '--rm', '--name', self.name('inspect'), '--label', self.label, '--network', 'none']
        args += ['--memory', MEMORY['runtime'], '--memory-swap', MEMORY['runtime'], '--entrypoint', 'python']
        output = self.docker(*args, self.image, '-c', IMAGE_REPORT, timeout=120).stdout
        try:
            report = json.loads(output.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise SmokeFailure(f'unreadable image report: {output!r}') from exc

        problems = []
        if report['uid'] == 0:
            problems.append('runs as root')
        if not report['venv']:
            problems.append('`python` on PATH is not the image virtualenv')
        if report['missing_extras']:
            problems.append(f'missing runtime extras {report["missing_extras"]}')
        if report['dev_packages']:
            problems.append(f'dev packages installed {report["dev_packages"]}')
        if report['uv']:
            problems.append(f'uv present at runtime {report["uv"]}')
        if problems:
            raise SmokeFailure(f'{self.image}: ' + '; '.join(problems))
        log(f'ok: image runs as uid {report["uid"]} from its virtualenv with the runtime extras and without uv')

    def stage_fixtures(self) -> None:
        # Copy with explicit modes so container users can read the mounts regardless of the checkout umask.
        self.staging = Path(tempfile.mkdtemp(prefix=f'{self.prefix}-'))
        self.fixtures = self.staging / 'fixture'
        shutil.copytree(FIXTURE_DIR, self.fixtures, ignore=shutil.ignore_patterns('__pycache__', '*.py[cod]'))
        for path in (self.fixtures, *self.fixtures.rglob('*')):
            path.chmod(0o755 if path.is_dir() else 0o644)
        if ',' in str(self.fixtures):
            raise SmokeFailure(f'fixture staging path cannot contain commas: {self.fixtures}')

    def mount(self, source: str, target: str) -> list[str]:
        return ['--mount', f'type=bind,source={self.fixtures / source},target={target},readonly']

    def start(
        self,
        role: str,
        image: str,
        *,
        memory: str,
        env: Mapping[str, str] | None = None,
        secret_env: Sequence[str] = (),
        options: Sequence[str] = (),
        command: Sequence[str] = (),
    ) -> None:
        args = ['run', '--detach', '--name', self.name(role), '--hostname', role, '--label', self.label]
        args += ['--network', self.network, '--network-alias', role, '--memory', memory, '--memory-swap', memory]
        for key, value in (env or {}).items():
            args += ['--env', f'{key}={value}']
        for key in secret_env:
            args += ['--env', key]
        self.docker(*args, *options, image, *command)
        log(f'started {role}')

    def start_services(self) -> None:
        for reference in (MOSQUITTO_IMAGE, REDIS_IMAGE, MYSQL_IMAGE):
            if self.docker('image', 'inspect', reference, check=False, timeout=30).returncode != 0:
                log(f'pulling {reference}')
                self.docker('pull', '--quiet', reference, timeout=PULL_TIMEOUT)
        self.docker('network', 'create', '--internal', '--label', self.label, self.network)
        self.start(
            'mqtt',
            MOSQUITTO_IMAGE,
            memory=MEMORY['mqtt'],
            options=self.mount('mosquitto.conf', '/mosquitto/config/mosquitto.conf'),
        )
        self.start('redis', REDIS_IMAGE, memory=MEMORY['redis'])
        self.start(
            'mysql',
            MYSQL_IMAGE,
            memory=MEMORY['mysql'],
            env={'MYSQL_DATABASE': DB_NAME, 'MYSQL_USER': DB_USER},
            secret_env=('MYSQL_ROOT_PASSWORD', 'MYSQL_PASSWORD'),
            options=self.mount('mysql/schema.sql', '/docker-entrypoint-initdb.d/schema.sql'),
            # Same authentication plugin as the MySQL service in the root docker-compose.yml.
            command=('--default-authentication-plugin=mysql_native_password',),
        )
        self.wait_service('mqtt', SERVICE_TIMEOUT)
        self.wait_service('redis', SERVICE_TIMEOUT)
        self.wait_service('mysql', MYSQL_TIMEOUT)

    def exec_output(self, role: str, *command: str, env: Sequence[str] = ()) -> str | None:
        env_args = [arg for key in env for arg in ('--env', key)]
        result = self.docker('exec', *env_args, self.name(role), *command, check=False, timeout=30)
        return result.stdout.strip() if result.returncode == 0 else None

    def mysql_query(self, sql: str) -> str | None:
        return self.exec_output(
            'mysql',
            'mysql',
            '--protocol=TCP',
            '--host=127.0.0.1',
            f'--user={DB_USER}',
            f'--database={DB_NAME}',
            '--batch',
            '--skip-column-names',
            f'--execute={sql}',
            env=('MYSQL_PWD',),
        )

    def service_ready(self, role: str) -> bool:
        self.running(role)
        if role == 'mqtt':
            return self.exec_output('mqtt', 'mosquitto_pub', '-h', '127.0.0.1', '-t', 'smoke', '-m', '1') is not None
        if role == 'redis':
            return self.exec_output('redis', 'redis-cli', 'ping') == 'PONG'
        return self.mysql_query(SCHEMA_SQL) == '3'

    def wait_service(self, role: str, timeout: float) -> None:
        self.wait_until(f'{role} accepting connections', lambda: self.service_ready(role), timeout)

    def state(self, role: str) -> dict:
        return json.loads(self.docker('container', 'inspect', '--format', '{{json .State}}', self.name(role)).stdout)

    def running(self, role: str) -> dict:
        state = self.state(role)
        if not state.get('Running'):
            raise SmokeFailure(
                f'{role} stopped unexpectedly: exit code {state.get("ExitCode")}, '
                f'OOMKilled={state.get("OOMKilled")}, error={state.get("Error")!r}'
            )
        return state

    def health(self, role: str) -> str:
        health = self.running(role).get('Health')
        if not health:
            raise SmokeFailure(f'{role} has no Docker health status')
        return health['Status']

    def wait_health(self, role: str, status: str, timeout: float) -> None:
        self.wait_until(f'{role} Docker health {status}', lambda: self.health(role) == status, timeout)

    def probe(self, role: str) -> int:
        return self.docker('exec', self.name(role), *self.probe_command, check=False, timeout=30).returncode

    def assert_ready(self, *roles: str) -> None:
        for role in roles:
            status = self.health(role)
            code = self.probe(role)
            if status != 'healthy' or code != 0:
                raise SmokeFailure(f'{role} not ready: Docker health {status}, probe exit {code}')

    def start_runtime(self, connection: str) -> tuple[str, str]:
        env = {
            'MQTT_BROKER': 'mqtt',
            'MQTT_PORT': '1883',
            'ENABLE_MYSQL': 'true',
            'DB_HOST': 'mysql',
            'DB_PORT': '3306',
            'DB_NAME': DB_NAME,
            'DB_USER': DB_USER,
            'ENABLE_REDIS': str(connection == 'redis').lower(),
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '6379',
            'QUEUE_CONNECTION': connection,
            'ENABLE_TSDB': 'false',
        }
        options = (*HEALTH_OPTIONS, *self.mount('app', '/app/app'))
        app, worker = f'app-{connection}', f'worker-{connection}'
        # No command override: the app container runs the image's default CMD.
        self.start(app, self.image, memory=MEMORY['runtime'], env=env, secret_env=('DB_PASS',), options=options)
        self.start(
            worker,
            self.image,
            memory=MEMORY['runtime'],
            env=env,
            secret_env=('DB_PASS',),
            options=options,
            command=WORKER_COMMAND,
        )
        self.wait_health(app, 'healthy', READY_TIMEOUT)
        self.wait_health(worker, 'healthy', READY_TIMEOUT)
        return app, worker

    def assert_ready_while_idle(self, *roles: str) -> None:
        log(f'idling {IDLE_SECONDS}s, past the Redis worker metadata TTL; readiness must hold')
        end = time.monotonic() + IDLE_SECONDS
        if end > self.deadline:
            raise SmokeFailure('overall smoke deadline leaves no time for the idle check')
        while time.monotonic() < end:
            for role in roles:
                if self.health(role) != 'healthy':
                    raise SmokeFailure(f'{role} lost readiness while idle')
            time.sleep(5)
        self.assert_ready(*roles)
        log('ok: app and worker stayed ready while idle')

    def assert_message_processed(self, worker: str) -> None:
        message_id = uuid.uuid4().hex
        value = secrets.token_hex(8)
        topic = TOPIC_TEMPLATE.format(message_id=message_id)
        publish = ('mosquitto_pub', '-h', '127.0.0.1', '-q', '1', '-t', topic, '-m', json.dumps({'value': value}))
        self.docker('exec', self.name('mqtt'), *publish)
        expected = f'{value}\t{worker}'
        query = f"SELECT `value`, worker_hostname FROM smoke_results WHERE message_id = '{message_id}'"
        observed: list[str | None] = [None]

        def stored() -> bool:
            self.running(worker)
            observed[0] = self.mysql_query(query)
            return observed[0] == expected

        try:
            self.wait_until(f'MySQL result of message {message_id} from {worker}', stored, RESULT_TIMEOUT)
        except SmokeFailure as exc:
            raise SmokeFailure(f'{exc}; last row {observed[0]!r}, expected {expected!r}') from None

    def assert_outage_and_recovery(self, service: str, dependent: str, recovery_timeout: float) -> None:
        log(f'stopping {service}; {dependent} must become unready')
        self.docker('stop', '--time', str(STOP_TIMEOUT), self.name(service), timeout=STOP_TIMEOUT + 30)
        self.wait_health(dependent, 'unhealthy', TRANSITION_TIMEOUT)
        if self.probe(dependent) == 0:
            raise SmokeFailure(f'{dependent} readiness probe passed while {service} was stopped')
        log(f'restarting {service}; {dependent} must recover')
        self.docker('start', self.name(service))
        self.wait_service(service, recovery_timeout)
        self.wait_health(dependent, 'healthy', READY_TIMEOUT)

    def assert_graceful_stop(self, role: str) -> None:
        self.docker('stop', '--time', str(STOP_TIMEOUT), self.name(role), timeout=STOP_TIMEOUT + 30)
        state = self.state(role)
        if state.get('Running') or state.get('ExitCode') != 0 or state.get('OOMKilled'):
            raise SmokeFailure(
                f'{role} did not exit cleanly on SIGTERM: exit code {state.get("ExitCode")}, '
                f'OOMKilled={state.get("OOMKilled")}'
            )
        log(f'ok: {role} exited 0 on SIGTERM')

    def exercise_redis_mode(self) -> None:
        log('== Redis queue mode')
        app, worker = self.start_runtime('redis')
        self.assert_ready_while_idle(app, worker)
        self.assert_message_processed(worker)
        self.assert_outage_and_recovery('redis', worker, SERVICE_TIMEOUT)
        self.assert_message_processed(worker)
        self.assert_outage_and_recovery('mqtt', app, SERVICE_TIMEOUT)
        self.assert_message_processed(worker)
        self.assert_graceful_stop(worker)
        self.assert_graceful_stop(app)

    def exercise_database_mode(self) -> None:
        log('== database queue mode; Redis is removed and disabled')
        self.docker('rm', '--force', '--volumes', self.name('redis'))
        app, worker = self.start_runtime('database')
        self.assert_message_processed(worker)
        self.assert_outage_and_recovery('mysql', worker, MYSQL_TIMEOUT)
        self.assert_message_processed(worker)
        self.assert_graceful_stop(worker)
        self.assert_graceful_stop(app)

    def owned(self, *listing: str) -> list[str]:
        return self.docker(*listing, '--quiet', '--filter', f'label={self.label}', bounded=False).stdout.split()

    def dump_diagnostics(self) -> None:
        try:
            for container in self.owned('container', 'ls', '--all'):
                inspect = ('container', 'inspect', '--format', '{{.Name}} {{json .State}}', container)
                state = self.docker(*inspect, check=False, bounded=False)
                logs = self.docker('logs', '--tail', '60', container, check=False, bounded=False)
                print(f'----- {state.stdout.strip()}', file=sys.stderr)
                print(f'{logs.stdout}{logs.stderr}'.rstrip(), file=sys.stderr, flush=True)
        except SmokeFailure as exc:
            log(f'diagnostics incomplete: {exc}')

    def teardown(self) -> list[str]:
        """Remove only this run's labelled containers, their anonymous volumes, and its network."""
        errors = []
        try:
            containers = self.owned('container', 'ls', '--all')
            if containers:
                self.docker('rm', '--force', '--volumes', *containers, timeout=120, bounded=False)
        except SmokeFailure as exc:
            errors.append(str(exc))
        try:
            networks = self.owned('network', 'ls')
            if networks:
                self.docker('network', 'rm', *networks, bounded=False)
        except SmokeFailure as exc:
            errors.append(str(exc))
        if self.staging is not None:
            shutil.rmtree(self.staging, ignore_errors=True)
        return errors


def _interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt(f'signal {signum}')


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Strict runtime smoke test for a locally built RouteMQ image.')
    parser.add_argument('--image', required=True, help='local image tag to test; it is never built or pulled here')
    args = parser.parse_args(argv)
    if args.image.startswith('-'):
        parser.error('--image must be an image reference')

    signal.signal(signal.SIGTERM, _interrupt)
    smoke = DockerSmoke(args.image)
    status = 1
    try:
        smoke.run()
        status = 0
    except SmokeFailure as exc:
        log(f'FAIL: {exc}')
        smoke.dump_diagnostics()
    except KeyboardInterrupt:
        log('FAIL: interrupted')
        status = 130
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        errors = smoke.teardown()
    for error in errors:
        log(f'FAIL: teardown: {error}')
    if errors and status == 0:
        status = 1
    if status == 0:
        log('PASS: default app CMD and Redis/database queue workers processed MQTT jobs with real readiness')
    return status


if __name__ == '__main__':
    sys.exit(main())
