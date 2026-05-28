# Integration Tests

RouteMQ integration tests exercise real Redis, MySQL, and MQTT services through Docker containers. They are intentionally opt-in so normal unit test runs stay fast and work on machines without Docker.

## Running Integration Tests

Run the default test suite without Docker-backed tests:

```bash
uv run python run_tests.py
```

Run only the Docker-backed integration tests:

```bash
RUN_INTEGRATION_TESTS=1 uv run python -m unittest \
  tests.integration.test_queue_backends \
  tests.integration.test_mqtt_end_to_end
```

Run the full suite, including integration tests:

```bash
RUN_INTEGRATION_TESTS=1 uv run python run_tests.py
```

If `RUN_INTEGRATION_TESTS` is not set, integration classes skip. If Docker is unavailable, they also skip instead of failing.

## Requirements

- Docker daemon available to the current user
- Development dependencies installed with uv
- `RUN_INTEGRATION_TESTS=1` set for Docker-backed runs

Install development dependencies:

```bash
uv sync --all-extras --dev
```

The integration test dependencies include `testcontainers[redis,mysql,mqtt]` and `paho-mqtt`.

## Current Coverage

| Test module | Service | Coverage |
|-------------|---------|----------|
| `tests.integration.test_queue_backends` | Redis | `RedisQueue` push/pop/delete round trip |
| `tests.integration.test_queue_backends` | MySQL | `DatabaseQueue` push/pop/delete round trip |
| `tests.integration.test_mqtt_end_to_end` | Mosquitto | MQTT publish/subscribe through `Router.dispatch()` |

## Pattern for New Integration Tests

Use `DockerIntegrationTestCase` for all Docker-backed integration tests:

```python
import unittest

from tests.integration.helpers import DockerIntegrationTestCase


class MyIntegrationTests(DockerIntegrationTestCase, unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Start testcontainers here.
        # Register cls.addClassCleanup(container.stop) after start().
```

Guidelines:

- Keep unit tests mocked; use integration tests only for real service behavior.
- Gate Docker work behind `DockerIntegrationTestCase`.
- Use `setUpClass()` and `addClassCleanup()` for expensive containers.
- Restore environment variables and singleton state in `tearDown()` / `asyncTearDown()`.
- Do not add pytest fixtures unless the whole suite is intentionally migrated.

## Troubleshooting

### Tests are skipped

Set the integration gate:

```bash
RUN_INTEGRATION_TESTS=1 uv run python -m unittest tests.integration.test_queue_backends
```

If they still skip, verify Docker:

```bash
docker version
docker ps
```

### First run is slow

The first Docker-backed run may pull Redis, MySQL, Mosquitto, and Ryuk images. Later runs should be faster if images are cached locally.

### MySQL timing

MySQL stores queue timestamps with second-level precision. Immediate pop checks may need a short wait after `push()` so the inserted `available_at` timestamp is visible as available.
