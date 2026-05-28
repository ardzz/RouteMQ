"""Stdlib-only health and readiness status for RouteMQ."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .settings import load_health_http_settings


@dataclass
class HealthStatus:
    """Mutable process health/readiness state."""

    alive: bool = True
    startup_complete: bool = False
    mqtt_connected: bool = False
    shutting_down: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def health_payload(self) -> tuple[int, dict[str, Any]]:
        payload = {'status': 'ok' if self.alive else 'down', 'alive': self.alive}
        payload.update(self.details)
        return (200 if self.alive else 503), payload

    def readiness_payload(self) -> tuple[int, dict[str, Any]]:
        ready = self.alive and self.startup_complete and self.mqtt_connected and not self.shutting_down
        payload = {
            'status': 'ready' if ready else 'not_ready',
            'alive': self.alive,
            'startup_complete': self.startup_complete,
            'mqtt_connected': self.mqtt_connected,
            'shutting_down': self.shutting_down,
        }
        payload.update(self.details)
        return (200 if ready else 503), payload


class HealthServer:
    """Small threaded HTTP server exposing /health and /ready."""

    def __init__(self, status: HealthStatus, host: str = '127.0.0.1', port: int = 8080):
        self.status = status
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return

        status = self.status

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == '/health':
                    code, payload = status.health_payload()
                elif self.path == '/ready':
                    code, payload = status.readiness_payload()
                else:
                    code, payload = 404, {'status': 'not_found'}
                body = json.dumps(payload, sort_keys=True).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name='RouteMQHealthServer', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None


def health_server_from_env(status: HealthStatus) -> HealthServer | None:
    settings = load_health_http_settings()
    if not settings.enabled:
        return None
    return HealthServer(status, host=settings.host, port=settings.port)
