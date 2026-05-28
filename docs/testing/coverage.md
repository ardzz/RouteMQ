# Test Coverage

Coverage is configured in `pyproject.toml` and CI runs the canonical coverage commands.

## Run coverage locally

```bash
uv run coverage erase
uv run coverage run run_tests.py
uv run coverage report -m
```

The coverage floor is configured in `[tool.coverage.report]` as `fail_under`.

## Dead-code audit status

Ruff currently enables Pyflakes but still carries baseline ignores for unused imports and variables.
Treat dead-code cleanup as an explicit follow-up: remove or narrow `F401` and `F841` ignores when the
codebase is ready, then run Ruff and the full test suite.
