# Running Tests

RouteMQ uses the Python standard library `unittest` runner through `run_tests.py`.

## Default suite

```bash
uv run python run_tests.py
```

The default suite runs unit tests and skips Docker-backed integration tests unless explicitly enabled.

## Integration suite

```bash
RUN_INTEGRATION_TESTS=1 uv run python -m unittest tests.integration.test_queue_backends tests.integration.test_mqtt_end_to_end
```

Integration tests require Docker and start Redis, MySQL, or Mosquitto containers through testcontainers.

## CI-equivalent checks

```bash
uv run python run_tests.py
uv run ruff check .
uv run ruff format --check .
uv run mypy routemq app bootstrap
uv run bandit -c pyproject.toml -r routemq app bootstrap
uv run pip-audit
uv run coverage run run_tests.py
uv run coverage report -m
uv build
```
