<img alt="logo.png" height="200" src="logo.png" width="200"/>

# RouteMQ Framework

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ardzz/RouteMQ/badge)](https://scorecard.dev/viewer/?uri=github.com/ardzz/RouteMQ)

<!-- TODO(sprint-15-followup): replace <PROJECT_ID> after submitting at https://www.bestpractices.dev/en/projects/new
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/<PROJECT_ID>/badge)](https://www.bestpractices.dev/projects/<PROJECT_ID>)
-->

A flexible MQTT routing framework with middleware, dynamic routes, queue workers, Redis integration, and horizontal scaling — inspired by Laravel/Django web frameworks.

## Quick Start

### 1. Install

```bash
pip install routemq[cli]
```

### 2. Scaffold a new project

```bash
routemq new my-app
cd my-app
```

The scaffolder asks about optional features (MySQL, Redis, background queue, Docker). Use `--yes` to accept defaults non-interactively.

### 3. Run

```bash
# Edit .env with your MQTT broker details
routemq run
```

## Features

- **Dynamic Router Loading** - Automatically discover and load routes from multiple files
- **Route-based MQTT topic handling** - Define routes for MQTT topics
- **Middleware support** - Process messages through middleware chains
- **Parameter extraction** - Extract variables from MQTT topics using Laravel-style syntax
- **Background Task Queue** - Laravel-style queue system for async job processing
- **Shared Subscriptions** - Horizontal scaling with worker processes
- **Redis Integration** - Optional Redis support for distributed caching and rate limiting
- **Advanced Rate Limiting** - Multiple rate limiting strategies with Redis backend
- **Optional MySQL integration** - Use with or without a database
- **Docker Support** - Production-ready Docker Compose setup with queue workers
- **Environment-based configuration** - Configuration through .env files

## Documentation

**Documentation is available in the [docs](./docs) folder, optimized for GitBook integration.**

See the [Installation Guide](./INSTALL.md) for detailed setup instructions.

### Quick Links

- **[Getting Started](./docs/getting-started/README.md)** - Installation, quick start, and basic setup
- **[Configuration](./docs/configuration/README.md)** - Environment variables and setup options
- **[Routing](./docs/routing/README.md)** - Route definition, parameters, and organization
- **[Controllers](./docs/controllers/README.md)** - Creating and organizing business logic
- **[Middleware](./docs/middleware/README.md)** - Request processing and middleware chains
- **[Queue System](./docs/queue/README.md)** - Background task processing and job queues
- **[Testing](./docs/testing/README.md)** - Unit and Docker-backed integration testing
- **[Docker Deployment](./docs/docker-deployment.md)** - Production deployment with Docker
- **[Redis Integration](./docs/redis/README.md)** - Caching, sessions, and distributed features
- **[Rate Limiting](./docs/rate-limiting/README.md)** - Advanced rate limiting strategies
- **[Examples](./docs/examples/README.md)** - Practical examples and use cases
- **[API Reference](./docs/api-reference/README.md)** - Complete API documentation
- **[FAQ](./docs/faq.md)** - Frequently asked questions

## Project Structure

Scaffolded projects follow this layout:

```
my-app/
├── app/                    # Your application code
│   ├── controllers/        # Route handlers
│   ├── middleware/         # Custom middleware
│   ├── models/             # Database models
│   ├── jobs/               # Background jobs
│   └── routers/            # Route definitions
├── bootstrap/              # Application bootstrap
├── docker-compose.yml      # Optional Docker setup
├── pyproject.toml          # Project metadata and dependencies
└── .env                    # Environment configuration
```

## Docker Deployment

RouteMQ can scaffold Docker support for Redis, MySQL, app runtime, and queue workers:

```bash
routemq new my-app --with-docker --with-redis --with-mysql --with-queue
cd my-app

# Start services from the scaffolded project
docker compose up -d

# View logs
docker compose logs -f

# Scale workers
docker compose up -d --scale queue-worker-default=5
```

See [Docker Deployment Guide](./docs/docker-deployment.md) for detailed instructions.

## Background Task Queue

Process time-consuming tasks asynchronously with the built-in queue system:

```python
# Create a job
from routemq.job import Job

class SendEmailJob(Job):
    max_tries = 3
    queue = "emails"

    async def handle(self):
        # Send email logic
        pass

# Dispatch the job
from routemq.queue.queue_manager import dispatch

job = SendEmailJob()
job.to = "user@example.com"
await dispatch(job)
```

Run a worker from your scaffolded app:

```bash
routemq queue-work --queue emails
```

See [Queue System Documentation](./docs/queue/README.md) for the complete guide.

## Advanced: Fork the framework

If you want to modify the framework internals directly (rather than depend on the published wheel), see [TEMPLATE.md](./TEMPLATE.md). This path is deprecated as the primary workflow; `pip install routemq[cli]` is recommended for application development.

For direct framework development:

```bash
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ
uv sync --all-extras --dev
uv run python run_tests.py
```

## Contributing

We welcome contributions! Please see our documentation for development setup and contribution guidelines.

## License

MIT License - see [LICENSE](LICENSE) file for details.
