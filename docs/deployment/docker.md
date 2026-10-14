# Docker Deployment

Deploy RouteMQ using Docker containers for consistent, scalable environments.

## Quick Start

### Basic Docker Deployment

```bash
# Clone the repository
git clone <your-repo-url>
cd RouteMQ

# Build the Docker image
docker build -t routemq:latest .

# Run the image's default command: /opt/venv/bin/routemq --run
docker run -d \
  --name routemq \
  -e MQTT_BROKER=test.mosquitto.org \
  -e MQTT_PORT=1883 \
  routemq:latest
```

The image enables the health server on `127.0.0.1:8080` inside the container, and its `HEALTHCHECK` probes it
there, so no port needs publishing. `docker ps` reports `healthy` only after the app's `/ready` passes, which
requires a completed startup and a connected MQTT broker.

### Docker Compose

Use the repository `docker-compose.yml` for Redis, MySQL, ClickHouse, the app, and queue workers. Add Mosquitto when you want a local broker instead of `test.mosquitto.org`.

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f routemq

# Stop all services
docker compose down
```

## Dockerfile Explanation

The repository root [`Dockerfile`](../../Dockerfile) is the source of truth. This section summarizes it instead of
repeating it; read the file for exact commands.

| Stage | What it does |
|---|---|
| `uv` | Supplies the pinned `uv` binary to `builder`. Nothing from this stage reaches the final image. |
| `builder` | Installs build packages and runs `uv sync --locked --no-dev --no-editable --extra redis --extra clickhouse --extra prometheus` into `/opt/venv`. |
| `runtime` | The final stage. Copies `/opt/venv` to the same path, copies `app/`, and runs as the non-root `app` user. |

The root `Dockerfile` has no `development` or `production` target. `docker build .` produces the `runtime` stage.

### Key Features

- Both `FROM` images, the Python 3.12 slim Debian base and the uv image, are literal references pinned by version
  tag and `sha256` digest. Neither is selected through `ARG` or a floating `latest` tag.
- The install is locked. The build copies `uv.lock` and runs `uv sync --locked`, so a missing lockfile, or one that
  no longer matches `pyproject.toml`, fails the build.
- The image holds RouteMQ and its base dependencies, which include the MySQL driver, plus the `redis`,
  `clickhouse`, and `prometheus` extras used by `docker-compose.yml`. RouteMQ is installed as a regular package, not
  an editable one. Development dependencies and the `cli` and `postgres` extras are not installed.
- The `runtime` stage contains no `uv`. Containers start `/opt/venv/bin/routemq` directly and download or install
  nothing at startup. `PATH` starts with `/opt/venv/bin`.
- `/opt/venv` sits outside `/app`, so bind mounts at `/app/app`, `/app/bootstrap`, or all of `/app` leave the
  environment in place. `PYTHONPATH=/app` puts mounted source ahead of the installed packages.
- The copied source and `/opt/venv` stay root-owned. The `app` user owns only the `/app` directory itself, where a
  generated `.env` can be written, and `/app/logs`.
- The default command is `/opt/venv/bin/routemq --run`. The queue workers in `docker-compose.yml` replace it with
  `/opt/venv/bin/routemq --queue-work --queue <name> --sleep <seconds>`.
- `HEALTHCHECK` runs `/opt/venv/bin/python -m routemq.healthcheck` every 30 seconds (10-second timeout, 40-second
  start period, 3 retries). The image sets `HEALTH_HTTP_ENABLED=true`, `HEALTH_HTTP_HOST=127.0.0.1`, and
  `HEALTH_HTTP_PORT=8080`, so the app and each worker container serve their own `/ready`. See
  [Health Checks](../monitoring/health-checks.md).
- The `TIMEZONE` build argument (default `Asia/Jakarta`) sets `TZ` in both stages.

### CI smoke test

The required CI `build` job builds this image and then runs:

```bash
python scripts/smoke_docker.py --image routemq:ci-smoke
```

The script never builds or pulls the RouteMQ image; it tests a tag that already exists locally. It runs the image's
default command and a queue worker against Mosquitto, Redis, and MySQL containers on a private `--internal` Docker
network, with no published ports, no host `.env`, and no internet route, so any install or download at startup
fails. First in Redis queue mode and then in database queue mode, it publishes MQTT messages that a fixture route
turns into queued jobs and checks the MySQL rows the worker writes. It also checks that both containers stay ready
after idling past the 30-second Redis worker metadata expiry, that the worker turns unhealthy and recovers when
Redis or MySQL stops and restarts, that the app does the same for Mosquitto, and that both exit `0` on `SIGTERM`.
Before that, it inspects the image for a non-root user, a virtualenv with the three extras, no development
packages, and no `uv`.

A missing prerequisite, a failed assertion, or a timeout fails the job; nothing is skipped. The script removes only
the containers and network it created. To run it locally, build once and pass the tag:

```bash
docker build -t routemq:local .
python scripts/smoke_docker.py --image routemq:local
```

## Docker Compose Configuration

### Complete stack with local Mosquitto

```yaml
version: '3.8'

