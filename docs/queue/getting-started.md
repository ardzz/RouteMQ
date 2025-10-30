# Getting Started with Queue System

This guide will help you set up and configure the RouteMQ queue system.

## Prerequisites

You'll need one of the following:

- **Redis** (recommended for production) - Fast, in-memory queue
- **MySQL** - Persistent, database-backed queue

## Installation

The queue system is included with RouteMQ. No additional installation required.

## Configuration

### 1. Choose Your Queue Driver

Edit your `.env` file:

```env
# Queue Configuration
QUEUE_CONNECTION=redis  # or 'database'
```

### 2. Configure Redis (Recommended)

If using Redis queue:

```env
# Enable Redis
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Queue connection
QUEUE_CONNECTION=redis
```

**Install Redis:**
```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis

# Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### 3. Configure Database Queue (Alternative)

If using database queue:

```env
# Enable MySQL
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password

# Queue connection
QUEUE_CONNECTION=database
```

**Create Tables:**

The queue tables will be created automatically when you start the application. They include:

- `queue_jobs` - Stores pending and reserved jobs
- `queue_failed_jobs` - Stores permanently failed jobs

## Queue Drivers Comparison

### Redis Driver

**Pros:**
- ✅ Very fast (in-memory)
- ✅ Low latency
- ✅ Excellent for high-throughput
- ✅ Supports delayed jobs
- ✅ Built-in sorted sets for delays

**Cons:**
- ⚠️ Requires Redis server
- ⚠️ Jobs lost if Redis crashes (unless persistence enabled)
- ⚠️ Additional infrastructure

**Best for:** Production environments with high job volumes

### Database Driver

**Pros:**
- ✅ Persistent storage
- ✅ ACID transactions
- ✅ No additional services needed
- ✅ Reliable job storage
- ✅ Easy to inspect jobs with SQL

**Cons:**
- ⚠️ Slower than Redis
- ⚠️ Higher database load
- ⚠️ May need index optimization for large queues

**Best for:** Low to medium job volumes, or when Redis isn't available

## Verify Configuration

### Test Redis Connection

```bash
# Using Redis CLI
redis-cli ping
# Should return: PONG

# In Python
python -c "
import redis
r = redis.Redis(host='localhost', port=6379)
print(r.ping())  # Should print: True
"
```

### Test Database Connection

```bash
# Using MySQL client
mysql -h localhost -u root -p -e "SHOW DATABASES;"

# In Python
python -c "
import asyncio
from bootstrap.app import Application

async def test():
    app = Application()
    await app.initialize_database()
    print('Database connected!')

asyncio.run(test())
"
```

## Docker Setup

For Docker, use the provided configuration:

```bash
# Start all services (includes Redis and MySQL)
docker compose up -d

# Check services
docker compose ps

# View worker logs
docker compose logs -f queue-worker-default
```

See [Docker Deployment](../docker-deployment.md) for details.

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `QUEUE_CONNECTION` | `redis` | Queue driver: `redis` or `database` |
| `ENABLE_REDIS` | `false` | Enable Redis integration |
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_PASSWORD` | - | Redis password (optional) |
| `ENABLE_MYSQL` | `false` | Enable MySQL integration |
| `DB_HOST` | `localhost` | MySQL server hostname |
| `DB_PORT` | `3306` | MySQL server port |
| `DB_NAME` | `mqtt_framework` | MySQL database name |
| `DB_USER` | `root` | MySQL username |
| `DB_PASS` | - | MySQL password |

## Next Steps

Now that your queue is configured:

1. [Create your first job](./creating-jobs.md)
2. [Learn how to dispatch jobs](./dispatching-jobs.md)
3. [Run queue workers](./running-workers.md)

## Troubleshooting

### Redis Connection Failed

```bash
# Check if Redis is running
redis-cli ping

# Check Redis logs
# macOS: /usr/local/var/log/redis.log
# Linux: /var/log/redis/redis-server.log

# Restart Redis
# macOS: brew services restart redis
# Linux: sudo systemctl restart redis
```

### Database Connection Failed

```bash
# Check if MySQL is running
sudo systemctl status mysql

# Test connection
mysql -h localhost -u root -p

# Check credentials in .env file
```

### Workers Not Processing Jobs

1. Verify queue configuration matches between app and worker
2. Check worker logs: `docker compose logs queue-worker-default`
3. Ensure Redis/MySQL is accessible
4. Verify queue name matches in dispatch and worker
