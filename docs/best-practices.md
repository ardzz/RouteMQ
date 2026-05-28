# Best Practices

RouteMQ projects are asynchronous MQTT applications. Keep handlers small, protect external resources,
and make operational behavior visible.

## Application code

- Keep controller handlers async and non-blocking.
- Move slow work into queued jobs instead of blocking MQTT message dispatch.
- Validate untrusted MQTT topics and payloads before using them in application logic.
- Keep route modules free of import-time side effects; router discovery imports every module.

## Queues and jobs

- Set `max_tries`, `retry_after`, and `timeout` explicitly for operationally important jobs.
- Keep job payloads serializable and avoid storing mutable state on job classes.
- Use separate queues for high-priority or latency-sensitive work.
- Monitor failed jobs and reserved jobs when using Redis or database queue backends.

## Configuration

- Keep secrets out of version control and load environment-specific values from `.env` or deployment
  configuration.
- Enable `HEALTH_HTTP_ENABLED=true` in containerized or orchestrated deployments.
- Use `LOG_LEVEL=INFO` by default and switch to `DEBUG` only for short investigations.

## Testing and releases

- Run `uv run python run_tests.py` before opening a pull request.
- Run Docker-backed integration tests when changing Redis, MySQL, MQTT, or queue backends.
- Keep changelog entries clear and follow Conventional Commits so automated release notes stay useful.
- Review [Release Conformance](release-conformance.md) before publishing a release.
