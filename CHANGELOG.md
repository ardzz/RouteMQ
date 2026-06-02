## v0.25.0 (2026-06-02)

### Feat

- **observability**: trace database, redis, rate-limit, and propagate MQTT context

## v0.24.0 (2026-06-02)

### Feat

- **app**: wire telemetry bootstrap lifecycle
- **metrics**: publish telemetry lifecycle metrics
- **tsdb**: add telemetry adapters
- **tsdb**: map telemetry observations
- **telemetry**: add runtime manager
- **telemetry**: add adapter contract
- **telemetry**: add measurement point types
- **config**: add relational database selectors

### Fix

- **telemetry**: address review feedback on adapters and runtime
- **telemetry**: validate timescale table identifier against allowlist

### Refactor

- **database**: use backend-neutral wording

## v0.23.0 (2026-05-29)

### Feat

- **metrics**: publish queue stats gauges
- **metrics**: add gauge registry support
- **cli**: add failed job management commands
- **queue**: drain workers with heartbeat support
- **queue**: harden database queue reliability
- **queue**: harden redis queue reliability
- **queue**: add driver admin and stats hooks
- **queue**: register bundled example jobs
- **queue**: discover registered job classes at boot
- **queue**: add reliability environment settings

## v0.22.2 (2026-05-29)

### Fix

- **docs**: refresh PyPI README and GitBook examples

## v0.22.1 (2026-05-29)

### Fix

- **tsdb**: return None from get_client when driver is not connected

## v0.22.0 (2026-05-29)

### Feat

- **tsdb**: add optional ClickHouse time-series integration

## v0.21.0 (2026-05-29)

### Feat

- **config**: add METRICS_HTTP_* environment variables
- **worker**: mark workers dead on stop for prometheus multiprocess cleanup
- **metrics**: add optional routemq[prometheus] extra with multiprocess support
- **health**: expose /metrics route with renderer-based content type
- **metrics**: install default hooks for lifecycle counters and span histograms
- **metrics**: add OpenMetrics text writer with content-type negotiation
- **metrics**: add MetricsRegistry with counter and histogram primitives

## v0.20.0 (2026-05-29)

### Feat

- **bootstrap**: wire DatabasePoolSettings into Model.configure
- **model**: accept pool kwargs in Model.configure
- **config**: add DatabasePoolSettings parser

## v0.19.2 (2026-05-29)

### Fix

