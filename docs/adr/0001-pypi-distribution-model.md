# ADR-0001: PyPI Distribution Model — Engine Package + Scaffolder

**Status:** Accepted
**Date:** 2026-05-27
**Sprint:** SPRINT-19 (Phases A–D)

## Context

RouteMQ shipped two contradictory ways: as a `git clone` template (via `setup-project.sh`) AND as a wheel via `pip install routemq`. The wheel was broken in three places (version lookup, console-script entry, packaging app/), and the dual presentation confused users.

## Decision

Adopt the Django distribution model in a single repository:

1. **Engine ships as `routemq` package** — `core/` renamed to `routemq/` so `pip install` name equals import name.
2. **Scaffolder ships inside the engine** — `routemq new <name>` mirrors `django-admin startproject`, generating a minimal working project from package-data templates.
3. **User's `app/` is never vendored** — engine upgrades via `pip install -U routemq` like any library.
4. **`bootstrap/` stays separate from `routemq/`** — distinct concern (process bootstrap vs. routing engine).
5. **CLI subcommands** — `routemq new|run|tinker|queue-work` with back-compat `--init/--run/--tinker/--queue-work` flag aliases retained for one deprecation cycle.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Pure cookiecutter scaffolder (separate tool) | Adds external dep; users would need `pip install cookiecutter && cookiecutter gh:ardzz/routemq` workflow — friction. |
| copier library | Heavier than needed for this use case; questionary + Jinja2 cover it. |
| src/ layout | More disruption to existing repo; flat layout works fine with hatchling. |
| Fold `bootstrap/` under `routemq/` | Conflates engine internals with bootstrap orchestration. Keeping separate matches the existing AGENTS.md hierarchy. |
| Embed scaffold strings in `cli.py` (status quo) | Hard to maintain; users can't preview before scaffolding; no way to add Jinja substitution for project name. |

## Consequences

### Positive
- Single `pip install routemq` works
- `routemq new` mirrors create-next-app UX
- Engine upgrades are normal pip workflow
- Scaffold templates are auditable (real files in the wheel)

### Negative
- ~150 import sites updated (one-time mechanical refactor — landed via PR #44)
- Optional `[cli]` extra needed for the scaffolder (questionary + rich + jinja2). Base `pip install routemq` does not include them. Documented in README.
- `setup-project.sh` retained for one release with deprecation header (transition window for users who fork the framework directly).

## Phases (executed in SPRINT-19)

| Phase | PR | Outcome |
|---|---|---|
| A — Rename + install fixes | #44 | `core/` → `routemq/`; 3 install bugs fixed; `routemq` console script works |
| B — CLI subcommands | #45 → v0.13.4 | `routemq new/run/tinker/queue-work` + back-compat aliases |
| C — Scaffolder + templates | #47 → v0.14.0 | `routemq new` generates runnable project with optional MySQL/Redis/Queue/Docker overlays |
| D — TestPyPI + ADR + README | this PR | TestPyPI workflow, clean-venv CI test, this ADR, README rewrite, setup-project deprecation |

## References

- Spec: `docs/superpowers/specs/2026-05-27-pypi-package-distribution-design.md`
- Plan: `docs/plans/sprints/SPRINT-19-pypi-distribution.md`
- Hatchling docs (Context7 `/pypa/hatch`)
- Questionary docs (Context7 `/tmbo/questionary`)
- Python `importlib.metadata` docs
