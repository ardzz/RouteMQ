import json
import os
import socket
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from routemq.health import HealthServer, HealthStatus, health_server_from_env


class HealthStatusTests(unittest.TestCase):
    def test_health_is_alive_without_dependency_checks(self) -> None:
        status = HealthStatus()

        code, payload = status.health_payload()

        self.assertEqual(code, 200)
        self.assertTrue(payload['alive'])

    def test_readiness_requires_startup_mqtt_and_not_shutting_down(self) -> None:
        status = HealthStatus(startup_complete=True, mqtt_connected=True)

        ready_code, ready_payload = status.readiness_payload()
        status.shutting_down = True
        down_code, down_payload = status.readiness_payload()

        self.assertEqual(ready_code, 200)
        self.assertEqual(ready_payload['status'], 'ready')
        self.assertEqual(down_code, 503)
        self.assertEqual(down_payload['status'], 'not_ready')


class HealthServerTests(unittest.TestCase):
    def _free_port(self) -> int:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            return sock.getsockname()[1]

    def test_http_server_exposes_health_and_ready(self) -> None:
        status = HealthStatus(startup_complete=True, mqtt_connected=True)
        server = HealthServer(status, port=self._free_port())
        server.start()
        self.addCleanup(server.stop)

        with urlopen(f'http://127.0.0.1:{server.port}/health', timeout=2) as response:
            health = json.loads(response.read().decode('utf-8'))
        with urlopen(f'http://127.0.0.1:{server.port}/ready', timeout=2) as response:
            ready = json.loads(response.read().decode('utf-8'))

        self.assertEqual(health['status'], 'ok')
        self.assertEqual(ready['status'], 'ready')

    def test_health_server_from_env_returns_none_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            server = health_server_from_env(HealthStatus())

        self.assertIsNone(server)

    def test_health_server_from_env_uses_central_settings_parser(self) -> None:
        with patch.dict(
            os.environ,
            {'HEALTH_HTTP_ENABLED': 'yes', 'HEALTH_HTTP_HOST': '0.0.0.0', 'HEALTH_HTTP_PORT': 'invalid'},
            clear=True,
        ):
            server = health_server_from_env(HealthStatus())

        assert server is not None
        self.assertEqual(server.host, '0.0.0.0')
        self.assertEqual(server.port, 8080)


if __name__ == '__main__':
    unittest.main()
