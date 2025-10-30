# Queue Drivers

RouteMQ supports two queue drivers: Redis and Database. This guide explains how they work and when to use each.

## Overview

Queue drivers handle the storage and retrieval of jobs. The driver you choose affects:

- **Performance** - How fast jobs are queued and processed
- **Persistence** - Whether jobs survive crashes
- **Infrastructure** - What services you need to run
- **Scalability** - How well it handles high job volumes

## Redis Queue Driver

Fast, in-memory queue backed by Redis.

### Features

- ✅ **Very fast** - In-memory storage for low latency
- ✅ **High throughput** - Handles thousands of jobs/second
- ✅ **Atomic operations** - Uses RPOPLPUSH for safe job claiming
- ✅ **Delayed jobs** - Efficient sorted sets for scheduling
- ✅ **Scalable** - Easy to cluster Redis for more capacity

###Requirements

- Redis server running (v5.0+)
- `ENABLE_REDIS=true` in `.env`
- `QUEUE_CONNECTION=redis` in `.env`

### Configuration

```env
# Enable Redis
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Use Redis for queue
QUEUE_CONNECTION=redis
```

### Data Structures

Redis queue uses different data structures for different purposes:

| Structure | Purpose | Type |
|-----------|---------|------|
| `routemq:queue:{name}` | Pending jobs | List (FIFO) |
| `routemq:queue:{name}:delayed` | Delayed jobs | Sorted Set (by timestamp) |
| `routemq:queue:{name}:reserved` | Processing jobs | List |
| `routemq:queue:failed:{name}` | Failed jobs | List |

### How It Works

**Pushing a job:**
```
1. Job serialized to JSON
2. RPUSH to routemq:queue:{name}
3. Job ID returned
```

**Popping a job:**
```
1. Check for delayed jobs ready to process
2. RPOPLPUSH from pending to reserved
3. Increment attempts
4. Return job data
```

**Completing a job:**
```
1. LREM from reserved list
2. Job deleted
```

**Failing a job:**
```
1. If attempts < max_tries:
   - LREM from reserved
   - RPUSH back to pending (or delayed)
2. Else:
   - Move to failed list
   - LREM from reserved
```

### Advantages

- **Speed**: Sub-millisecond latency
- **Throughput**: Handle high job volumes
- **Simple**: No complex queries needed
- **Scalable**: Easy to add Redis replicas

### Disadvantages

- **Volatility**: Jobs lost if Redis crashes (unless AOF enabled)
- **Infrastructure**: Requires Redis server
- **Memory**: All jobs stored in RAM

### Best For

- High-volume applications
- Real-time job processing
- When you already use Redis
- When speed is critical

## Database Queue Driver

Persistent queue backed by MySQL.

### Features

- ✅ **Persistent** - Jobs survive crashes
- ✅ **ACID** - Transactional guarantees
- ✅ **Inspectable** - Easy to query with SQL
- ✅ **Reliable** - No job loss
- ✅ **No extra service** - Uses existing MySQL

### Requirements

- MySQL server running (v8.0+)
- `ENABLE_MYSQL=true` in `.env`
- `QUEUE_CONNECTION=database` in `.env`

### Configuration

```env
# Enable MySQL
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password

# Use database for queue
QUEUE_CONNECTION=database
```

### Database Tables

**queue_jobs:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Primary key |
| `queue` | VARCHAR(255) | Queue name |
| `payload` | TEXT | Serialized job data |
| `attempts` | INT | Number of attempts |
| `reserved_at` | DATETIME | When job was claimed (NULL if pending) |
| `available_at` | DATETIME | When job becomes available |
| `created_at` | DATETIME | When job was created |

**queue_failed_jobs:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Primary key |
| `connection` | VARCHAR(255) | Connection name |
| `queue` | VARCHAR(255) | Queue name |
| `payload` | TEXT | Serialized job data |
| `exception` | TEXT | Exception details |
| `failed_at` | DATETIME | When job failed |

### How It Works

**Pushing a job:**
```sql
INSERT INTO queue_jobs
(queue, payload, attempts, available_at, created_at)
VALUES (?, ?, 0, ?, NOW())
```

**Popping a job:**
```sql
-- Use FOR UPDATE SKIP LOCKED for concurrency
SELECT * FROM queue_jobs
WHERE queue = ?
  AND reserved_at IS NULL
  AND available_at <= NOW()
ORDER BY id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Mark as reserved
UPDATE queue_jobs
SET reserved_at = NOW(), attempts = attempts + 1
WHERE id = ?
```

**Completing a job:**
```sql
DELETE FROM queue_jobs WHERE id = ?
```

**Failing a job:**
```sql
-- If retrying
UPDATE queue_jobs
SET reserved_at = NULL,
    available_at = DATE_ADD(NOW(), INTERVAL ? SECOND)
WHERE id = ?

-- If permanently failed
INSERT INTO queue_failed_jobs
(connection, queue, payload, exception, failed_at)
VALUES (?, ?, ?, ?, NOW());

DELETE FROM queue_jobs WHERE id = ?
```

### Advantages

- **Persistence**: Jobs survive crashes
- **Reliability**: ACID transactions
- **Visibility**: Easy to inspect with SQL
- **Simplicity**: No additional infrastructure

