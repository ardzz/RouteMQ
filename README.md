<img alt="logo.png" height="200" src="logo.png" width="200"/>

# RouteMQ Framework

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ardzz/RouteMQ/badge)](https://scorecard.dev/viewer/?uri=github.com/ardzz/RouteMQ)

An MQTT routing framework with middleware support, dynamic router loading, Redis integration, and horizontal scaling capabilities, inspired by web frameworks.

## Quick Start

### Option 1: Use as Template

Start your own project with a clean git history:

**Using GitHub:**
1. Click "Use this template" button on GitHub
2. Create your new repository
3. Clone your repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
   cd YOUR_REPO
   ```

**Manual Setup:**
```bash
# Download and extract, or clone
git clone https://github.com/ardzz/RouteMQ.git my-mqtt-project
cd my-mqtt-project

# Run setup script to initialize fresh repository
bash setup-project.sh    # Linux/Mac
# OR
.\setup-project.ps1      # Windows PowerShell

# Install dependencies
uv sync

# Initialize project structure
python main.py --init

# Configure .env file with your MQTT broker details
# Run the application
uv run python main.py --run
```

### Option 2: Direct Clone

To explore or contribute to RouteMQ itself:

```bash
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ
uv sync
uv run python main.py --init
uv run python main.py --run
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
- **[Docker Deployment](./docs/docker-deployment.md)** - Production deployment with Docker
- **[Redis Integration](./docs/redis/README.md)** - Caching, sessions, and distributed features
- **[Rate Limiting](./docs/rate-limiting/README.md)** - Advanced rate limiting strategies
- **[Examples](./docs/examples/README.md)** - Practical examples and use cases
- **[API Reference](./docs/api-reference/README.md)** - Complete API documentation
- **[FAQ](./docs/faq.md)** - Frequently asked questions

## Project Structure

```
RouteMQ/
├── docs/                   # Documentation
├── app/                    # Your application code
│   ├── controllers/        # Route handlers
│   ├── middleware/         # Custom middleware
│   ├── models/            # Database models
│   ├── jobs/              # Background jobs
│   └── routers/           # Route definitions
├── core/                  # Framework core
│   ├── queue/             # Queue system
│   ├── job.py             # Base job class
│   └── ...                # Other core components
├── bootstrap/             # Application bootstrap
├── docker-compose.yml     # Production Docker setup
└── tests/                 # Test files
```

## Docker Deployment

RouteMQ includes production-ready Docker Compose configuration with Redis, MySQL, and queue workers:

```bash
# Start all services (app + 3 queue workers + Redis + MySQL)
docker compose up -d

# View logs
docker compose logs -f

# Scale workers
docker compose up -d --scale queue-worker-default=5

# Or use Makefile
make up      # Start all services
make logs    # View logs
make ps      # Show status
```

See [Docker Deployment Guide](./docs/docker-deployment.md) for detailed instructions.

## Background Task Queue

Process time-consuming tasks asynchronously with the built-in queue system:

```python
# Create a job
from core.job import Job

class SendEmailJob(Job):
    max_tries = 3
    queue = "emails"

    async def handle(self):
        # Send email logic
        pass

# Dispatch the job
from core.queue.queue_manager import dispatch

job = SendEmailJob()
job.to = "user@example.com"
await dispatch(job)

# Run queue worker
python main.py --queue-work --queue emails
```

See [Queue System Documentation](./docs/queue/README.md) for complete guide.

## Contributing

We welcome contributions! Please see our documentation for development setup and contribution guidelines.

## License

MIT License - see [LICENSE](LICENSE) file for details.