services:
  routemq:
    build: .
    container_name: routemq-app
    environment:
      # MQTT Configuration
      MQTT_BROKER: ${MQTT_BROKER:-mosquitto}
      MQTT_PORT: ${MQTT_PORT:-1883}
      MQTT_USERNAME: ${MQTT_USERNAME:-}
      MQTT_PASSWORD: ${MQTT_PASSWORD:-}
      MQTT_GROUP_NAME: ${MQTT_GROUP_NAME:-production_group}

      # Database Configuration
      ENABLE_MYSQL: ${ENABLE_MYSQL:-true}
      DB_HOST: ${DB_HOST:-mysql}
      DB_PORT: ${DB_PORT:-3306}
      DB_NAME: ${DB_NAME:-routemq_production}
      DB_USER: ${DB_USER:-routemq_user}
      DB_PASS: ${DB_PASS:-secure_password}

      # Redis Configuration
      ENABLE_REDIS: ${ENABLE_REDIS:-true}
      REDIS_HOST: ${REDIS_HOST:-redis}
      REDIS_PORT: ${REDIS_PORT:-6379}

      # Application Configuration
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      WORKER_COUNT: ${WORKER_COUNT:-3}

    depends_on:
      mosquitto:
        condition: service_healthy
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy

    networks:
      - routemq-network

    restart: unless-stopped

    volumes:
      - ./app:/app/app:ro  # Mount application code (read-only)
      - ./logs:/app/logs   # Mount logs directory
      - ./.env:/app/.env:ro # Mount environment file

    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M

    # Same readiness probe as the image HEALTHCHECK; exits 0 only when /ready reports ready
    healthcheck:
      test: ["CMD", "/opt/venv/bin/python", "-m", "routemq.healthcheck"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  mosquitto:
    image: eclipse-mosquitto:2.0
    container_name: routemq-mosquitto
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./docker/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./docker/mosquitto/passwd:/mosquitto/config/passwd:ro
      - mosquitto_data:/mosquitto/data
      - mosquitto_logs:/mosquitto/log
    networks:
      - routemq-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mosquitto_pub", "-h", "localhost", "-t", "health", "-m", "check", "-u", "health", "-P", "check"]
      interval: 30s
      timeout: 5s
      retries: 3

  mysql:
    image: mysql:8.0
    container_name: routemq-mysql
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-root_password}
      MYSQL_DATABASE: ${DB_NAME:-routemq_production}
      MYSQL_USER: ${DB_USER:-routemq_user}
      MYSQL_PASSWORD: ${DB_PASS:-secure_password}
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./docker/mysql/init:/docker-entrypoint-initdb.d:ro
    networks:
      - routemq-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD:-root_password}"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    container_name: routemq-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
      - ./docker/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
    networks:
      - routemq-network
    restart: unless-stopped
    command: redis-server /usr/local/etc/redis/redis.conf
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  mysql_data:
  redis_data:
  mosquitto_data:
  mosquitto_logs:

networks:
  routemq-network:
    driver: bridge
```

## Environment Configuration

### Environment Variables

Create a `.env` file for configuration:

```env
# MQTT Broker Settings
MQTT_BROKER=mosquitto
MQTT_PORT=1883
MQTT_USERNAME=routemq_user
MQTT_PASSWORD=mqtt_secure_password
MQTT_GROUP_NAME=production_group

# Database Settings
ENABLE_MYSQL=true
DB_HOST=mysql
DB_PORT=3306
DB_NAME=routemq_production
DB_USER=routemq_user
DB_PASS=db_secure_password

# Redis Settings
ENABLE_REDIS=true
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=redis_secure_password