### Disadvantages

- **Speed**: Slower than Redis (disk I/O)
- **Load**: Increases database queries
- **Scaling**: Harder to scale than Redis

### Best For

- Low to medium job volumes
- When persistence is critical
- When you don't want to manage Redis
- When you need to inspect jobs easily

## Comparison

| Feature | Redis | Database |
|---------|-------|----------|
| **Speed** | ⭐⭐⭐⭐⭐ Very Fast | ⭐⭐⭐ Moderate |
| **Persistence** | ⭐⭐ Configurable | ⭐⭐⭐⭐⭐ Always |
| **Scalability** | ⭐⭐⭐⭐⭐ Excellent | ⭐⭐⭐ Good |
| **Reliability** | ⭐⭐⭐ Good | ⭐⭐⭐⭐⭐ Excellent |
| **Setup** | ⭐⭐⭐ Need Redis | ⭐⭐⭐⭐⭐ Use existing DB |
| **Inspection** | ⭐⭐⭐ Redis CLI | ⭐⭐⭐⭐⭐ SQL queries |
| **Memory** | ⭐⭐ All in RAM | ⭐⭐⭐⭐⭐ On disk |

## Switching Drivers

You can switch drivers at any time:

```env
# Change in .env
QUEUE_CONNECTION=redis  # or 'database'
```

**Important notes:**
- Jobs in the old driver won't be transferred
- Complete existing jobs before switching
- Or manually migrate jobs between drivers

## Performance Tips

### Redis

```env
# Use a dedicated Redis database
REDIS_DB=1  # Separate from cache

# Enable persistence (optional)
# In redis.conf:
# appendonly yes
# appendfsync everysec
```

### Database

```sql
-- Add indexes for performance
CREATE INDEX idx_queue_reserved ON queue_jobs(queue, reserved_at);
CREATE INDEX idx_available ON queue_jobs(available_at);

-- Monitor slow queries
SHOW FULL PROCESSLIST;
```

## Monitoring

### Redis

```bash
# Connect to Redis
redis-cli

# Check queue sizes
LLEN routemq:queue:default
LLEN routemq:queue:emails
LLEN routemq:queue:reports

# Check delayed jobs
ZCARD routemq:queue:default:delayed

# View pending jobs
LRANGE routemq:queue:default 0 9

# Check memory usage
INFO memory

# Monitor commands
MONITOR
```

### Database

```sql
-- Check pending jobs by queue
SELECT queue, COUNT(*) as pending_jobs
FROM queue_jobs
WHERE reserved_at IS NULL
GROUP BY queue;

-- Check processing jobs
SELECT queue, COUNT(*) as processing_jobs
FROM queue_jobs
WHERE reserved_at IS NOT NULL
GROUP BY queue;

-- Check job age
SELECT queue,
       MIN(created_at) as oldest_job,
       MAX(created_at) as newest_job,
       COUNT(*) as total_jobs
FROM queue_jobs
GROUP BY queue;

-- Check failed jobs
SELECT queue, COUNT(*) as failed_jobs
FROM queue_failed_jobs
GROUP BY queue;

-- Find stuck jobs (reserved > 1 hour ago)
SELECT * FROM queue_jobs
WHERE reserved_at < DATE_SUB(NOW(), INTERVAL 1 HOUR);
```

## Troubleshooting

### Redis Connection Issues

```bash
# Test connection
redis-cli ping

# Check if Redis is running
redis-cli INFO server

# Restart Redis
# macOS: brew services restart redis
# Linux: sudo systemctl restart redis
```

### Database Connection Issues

```bash
# Test connection
mysql -h localhost -u root -p -e "SELECT 1"

# Check if MySQL is running
sudo systemctl status mysql

# Check for locks
mysql> SHOW PROCESSLIST;
mysql> SHOW OPEN TABLES WHERE In_use > 0;
```

### Jobs Not Processing

1. **Check driver configuration:**
   ```env
   QUEUE_CONNECTION=redis  # Match your setup
   ```

2. **Verify service is running:**
   ```bash
   # Redis
   redis-cli ping

   # MySQL
   mysql -h localhost -u root -p -e "SELECT 1"
   ```

3. **Check worker connection:**
   ```bash
   python main.py --queue-work --connection redis
   python main.py --queue-work --connection database
   ```

## Best Practices

### 1. Choose Based on Requirements

```
High volume, speed critical → Redis
Persistence critical → Database
Low volume, simple setup → Database
Already using Redis → Redis
```

### 2. Monitor Both

Even if using Redis, keep failed jobs in database:

```python
# RedisQueue already does this
await driver.failed(connection, queue, payload, exception)
# Stores in database if available
```

### 3. Regular Cleanup

```sql
-- Clean old failed jobs (> 30 days)
DELETE FROM queue_failed_jobs
WHERE failed_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

### 4. Backup Important Queues

```bash
# Redis
redis-cli SAVE
cp /var/lib/redis/dump.rdb /backup/

# MySQL
mysqldump -u root -p mqtt_framework queue_jobs > backup.sql
```

## Next Steps

- [Handle failed jobs](./failed-jobs.md)
- [Review best practices](./best-practices.md)
- [Docker deployment](../docker-deployment.md)
