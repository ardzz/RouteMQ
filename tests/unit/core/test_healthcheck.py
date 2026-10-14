import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from routemq import healthcheck
from routemq.health import HealthServer, HealthStatus

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _raw_ready_server(status: int, body: bytes) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(('127.0.0.1', _free_port()), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class HealthcheckProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        original_cwd = os.getcwd()
        os.chdir(workdir.name)
        self.addCleanup(os.chdir, original_cwd)
        self.workdir = Path(workdir.name)

    def _start(self, status: HealthStatus) -> HealthServer:
        server = HealthServer(status, port=_free_port())
        server.start()
        self.addCleanup(server.stop)
        return server

    def _start_raw(self, status: int, body: bytes) -> int:
        server = _raw_ready_server(status, body)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def _env(self, port: int, host: str = '127.0.0.1', enabled: str = 'true') -> dict[str, str]:
        return {'HEALTH_HTTP_ENABLED': enabled, 'HEALTH_HTTP_HOST': host, 'HEALTH_HTTP_PORT': str(port)}

    def test_ready_application_exits_zero_through_wildcard_bind_without_proxy(self) -> None:
        server = self._start(HealthStatus(startup_complete=True, mqtt_connected=True))
        env = self._env(server.port, host='0.0.0.0')
        env.update({'HTTP_PROXY': 'http://127.0.0.1:9', 'http_proxy': 'http://127.0.0.1:9', 'NO_PROXY': ''})

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(healthcheck.main(), 0)

    def test_not_ready_application_exits_one(self) -> None:
        server = self._start(HealthStatus(startup_complete=True, mqtt_connected=False))

        with patch.dict(os.environ, self._env(server.port), clear=True):
            self.assertEqual(healthcheck.main(), 1)

    def test_disabled_health_exits_one_even_when_a_ready_server_is_listening(self) -> None:
        server = self._start(HealthStatus(startup_complete=True, mqtt_connected=True))

        with patch.dict(os.environ, self._env(server.port, enabled='false'), clear=True):
            self.assertEqual(healthcheck.main(), 1)

    def test_unavailable_server_exits_one(self) -> None:
        with patch.dict(os.environ, self._env(_free_port()), clear=True):
            self.assertEqual(healthcheck.main(), 1)

    def test_malformed_success_responses_exit_one(self) -> None:
        for body in (b'not-json', b'["ready"]', json.dumps({'status': 'not_ready'}).encode()):
            with self.subTest(body=body):
                port = self._start_raw(200, body)
                with patch.dict(os.environ, self._env(port), clear=True):
                    self.assertEqual(healthcheck.main(), 1)

    def test_settings_from_working_directory_env_file_match_server_settings(self) -> None:
        server = self._start(HealthStatus(startup_complete=True, mqtt_connected=True))
        (self.workdir / '.env').write_text(f'HEALTH_HTTP_ENABLED=true\nHEALTH_HTTP_PORT={server.port}\n')

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(healthcheck.main(), 0)

    def test_module_command_exit_status_reflects_readiness(self) -> None:
        ready = self._start(HealthStatus(startup_complete=True, mqtt_connected=True))
        not_ready = self._start(HealthStatus(startup_complete=True, mqtt_connected=False))
        base_env = {key: value for key, value in os.environ.items() if not key.startswith('HEALTH_HTTP_')}
        base_env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(PROJECT_ROOT), base_env.get('PYTHONPATH')]))

        results = {}
        for name, server in (('ready', ready), ('not_ready', not_ready)):
            completed = subprocess.run(
                [sys.executable, '-m', 'routemq.healthcheck'],
                cwd=self.workdir,
                env={**base_env, **self._env(server.port)},
                capture_output=True,
                timeout=30,
                check=False,
            )
            results[name] = completed.returncode

        self.assertEqual(results, {'ready': 0, 'not_ready': 1})


if __name__ == '__main__':
    unittest.main()