# Application Settings
LOG_LEVEL=INFO
WORKER_COUNT=3
ENVIRONMENT=production

# Security Settings
SECRET_KEY=your-secret-key-here
JWT_SECRET=jwt-secret-key-here

# MySQL Root Password (for container)
MYSQL_ROOT_PASSWORD=mysql_root_password
```

### Docker Environment File

```env
# .env.docker - Docker-specific overrides
MQTT_BROKER=mosquitto
DB_HOST=mysql
REDIS_HOST=redis
```

## Supporting Configuration Files

### Mosquitto Configuration

Create `docker/mosquitto/mosquitto.conf`:

```conf
# docker/mosquitto/mosquitto.conf
listener 1883
protocol mqtt

listener 9001
protocol websockets

# Persistence
persistence true
persistence_location /mosquitto/data/

# Logging
log_dest file /mosquitto/log/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information

# Security
allow_anonymous false
password_file /mosquitto/config/passwd

# Shared subscriptions (for scaling)
max_queued_messages 1000
message_size_limit 268435456
```

### Mosquitto Password File

Create `docker/mosquitto/passwd`:

```bash
# Generate password file
docker run -it --rm -v $(pwd)/docker/mosquitto:/mosquitto/config eclipse-mosquitto:2.0 \
  mosquitto_passwd -c /mosquitto/config/passwd routemq_user

# Or manually create (replace with actual hash)
echo "routemq_user:$6$hash_here" > docker/mosquitto/passwd
```

### MySQL Initialization

Create `docker/mysql/init/01-init.sql`:

```sql
-- docker/mysql/init/01-init.sql
-- Database initialization script

CREATE DATABASE IF NOT EXISTS routemq_production 
  CHARACTER SET utf8mb4 
  COLLATE utf8mb4_unicode_ci;

-- Create application user
CREATE USER IF NOT EXISTS 'routemq_user'@'%' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON routemq_production.* TO 'routemq_user'@'%';

-- Create read-only user for monitoring
CREATE USER IF NOT EXISTS 'routemq_readonly'@'%' IDENTIFIED BY 'readonly_password';
GRANT SELECT ON routemq_production.* TO 'routemq_readonly'@'%';

FLUSH PRIVILEGES;

USE routemq_production;

-- Create RouteMQ-managed tables here, or set DB_AUTO_CREATE_TABLES=true
-- for controlled development environments.
```

### Redis Configuration

Create `docker/redis/redis.conf`:

```conf
# docker/redis/redis.conf
# Redis configuration for production

# Network
bind 0.0.0.0
port 6379
timeout 300

# Persistence
save 900 1
save 300 10
save 60 10000

appendonly yes
appendfsync everysec

# Memory
maxmemory 256mb
maxmemory-policy allkeys-lru

# Security
requirepass redis_secure_password

# Logging
loglevel notice
```

## Development vs Production

### Development Setup

The root `Dockerfile` has no `development` target and installs no development dependencies. Run Redis, MySQL,
and ClickHouse from `docker-compose.dev.yml` and run the app on the host:

```bash
docker compose -f docker-compose.dev.yml up -d
uv run routemq run
```

To run the app in a container too, start the optional `full` profile. It builds the same `runtime` image and
bind-mounts `./app` and `./bootstrap` into `/app`. `PYTHONPATH=/app` loads the mounted source ahead of the
installed packages, and the environment in `/opt/venv` is unaffected.

```bash
docker compose -f docker-compose.dev.yml --profile full up -d
```

### Production Setup

Production uses the same `runtime` image. Build and tag it, then reference the tag:

```bash
docker build -t routemq:production .
```

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  routemq:
    image: routemq:production
    environment:
      - LOG_LEVEL=INFO
      - ENABLE_MYSQL=true
    volumes:
      - ./app:/app/app:ro  # Read-only application code
      - ./logs:/app/logs   # Logs volume
    deploy:
      replicas: 3  # Multiple instances for HA
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
```

## Multi-Stage Dockerfile

