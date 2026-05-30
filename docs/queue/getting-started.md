# Getting Started with Queue System

This guide will help you set up and configure the RouteMQ queue system.

## Prerequisites

You'll need one of the following:

- **Redis** - Fast, in-memory queue for high-throughput workloads
- **Relational database** - Persistent queue storage with MySQL or PostgreSQL

## Installation

The queue API is included with base `routemq`. Redis support is optional and must be installed when `QUEUE_CONNECTION=redis`.

```bash
uv add routemq                  # database queue support is in the base package
uv add "routemq[redis]"         # Redis queue support

# pip works too:
pip install routemq
pip install "routemq[redis]"
```

## Configuration

### 1. Choose Your Queue Driver

Edit your `.env` file:

```env
# Queue Configuration
QUEUE_CONNECTION=redis  # or 'database'
```

### 2. Configure Redis

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
# Enable the relational database integration
ENABLE_MYSQL=true
DB_CONNECTION=mysql  # mysql or postgres
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASSWORD=your_password
# DATABASE_URL=mysql://root:your_password@localhost:3306/mqtt_framework
DB_AUTO_CREATE_TABLES=false

# Queue connection
QUEUE_CONNECTION=database
```

**Create tables:**

The queue tables are not created automatically unless you set `DB_AUTO_CREATE_TABLES=true`. Keep the
default `false` in shared environments and create these tables through your own migration flow:

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

**Best for:** High-throughput queues and latency-sensitive jobs

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

# Using PostgreSQL client
psql "$DATABASE_URL" -c "SELECT 1;"

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
| `ENABLE_MYSQL` | `true` | Legacy flag for relational database integration |
| `DB_CONNECTION` | `mysql` | Database selector: `mysql` or `postgres` |
| `DATABASE_URL` | - | Full SQLAlchemy database URL. Wins over individual `DB_*` fields. |
| `DB_HOST` | `localhost` | Database server hostname |
| `DB_PORT` | `3306` for MySQL, `5432` for PostgreSQL | Database server port |
| `DB_NAME` | `mqtt_framework` | Database name |
| `DB_USER` | `root` | Database username |
| `DB_PASSWORD` | - | Database password. Preferred over `DB_PASS`. |
| `DB_PASS` | - | Legacy database password fallback |
| `DB_AUTO_CREATE_TABLES` | `false` | Create RouteMQ-managed tables during startup |

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

# Test MySQL connection
mysql -h localhost -u root -p

# Test PostgreSQL connection
psql "$DATABASE_URL" -c "SELECT 1"

# Check credentials in .env file
```

### Workers Not Processing Jobs

1. Verify queue configuration matches between app and worker
2. Check worker logs: `docker compose logs queue-worker-default`
3. Ensure Redis or the configured database is accessible
4. Verify queue name matches in dispatch and worker
