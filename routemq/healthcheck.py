"""Container health probe: exit 0 only when the local RouteMQ /ready endpoint reports ready."""

from __future__ import annotations

import http.client
import ipaddress
import json

from dotenv import load_dotenv

from routemq.settings import load_health_http_settings

PROBE_TIMEOUT_SECONDS = 5.0


def _probe_host(bind_host: str) -> str:
    """Map an all-interfaces bind address to the matching loopback; keep hostnames and specific addresses."""
    if not bind_host:
        return '127.0.0.1'
    try:
        address = ipaddress.ip_address(bind_host)
    except ValueError:
        return bind_host
    if address.is_unspecified:
        return '::1' if address.version == 6 else '127.0.0.1'
    return bind_host


def probe_ready() -> bool:
    """Return True only for an enabled local /ready endpoint answering 200 with status "ready"."""
    load_dotenv('.env')
    settings = load_health_http_settings()
    if not settings.enabled:
        return False

    host = _probe_host(settings.host)
    connection = http.client.HTTPConnection(host, settings.port, timeout=PROBE_TIMEOUT_SECONDS)
    try:
        connection.request('GET', '/ready')
        response = connection.getresponse()
        body = response.read()
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()

    if response.status != 200:
        return False
    try:
        payload = json.loads(body)
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get('status') == 'ready'


def main() -> int:
    return 0 if probe_ready() else 1


if __name__ == '__main__':
    raise SystemExit(main())
