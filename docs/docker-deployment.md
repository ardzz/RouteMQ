# Docker Deployment Guide

This guide explains how to deploy RouteMQ with queue workers using Docker and Docker Compose.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Production Deployment](#production-deployment)
- [Development Setup](#development-setup)
- [Scaling Workers](#scaling-workers)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Architecture Overview

The Docker deployment includes:

```
┌─────────────────────────────────────────────────────┐
│                  Docker Network                      │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │  Redis   │  │  MySQL   │  │ RouteMQ  │          │
│  │  :6379   │  │  :3306   │  │   App    │          │
│  └────┬─────┘  └────┬─────┘  └──────────┘          │
│       │             │                                │
│       ├─────────────┼────────────────┐              │
│       │             │                │              │
│  ┌────▼────┐  ┌─────▼────┐  ┌───────▼──────┐      │
│  │ Queue   │  │  Queue   │  │    Queue     │      │
│  │ Worker  │  │  Worker  │  │   Worker     │      │
│  │(default)│  │  (high)  │  │  (emails)    │      │
│  └─────────┘  └──────────┘  └──────────────┘      │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### Services

1. **redis** - Fast, in-memory queue backend
2. **mysql** - Persistent storage and database queue
3. **routemq** - Main MQTT application
4. **queue-worker-default** - Processes jobs from 'default' queue
5. **queue-worker-high** - Processes jobs from 'high-priority' queue (faster polling)
6. **queue-worker-emails** - Processes jobs from 'emails' queue

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+

### 1. Prepare Environment File

```bash
# Copy the Docker environment template
cp .env.docker .env

# Edit with your settings
nano .env
```

### 2. Start All Services

```bash
# Build and start all services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f
```

### 3. Verify Deployment

```bash
# Check RouteMQ app logs
docker compose logs routemq

# Check queue worker logs
docker compose logs queue-worker-default

# Check Redis connection
docker compose exec redis redis-cli ping

# Check MySQL connection
docker compose exec mysql mysql -uroot -p${DB_PASS} -e "SHOW DATABASES;"
```

## Production Deployment

### Environment Configuration

Create a `.env` file with production settings:

```env
# MQTT Broker (use your production broker)
MQTT_BROKER=mqtt.yourcompany.com
MQTT_PORT=1883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_secure_password
MQTT_GROUP_NAME=routemq_production

# MySQL (strong password!)
ENABLE_MYSQL=true
DB_HOST=mysql
DB_PORT=3306
DB_NAME=routemq_production
DB_USER=routemq
DB_PASS=YOUR_STRONG_PASSWORD_HERE

# Redis
ENABLE_REDIS=true
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Queue
QUEUE_CONNECTION=redis

# Timezone
TIMEZONE=UTC

# Logging
LOG_LEVEL=INFO
```

### Persistent Data

Data is stored in Docker volumes:

```bash
# List volumes
docker volume ls | grep routemq

# Backup MySQL data
docker compose exec mysql mysqldump -uroot -p${DB_PASS} routemq_production > backup.sql

# Backup Redis data
docker compose exec redis redis-cli SAVE
docker cp routemq-redis:/data/dump.rdb ./redis-backup.rdb
```

### Starting Services

```bash
# Start all services in production mode
docker compose up -d

# Verify all containers are running
docker compose ps

# Check resource usage
docker stats
```

### Updating Deployment

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose build
docker compose up -d

# Or rebuild specific service
docker compose build routemq
docker compose up -d routemq
```

## Development Setup

For local development, use the minimal development compose file:

```bash
# Start only Redis and MySQL
docker compose -f docker-compose.dev.yml up -d

# Run RouteMQ app on host for hot reload
uv run python main.py --run

# Run queue worker on host
uv run python main.py --queue-work --queue default
```

Or start everything including the app:

```bash
# Start all services including app
docker compose -f docker-compose.dev.yml --profile full up -d
```

## Scaling Workers

### Add More Workers for Same Queue

Edit `docker-compose.yml` to add more worker instances:

```yaml
# Add a second worker for default queue
queue-worker-default-2:
  build:
    context: .
  container_name: routemq-queue-default-2
  command: ["uv", "run", "python", "main.py", "--queue-work", "--queue", "default", "--sleep", "3"]
  # ... same environment as queue-worker-default
```

Or scale using Docker Compose:

```bash
# Scale default queue workers to 3 instances
docker compose up -d --scale queue-worker-default=3
```

### Add Workers for New Queues

To add a worker for a custom queue:

```yaml
queue-worker-reports:
  build:
    context: .
  container_name: routemq-queue-reports
  command: ["uv", "run", "python", "main.py", "--queue-work", "--queue", "reports", "--sleep", "10"]
  environment:
    # ... same as other workers
  depends_on:
    - mysql
    - redis
  networks:
    - routemq-network
  restart: unless-stopped
```

### Resource Allocation

Adjust resources per worker based on workload:

```yaml
queue-worker-heavy:
  deploy:
    resources:
      limits:
        cpus: '1.0'    # Allow 1 full CPU
        memory: 512M   # 512MB RAM
      reservations:
        cpus: '0.5'
        memory: 256M
```

## Monitoring

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f queue-worker-default

# Last 100 lines
docker compose logs --tail=100 routemq

# Logs from specific time
docker compose logs --since 2h queue-worker-emails
```

### Resource Usage

```bash
# Real-time stats
docker stats

# Check specific container
docker stats routemq-queue-default
```

### Queue Status

Connect to Redis to check queue status:

```bash
# Connect to Redis CLI
docker compose exec redis redis-cli

# Check queue length
LLEN routemq:queue:default
LLEN routemq:queue:emails

# Check delayed jobs
ZCARD routemq:queue:default:delayed

# View queue contents (first 10 items)
LRANGE routemq:queue:default 0 9
```

Check database queue:

```bash
# Connect to MySQL
docker compose exec mysql mysql -uroot -p${DB_PASS} routemq_production

# Check queue jobs
SELECT queue, COUNT(*) as pending_jobs
FROM queue_jobs
WHERE reserved_at IS NULL
GROUP BY queue;

# Check failed jobs
SELECT queue, COUNT(*) as failed_jobs
FROM queue_failed_jobs
GROUP BY queue;
```

### Health Checks

All services include health checks:

```bash
# View health status
docker compose ps

# Manually check health
docker inspect routemq-redis | grep -A 10 Health
docker inspect routemq-mysql | grep -A 10 Health
docker inspect routemq-app | grep -A 10 Health
```

## Service Management

### Start/Stop Services

```bash
# Stop all services
docker compose stop

# Start all services
docker compose start

# Restart specific service
docker compose restart queue-worker-default

# Stop and remove containers (keeps volumes)
docker compose down

# Stop and remove everything including volumes
docker compose down -v
```

### Update Configuration

After changing `.env`:

```bash
# Recreate containers with new config
docker compose up -d --force-recreate

# Or restart specific service
docker compose up -d --force-recreate routemq
```

## Troubleshooting

### Workers Not Processing Jobs

**Check worker logs:**
```bash
docker compose logs queue-worker-default
```

**Common issues:**
- Worker not connected to Redis/MySQL
- Queue name mismatch
- Jobs failing during processing

**Solutions:**
```bash
# Restart worker
docker compose restart queue-worker-default

# Check Redis connection
docker compose exec redis redis-cli ping

# Check MySQL connection
docker compose exec mysql mysqladmin ping -h localhost
```

### Redis Connection Issues

```bash
# Check if Redis is running
docker compose ps redis

# Check Redis logs
docker compose logs redis

# Test connection
docker compose exec redis redis-cli ping
```

### MySQL Connection Issues

```bash
# Check if MySQL is running
docker compose ps mysql

# Check MySQL logs
docker compose logs mysql

# Test connection
docker compose exec mysql mysql -uroot -p${DB_PASS} -e "SELECT 1"
```

### High Memory Usage

```bash
# Check memory usage
docker stats

# Reduce worker limits in docker-compose.yml
queue-worker-default:
  deploy:
    resources:
      limits:
        memory: 128M  # Reduce from 256M
```

### Container Won't Start

```bash
# View detailed logs
docker compose logs [service-name]

# Check for port conflicts
netstat -tulpn | grep :6379
netstat -tulpn | grep :3306

# Remove and recreate
docker compose down
docker compose up -d
```

### Database Tables Not Created

```bash
# Connect to RouteMQ container and create tables manually
docker compose exec routemq python -c "
import asyncio
from bootstrap.app import Application

async def create_tables():
    app = Application()
    await app.initialize_database()
    print('Tables created!')

asyncio.run(create_tables())
"
```

## Best Practices

### 1. Use Docker Secrets for Production

Instead of plain text passwords in `.env`:

```yaml
services:
  mysql:
    environment:
      MYSQL_ROOT_PASSWORD_FILE: /run/secrets/mysql_root_password
    secrets:
      - mysql_root_password

secrets:
  mysql_root_password:
    file: ./secrets/mysql_root_password.txt
```

### 2. Regular Backups

Set up automated backups:

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)

# Backup MySQL
docker compose exec mysql mysqldump -uroot -p${DB_PASS} routemq_production > backup_mysql_${DATE}.sql

# Backup Redis
docker compose exec redis redis-cli SAVE
docker cp routemq-redis:/data/dump.rdb backup_redis_${DATE}.rdb

echo "Backup completed: ${DATE}"
```

### 3. Log Rotation

Configure log rotation in `docker-compose.yml`:

```yaml
routemq:
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"
```

### 4. Monitoring and Alerts

Use Docker health checks and monitoring tools:

```yaml
routemq:
  healthcheck:
    test: ["CMD", "python", "-c", "import paho.mqtt.client; print('OK')"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s
```

### 5. Resource Limits

Always set resource limits in production:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
    reservations:
      cpus: '0.5'
      memory: 256M
```

## Example Deployment Scenarios

### Scenario 1: Small Deployment (Single Server)

```bash
# Use default docker-compose.yml
docker compose up -d
```

**Resources:** 1 app + 3 workers + Redis + MySQL

### Scenario 2: Medium Deployment (High Load)

Scale workers:

```bash
docker compose up -d --scale queue-worker-default=5 --scale queue-worker-emails=3
```

**Resources:** 1 app + 8+ workers + Redis + MySQL

### Scenario 3: Development

```bash
# Start only dependencies
docker compose -f docker-compose.dev.yml up -d

# Run app on host
uv run python main.py --run

# Run worker on host
uv run python main.py --queue-work
```

## Summary

The Docker deployment provides:

- ✅ Complete stack with Redis and MySQL
- ✅ Multiple queue workers out of the box
- ✅ Easy scaling and configuration
- ✅ Health checks and auto-restart
- ✅ Resource limits for stability
- ✅ Development and production setups

For more information, see:
- [Queue System Documentation](../docs/queue-system.md)
- [RouteMQ Documentation](../README.md)
