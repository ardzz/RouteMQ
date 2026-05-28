# ADR-0003: Docker-backed Integration Tests — Explicit Gate + Clean Skips

**Status:** Accepted
**Date:** 2026-05-28
**Sprint:** SPRINT-07

## Context

RouteMQ had strong unit coverage for routing, queue, Redis, database, and worker behavior, but most tests used mocks. The root `test_queue.py` file was a manual smoke script and did not exercise live queue backends.

Sprint 07 needs confidence that Redis, MySQL, and MQTT behavior works against real services without making every local or CI test run depend on Docker.

## Decision

Adopt Docker-backed integration tests using `testcontainers-python` and stdlib `unittest`:

1. **Integration tests live under `tests/integration/`** so the canonical `run_tests.py` discovery can find them.
2. **Docker tests are opt-in** with `RUN_INTEGRATION_TESTS=1`.
3. **Docker availability is checked before starting containers** using Docker SDK `from_env(...).ping()`.
4. **Unavailable Docker skips, not fails** — integration test classes raise `unittest.SkipTest` when Docker is not available.
5. **Real services are covered with testcontainers** — Redis, MySQL, and Mosquitto containers validate queue and MQTT paths.
6. **Unit tests remain mock-only** — Docker-backed coverage must not replace fast unit tests.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Always run Docker tests during `run_tests.py` | Local development and constrained CI runners would fail when Docker is unavailable. |
| Keep only the root `test_queue.py` smoke script | It is outside unittest discovery and does not dispatch to a live backend. |
| Use pytest fixtures | The project standard is stdlib `unittest`; switching frameworks would require a broader test migration. |
| Use docker-compose for integration tests | Compose would add another orchestration path; testcontainers keeps test setup local to each test class. |

## Consequences

### Positive

- Default test runs stay fast and deterministic.
- `RUN_INTEGRATION_TESTS=1` validates real Redis, MySQL, and MQTT behavior.
- Docker-unavailable environments skip cleanly.
- Integration setup is reusable through `DockerIntegrationTestCase`.

### Negative

- Docker-enabled runs are slower and pull service images on first use.
- Integration tests need careful environment and singleton cleanup.
- MySQL datetime precision can require small waits before immediate pop checks.

## References

- Helper: `tests/integration/helpers.py`
- Redis/MySQL tests: `tests/integration/test_queue_backends.py`
- MQTT test: `tests/integration/test_mqtt_end_to_end.py`
- Test runner: `run_tests.py`
- Testcontainers Python documentation
- Python `unittest.SkipTest` and class fixture documentation