The root `Dockerfile` is already multi-stage: `uv` and `builder` produce `/opt/venv`, and `runtime` is the image you
run. See [Dockerfile Explanation](#dockerfile-explanation). There are no separate development and production
stages to select with `--target`.

## Container Commands

### Build Commands

```bash
# Build the runtime image
docker build -t routemq:latest .

# Build with specific version
docker build -t routemq:v1.0.0 .
```

### Run Commands

```bash
# Run with the local checkout mounted over /app; the environment stays in /opt/venv
docker run -it --rm \
  -v $(pwd):/app \
  -e LOG_LEVEL=DEBUG \
  routemq:latest

# Run production container
docker run -d \
  --name routemq-prod \
  -e MQTT_BROKER=mqtt.example.com \
  --restart unless-stopped \
  routemq:v1.0.0

# Run a queue worker instead of the default app command
docker run -d --name routemq-worker routemq:v1.0.0 \
  /opt/venv/bin/routemq queue-work --queue default --sleep 3

# Run with custom command
docker run -it --rm routemq:latest /opt/venv/bin/python -c "print('Hello')"
```

### Management Commands

```bash
# View logs
docker logs -f routemq

# Execute commands in running container
docker exec -it routemq bash

# Inspect container
docker inspect routemq

# View resource usage
docker stats routemq
```

## Troubleshooting

### Common Issues

**Container Won't Start**
```bash
# Check logs
docker logs routemq

# Check configuration
docker run --rm routemq:latest env

# Verify the runtime dependencies and extras import
docker run --rm routemq:latest /opt/venv/bin/python -c "import paho.mqtt.client, redis, clickhouse_connect, prometheus_client"
```

**Database Connection Issues**
```bash
# Test MySQL connection
docker run --rm --network routemq_routemq-network mysql:8.0 \
  mysql -h mysql -u routemq_user -p -e "SHOW DATABASES;"

# Check network connectivity
docker run --rm --network routemq_routemq-network routemq:latest \
  /opt/venv/bin/python -c "import socket; socket.create_connection(('mysql', 3306), timeout=5); print('mysql:3306 reachable')"
```

**Memory Issues**
```bash
# Monitor memory usage
docker stats

# Increase memory limits
docker run -m 1g routemq:latest
```

### Health Checks

```bash
# Run the image's readiness probe; exit code 0 means /ready passed
docker exec routemq /opt/venv/bin/python -m routemq.healthcheck; echo $?

# Read the readiness payload on the default health port
docker exec routemq curl -s http://127.0.0.1:8080/ready

# Show the results Docker recorded for the image HEALTHCHECK
docker inspect --format '{{json .State.Health}}' routemq
```

App readiness covers startup and the MQTT connection; it does not check MySQL or Redis. A queue worker
container's `/ready` checks the worker loop and its queue backend instead: Redis `PING`, or `SELECT 1` plus the
queue tables for the database queue. To test MySQL directly, use the MySQL client shown under Database Connection
Issues. Docker marks a failing container `unhealthy` but does not restart it; see
[Health Checks](../monitoring/health-checks.md).

## Security Considerations

### Container Security

The root image already runs as the non-root `app` system user without a login shell, and its source and
`/opt/venv` are root-owned. Further restrictions are run-time options:

```bash
# Read-only file system (where possible)
# docker run --read-only routemq:latest

# Drop capabilities
# docker run --cap-drop ALL routemq:latest
```

### Network Security

```yaml
# Isolate networks
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # No external access

services:
  routemq:
    networks:
      - frontend
      - backend
  
  mysql:
    networks:
      - backend  # Only internal access
```

### Secrets Management

```yaml
# Use Docker secrets
secrets:
  db_password:
    file: ./secrets/db_password.txt
  mqtt_password:
    file: ./secrets/mqtt_password.txt

services:
  routemq:
    secrets:
      - db_password
      - mqtt_password
    environment:
      DB_PASS_FILE: /run/secrets/db_password
      MQTT_PASSWORD_FILE: /run/secrets/mqtt_password
```

## Performance Optimization

### Resource Limits

```yaml
services:
  routemq:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M
```

### Volume Optimization

```yaml
volumes:
  # Use named volumes for better performance
  - mysql_data:/var/lib/mysql
  
  # Mount application code read-only
  - ./app:/app/app:ro
  
  # Use tmpfs for temporary files
  - type: tmpfs
    target: /tmp
    tmpfs:
      size: 100M
```

## Next Steps

- [Configuration Reference](../configuration/environment-variables.md) - Configure production settings
- [Scaling](scaling.md) - Scale your Docker deployment
- [Load Balancing](load-balancing.md) - Distribute traffic across containers
- [Security](../security.md) - Secure your containerized deployment
