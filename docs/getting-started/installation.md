# Installation

RouteMQ is published on PyPI as `routemq`. Install the base runtime when you already have an app layout, or install an extra when you want the scaffolder, Redis, or every optional integration.

## Prerequisites

- Python 3.12 or newer
- An MQTT broker. For local work, Mosquitto is fine. For a quick smoke test, `test.mosquitto.org` also works.

## Install modes

| Package | Includes | Use it when |
|---|---|---|
| `routemq` | Router, middleware, app boot, jobs, MySQL-backed queue | You already have an `app/` layout or you are adding RouteMQ to an existing project. |
| `routemq[cli]` | Base runtime plus the `routemq new` scaffolder UI | You are starting a new app. |
| `routemq[redis]` | Base runtime plus Redis client support | You want Redis queues, cache, rate limits, or shared state. |
| `routemq[all]` | CLI, Redis, Prometheus, and ClickHouse extras | You want every optional integration in one install. |

## uv

Use `uv add` inside a uv-managed project, then run the CLI with `uv run`:

```bash
uv add routemq
uv add "routemq[cli]"
uv add "routemq[redis]"
uv add "routemq[all]"
uv run routemq --help
```

Use `uv pip install` when you want pip-compatible installation into the active environment:

```bash
uv pip install routemq
uv pip install "routemq[cli]"
routemq --help
```

## pip

```bash
pip install routemq
pip install "routemq[cli]"
pip install "routemq[redis]"
pip install "routemq[all]"
```

Quote extras in shells that treat brackets specially.

## Verify the install

```bash
# uv-managed project
uv run routemq --help
uv run routemq new --help
uv run routemq run --help
uv run routemq queue-work --help

# active virtualenv or pip-installed CLI
routemq --help
routemq new --help
routemq run --help
routemq queue-work --help
```

If `routemq new` is missing rich prompts or templates, install `routemq[cli]`.

## Source checkout for framework development

Use this only when you are hacking on RouteMQ itself:

```bash
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ
uv sync --all-extras --dev
uv run python run_tests.py
```

## Next steps

- [Quick Start](quick-start.md) - Create a small RouteMQ app.
- [Your First Route](first-route.md) - Add a controller and route by hand.
- [Queue System](../queue/README.md) - Dispatch background jobs.
