# Running Queue Workers

Queue workers poll a queue, restore a registered `Job`, call `handle()`, and retry or fail the job based on its settings.

## Start a worker

```bash
routemq queue-work
routemq queue-work --queue emails
routemq queue-work --queue telemetry --connection redis
```

`routemq --queue-work` still exists as a compatibility alias, but new docs should use the `queue-work` subcommand.

## Options

| Option | Example | What it does |
|---|---|---|
| `--queue` | `--queue telemetry` | Poll one queue name. |
| `--connection` | `--connection redis` | Override `QUEUE_CONNECTION`. |
| `--sleep` | `--sleep 1` | Seconds to wait when no job is available. |
| `--max-jobs` | `--max-jobs 100` | Stop after N jobs. Useful for one-shot containers. |
| `--max-time` | `--max-time 3600` | Stop after N seconds. |
| `--max-tries` | `--max-tries 5` | Override retry attempts for this worker. |
| `--timeout` | `--timeout 120` | Maximum seconds per job. |

## Multiple queues

Run one process per queue when different work needs different polling rates:

```bash
routemq queue-work --queue high-priority --sleep 1
routemq queue-work --queue default --sleep 3
routemq queue-work --queue cleanup --sleep 30
```

## Docker Compose

```yaml
services:
  queue-worker-telemetry:
    build: .
    command: ["uv", "run", "routemq", "queue-work", "--queue", "telemetry", "--connection", "redis", "--sleep", "1"]
    environment:
      ENABLE_REDIS: "true"
      REDIS_HOST: redis
      REDIS_PORT: "6379"
      QUEUE_CONNECTION: redis
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

Scale workers when one queue needs more throughput:

```bash
docker compose up -d --scale queue-worker-telemetry=5
docker compose logs -f queue-worker-telemetry
```

## Supervisor

```ini
[program:routemq-queue-telemetry]
command=/path/to/venv/bin/routemq queue-work --queue telemetry --connection redis --sleep 1
directory=/path/to/app
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/routemq/queue-telemetry.log
stopwaitsecs=60
```

## systemd

```ini
[Unit]
Description=RouteMQ Queue Worker (telemetry)
After=network.target redis.service

[Service]
Type=simple
WorkingDirectory=/path/to/app
ExecStart=/path/to/venv/bin/routemq queue-work --queue telemetry --connection redis --sleep 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Shutdown

Workers handle `SIGTERM` and `SIGINT`. In containers and process managers, give the worker enough time to finish the current job before killing the process.

## Common checks

```bash
redis-cli ping
routemq queue-work --queue telemetry --connection redis --max-jobs 1 --sleep 1
```

If a worker cannot restore a job, make sure the job class is imported by your app and decorated with `@Job.register`.
