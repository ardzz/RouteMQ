# Unit Tests

Unit tests live under `tests/unit/` and use `unittest` classes, including `unittest.IsolatedAsyncioTestCase`
for async handlers, middleware, queues, and bootstrap behavior.

## Guidelines

- Mock Redis, MySQL, MQTT clients, and filesystem side effects unless the test is explicitly an integration test.
- Keep unit tests deterministic and fast.
- Pair bug fixes with regression tests when practical.
- Prefer explicit assertions over broad smoke tests.

## Run unit tests directly

```bash
uv run python -m unittest discover tests/unit -p 'test_*.py'
```
