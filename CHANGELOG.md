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