- fail-fast logging audit for routemq and bootstrap (Sprint 06F) (#66)

## v0.19.1 (2026-05-28)

### Fix

- **release**: push bump tag with RELEASE_TOKEN so GitHub Release fires (#63)

## v0.19.0 (2026-05-28)

### Feat

- complete Sprint 06 observability (logs-first + tracing spans) (#61)

## v0.18.0 (2026-05-28)

### Feat

- complete Sprint 07 extensibility and settings (#59)

## v0.17.1 (2026-05-28)

### Fix

- **release**: stop stale release drafter drafts (#56)

## v0.17.0 (2026-05-28)

### Feat

- complete Sprint 06 reliability foundation (#54)

## v0.16.0 (2026-05-27)

### Feat

- **tinker**: add Rich FIGlet REPL startup

## v0.15.0 (2026-05-27)

### Feat

- **tinker**: polish REPL with Rich banner, traceback hooks, and styled output helpers (#50)

## v0.14.0 (2026-05-27)

### Feat

- **scaffold**: implement routemq new scaffolder with interactive + non-interactive modes (#47)

## v0.13.4 (2026-05-27)

### Refactor

- **cli**: convert argparse flags to subcommands with backward-compat aliases
- **rename**: rename core/ to routemq/ and fix install-correctness bugs (#44)

## v0.13.3 (2026-05-27)

### Fix

- **ci**: use RELEASE_TOKEN PAT for bump PR creation to trigger CI

## v0.13.2 (2026-05-27)

### Fix

- migrate declarative_base import to sqlalchemy.orm (silence MovedIn20Warning)

## v0.13.1 (2026-05-27)

### Fix

- replace deprecated datetime.utcnow() and asyncio.get_event_loop() in runtime paths

## v0.13.0 (2026-05-27)

### Feat

- **ci**: add OpenSSF Scorecard workflow and badge

## v0.12.3 (2026-05-27)

### Fix

- **ci**: use REVISION env var for bump detection and remove stale preflight
- **ci**: stop release-drafter from autotagging on every push; sync version sources (#23)

## v0.1.31 (2026-05-27)

## v0.1.30 (2026-05-27)

## v0.1.29 (2026-05-27)

## v0.1.28 (2026-05-27)

## v0.1.27 (2026-05-27)

### Fix

- **middleware**: handle max_requests=None in RateLimit middleware (#16)

## v0.1.26 (2026-05-27)

## v0.1.25 (2026-05-26)

## v0.12.1 (2026-05-26)

## v0.1.24 (2026-05-26)

### Fix

- **ci**: update cyclonedx-py CLI flags to modern syntax

## v0.1.23 (2026-05-26)

## v0.1.22 (2026-05-26)

### Fix

- **ci**: grant contents:write to SLSA provenance job to fix startup_failure
- **ci**: pin SLSA generator to tag ref to fix release.yml startup_failure
- **ci**: repair release.yml startup_failure on master push
- **worker_manager**: sum worker_count across routes and isolate spawn failures
- **job**: require explicit allow-list for Job.unserialize to prevent arbitrary import RCE
- **queue**: align job_id type across QueueDriver subclasses
- **model**: connect Model base class to declarative Base so create_tables actually works

### Refactor

- **queue**: move QueueJob and QueueFailedJob models into core/queue to fix core->app import inversion

## v0.12.0 (2025-10-30)

## v0.1.21 (2025-10-30)

### Feat

- make repository projectable with clean git initialization

## v0.1.20 (2025-10-30)

### Fix

- update CI/CD script to include queue documentation in SUMMARY.md

## v0.1.19 (2025-10-30)

### Feat

- add Docker configuration for queue workers and production deployment
- add background task queue system similar to Laravel's queue:work

## v0.1.18 (2025-09-14)

## v0.10.0 (2025-09-13)

## v0.1.17 (2025-09-14)

### Feat

- add timezone configuration to Docker setup

## v0.1.16 (2025-09-13)

## v0.9.0 (2025-09-13)

## v0.1.15 (2025-09-13)

### Feat

- enhance interactive REPL with run_async helper and async magic commands

## v0.1.14 (2025-09-13)

### Feat

- add nest-asyncio support and create interactive REPL documentation

## v0.7.1 (2025-09-13)

## v0.1.13 (2025-09-13)

### Fix

- update required Python version to 3.12 and add IPython dependency

## v0.7.0 (2025-09-13)

## v0.1.12 (2025-09-13)

### Feat

- add interactive REPL for testing ORM and queries

## v0.6.2 (2025-09-13)

## v0.1.11 (2025-09-13)

### Fix

- remove redundant check for existing .env file creation

## v0.1.10 (2025-09-13)

## v0.1.9 (2025-09-13)

## v0.1.8 (2025-09-13)

## v0.6.1 (2025-09-13)

## v0.1.7 (2025-09-13)

## v0.6.0 (2025-09-13)

### Fix

- update permissions for GitHub Action to enhance functionality

## v0.1.6 (2025-09-13)

### Feat

- add GitHub Action to auto-update SUMMARY.md based on docs directory structure

## v0.1.5 (2025-09-13)

## v0.1.4 (2025-09-13)

## v0.5.0 (2025-09-13)

## v0.1.3 (2025-09-13)

### Feat

- Add comprehensive documentation for creating controllers and database operations in RouteMQ

## v0.1.2 (2025-09-13)

## v0.4.0 (2025-09-13)

## v0.1.1 (2025-09-13)

### Feat

- Enhance logging configuration with file rotation support and update example environment file

## v0.3.0 (2025-09-13)

## v0.1.0 (2025-09-13)

### Feat

- Add release drafter configuration and update permissions in release.yml

## v0.2.2 (2025-09-13)

### Refactor

- Update authors list in pyproject.toml
- Remove unused port exposure for routemq service in Docker configuration

## v0.2.1 (2025-09-13)

### Refactor

- Add example files for middleware and router in the application

## v0.2.0 (2025-09-13)

### Feat

- Add Commitizen for conventional commit management and create release workflow
- Update Docker setup and enhance README for uv integration
- Enhance README with Redis integration and rate limiting details
- Add Redis integration and rate limiting middleware
- Implement dynamic router loading and enhance worker management
- Implement worker management for shared MQTT subscriptions
- Add initial implementation of RouteMQ framework with MQTT and MySQL support

### Fix

- update release workflow permissions and add GitHub token for checkout
- Update router path to point to device.py for correct routing

### Refactor

- Update logger names to use RouteMQ namespace for consistency
- Refactor RedisManager to improve type hinting and logging
