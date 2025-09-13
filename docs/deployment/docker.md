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

# Run with default settings
docker run -d \
  --name routemq \
  -e MQTT_BROKER=test.mosquitto.org \
  -e MQTT_PORT=1883 \
  -p 8080:8080 \
  routemq:latest
```

### Docker Compose (Recommended)

Use the included `docker-compose.yml` for a complete stack:

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f routemq

# Stop all services
docker-compose down
```

## Dockerfile Explanation

The RouteMQ Dockerfile uses a multi-stage approach optimized for production:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy dependency files and install dependencies
COPY pyproject.toml uv.lock* ./
COPY . .
RUN uv sync

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app

# Health check
RUN uv run python -c "import sys; sys.exit(0)"

CMD ["uv", "run", "python", "main.py", "--run"]
```

### Key Features

- **Python 3.12**: Latest stable Python version
- **UV Package Manager**: Fast dependency resolution and installation
- **Non-root User**: Security best practice
- **Optimized Layers**: Minimal image size with dependency caching
- **Health Checks**: Built-in application health verification

## Docker Compose Configuration

### Complete Stack

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

    healthcheck:
      test: ["CMD", "python", "-c", "import paho.mqtt.client as mqtt; print('Health check passed')"]
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

-- Create initial tables (optional - app will create them)
-- Tables will be created automatically by the application
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

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  routemq:
    build: 
      context: .
      target: development
    environment:
      - LOG_LEVEL=DEBUG
      - ENABLE_MYSQL=false  # Use SQLite for development
    volumes:
      - .:/app  # Mount entire project for live reloading
    ports:
      - "8000:8000"  # Expose for debugging
```

### Production Setup

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

For optimized production builds:

```dockerfile
# Dockerfile.multi-stage
FROM python:3.12-slim as base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Development stage
FROM base as development

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install dependencies including dev dependencies
COPY pyproject.toml uv.lock* ./
RUN uv sync --dev

COPY . .

CMD ["uv", "run", "python", "main.py", "--run"]

# Production stage
FROM base as production

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install only production dependencies
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app

CMD ["uv", "run", "python", "main.py", "--run"]
```

## Container Commands

### Build Commands

```bash
# Build development image
docker build -t routemq:dev --target development .

# Build production image
docker build -t routemq:prod --target production .

# Build with specific version
docker build -t routemq:v1.0.0 .
```

### Run Commands

```bash
# Run development container
docker run -it --rm \
  -v $(pwd):/app \
  -e LOG_LEVEL=DEBUG \
  routemq:dev

# Run production container
docker run -d \
  --name routemq-prod \
  -e MQTT_BROKER=mqtt.example.com \
  --restart unless-stopped \
  routemq:prod

# Run with custom command
docker run -it --rm routemq:prod uv run python -c "print('Hello')"
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

# Verify dependencies
docker run --rm routemq:latest uv run python -c "import paho.mqtt.client"
```

**Database Connection Issues**
```bash
# Test MySQL connection
docker run --rm --network routemq_routemq-network mysql:8.0 \
  mysql -h mysql -u routemq_user -p -e "SHOW DATABASES;"

# Check network connectivity
docker run --rm --network routemq_routemq-network routemq:latest \
  ping mysql
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
# Check application health
docker exec routemq python -c "
import paho.mqtt.client as mqtt
client = mqtt.Client()
try:
    client.connect('mosquitto', 1883)
    print('MQTT connection: OK')
except:
    print('MQTT connection: FAILED')
"

# Check database health
docker exec routemq python -c "
from core.model import Model
import asyncio

async def test_db():
    try:
        session = await Model.get_session()
        print('Database connection: OK')
    except:
        print('Database connection: FAILED')

asyncio.run(test_db())
"
```

## Security Considerations

### Container Security

```dockerfile
# Use non-root user
RUN useradd --create-home --shell /bin/bash app
USER app

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

- [Production Configuration](production-config.md) - Configure for production deployment
- [Scaling](scaling.md) - Scale your Docker deployment
- [Load Balancing](load-balancing.md) - Distribute traffic across containers
- [Security](security.md) - Secure your containerized deployment
