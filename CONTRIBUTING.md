# Contributing to RouteMQ

Thank you for your interest in contributing to RouteMQ. This guide explains how to report issues, propose changes, and prepare pull requests that are easy to review and safe to merge.

## How to report bugs

Use [GitHub Issues](https://github.com/ardzz/RouteMQ/issues) for bug reports. A useful report includes:

- RouteMQ version or commit SHA.
- Python version, operating system, and whether Docker is involved.
- MQTT broker, Redis, or MySQL details when relevant, with secrets removed.
- A minimum reproduction: topic, payload shape, route definition, expected behavior, and actual behavior.
- Logs, tracebacks, or screenshots if they help explain the failure.

Please do not report undisclosed security vulnerabilities in public issues. Follow [SECURITY.md](./SECURITY.md) instead.

## How to request features

Use [GitHub Issues](https://github.com/ardzz/RouteMQ/issues) for feature requests. Include the use case, motivation, proposed API or behavior when you have one, and any compatibility concerns for existing RouteMQ users.

## Pull request process

1. Fork the repository or create a branch from `master`.
2. Install dependencies with `uv sync`.
3. Run `uv run routemq new .` if you need the local scaffolded app structure.
4. Keep changes focused and follow Conventional Commits:
   - `feat:` — new feature
   - `fix:` — bug fix
   - `docs:` — documentation only
   - `test:` — adding or correcting tests
   - `build:` — build system or dependency changes
   - `chore:` — maintenance tasks
   - `ci:` — CI configuration
   - `refactor:` — code change that neither fixes a bug nor adds a feature
5. Run the local verification commands before opening a PR:
   ```bash
   uv run python run_tests.py
   uv run ruff check . && uv run ruff format --check .
   uv run mypy routemq app bootstrap tests/unit
   ```
6. Open a pull request with a clear description, link related issues, wait for CI, and respond to review threads.

## Testing requirements

- All new features must include tests.
- Bug fixes should include regression tests that fail without the fix when practical.
- CI enforces the coverage floor configured in `pyproject.toml`.
- If a regression test is not applicable because the project has no matching historical report or the behavior is documentation-only, state that in the PR description.

## Coding standards

- RouteMQ targets Python 3.12+.
- Type hints are encouraged for new and changed code.
- Follow existing framework patterns in the codebase and public documentation.
- Controller handlers should be `@staticmethod async` methods.
- Middleware and jobs should avoid blocking the event loop; use async APIs or `asyncio.to_thread` for blocking work.
- Do not introduce side effects at module-import time in `app/routers/*.py`.
- Do not add broad `# type: ignore` suppressions or equivalent unchecked casts; narrow and justify unavoidable exceptions in review.

## Acceptable contribution requirements

- Contributions must be compatible with the project's MIT license.
- DCO sign-off is not required.
- Contributors must follow the [Code of Conduct](./CODE_OF_CONDUCT.md).
- Do not include secrets, credentials, private keys, or production data in commits, tests, issues, or PRs.

## Communication channels

- Use GitHub Issues for bugs and feature requests.
- Use GitHub Discussions for usage questions, design questions, and community discussion.
- Use pull request threads for code-level review and implementation details.

## Project structure

RouteMQ keeps framework internals in `routemq/`, application examples and scaffolded userland code in `app/`, bootstrapping in `bootstrap/`, and unittest-based tests in `tests/unit/`. The root [AGENTS.md](./AGENTS.md) is the maintained contributor map for architecture, conventions, and anti-patterns; consult it before changing routing, queue, worker, or bootstrap behavior.
