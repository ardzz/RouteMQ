# Contributing to RouteMQ

Thank you for your interest in contributing to RouteMQ!

## Getting Started

1. Fork the repository and clone your fork.
2. Install dependencies with `uv sync`.
3. Run `python main.py --init` to scaffold the local app structure.
4. Create a branch for your changes.

## Development Workflow

- Follow the existing code style. The project targets Python 3.12+.
- All controller handlers should be `@staticmethod async`.
- Add or update tests in `tests/` and run `uv run python run_tests.py` before submitting.
- Keep middleware chains non-blocking; heavy work belongs in queued `Job` instances.
- Do not introduce side effects at module-import time in `app/routers/*.py`.

## Commit Style

This project uses [Commitizen](https://commitizen-tools.github.io/commitizen/) to manage versions and changelogs. Please use conventional commit messages:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `style:` — formatting, no code change
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — adding or correcting tests
- `chore:` — maintenance tasks

## Pull Request Process

1. Ensure your branch is up to date with the upstream `master` or `develop` branch.
2. Verify that `uv run python run_tests.py` passes.
3. Open a pull request with a clear description of the change and the problem it solves.
4. Link any related issues.

## Questions?

Open an issue or start a discussion in the repository. For usage questions, refer to the documentation in the `docs/` folder.
