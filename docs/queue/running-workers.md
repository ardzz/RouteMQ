# Running Queue Workers

Queue workers are background processes that fetch and execute jobs from the queue. This guide explains how to run and manage workers.

## Starting a Worker

### Basic Usage

Start a worker to process jobs from the default queue:

```bash
# Process jobs from 'default' queue
python main.py --queue-work

# Or using the routemq command
routemq --queue-work
```

The worker will:
- Connect to Redis/MySQL based on `QUEUE_CONNECTION`
- Poll the queue for jobs
- Execute jobs as they become available
- Automatically retry failed jobs
- Run until stopped (Ctrl+C)

## Worker Options

### --queue

Specify which queue to process:

```bash
python main.py --queue-work --queue emails
python main.py --queue-work --queue high-priority
python main.py --queue-work --queue reports
```

### --connection

Override the queue connection:

```bash
# Use Redis queue
python main.py --queue-work --connection redis

# Use database queue
python main.py --queue-work --connection database
```

### --max-jobs

Process a maximum number of jobs then stop:

```bash
# Process 100 jobs then exit
python main.py --queue-work --max-jobs 100

# Process 1 job then exit (useful for testing)
python main.py --queue-work --max-jobs 1
```

### --max-time

Run for a maximum time (in seconds) then stop:

```bash
# Run for 1 hour
python main.py --queue-work --max-time 3600

# Run for 8 hours
python main.py --queue-work --max-time 28800
```

### --sleep

Seconds to sleep when no jobs are available:

```bash
# Check every second (high priority queue)
python main.py --queue-work --sleep 1

# Check every 5 seconds (normal priority)
python main.py --queue-work --sleep 5

# Check every 10 seconds (low priority)
python main.py --queue-work --sleep 10
```

### --max-tries

Override the maximum retry attempts for all jobs:

```bash
# Retry failed jobs up to 5 times
python main.py --queue-work --max-tries 5

# Never retry (fail immediately)
python main.py --queue-work --max-tries 1
```

### --timeout

Maximum seconds a job can run:

```bash
# 2 minute timeout
python main.py --queue-work --timeout 120

# 10 minute timeout
python main.py --queue-work --timeout 600
```

## Multiple Workers

Run multiple workers for different queues:

```bash
# Terminal 1: High-priority queue (check every second)
python main.py --queue-work --queue high-priority --sleep 1

# Terminal 2: Default queue (check every 3 seconds)
python main.py --queue-work --queue default --sleep 3

# Terminal 3: Low-priority queue (check every 10 seconds)
python main.py --queue-work --queue low-priority --sleep 10

# Terminal 4: Email queue (dedicated worker)
python main.py --queue-work --queue emails --sleep 5
```

## Production Deployment

### Using Docker Compose

The easiest way to run workers in production:

```bash
# Start all services including workers
docker compose up -d

# Scale workers
docker compose up -d --scale queue-worker-default=5

# View worker logs
docker compose logs -f queue-worker-default
```

See [Docker Deployment](../docker-deployment.md) for details.

### Using Supervisor

For non-Docker deployments, use Supervisor:

```ini
; /etc/supervisor/conf.d/routemq-queue.conf

[program:routemq-queue-default]
command=/path/to/venv/bin/python main.py --queue-work --queue default --sleep 3
directory=/path/to/RouteMQ
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/routemq/queue-default.log
startsecs=10
stopwaitsecs=60

[program:routemq-queue-high]
command=/path/to/venv/bin/python main.py --queue-work --queue high-priority --sleep 1
directory=/path/to/RouteMQ
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/routemq/queue-high.log
startsecs=10
stopwaitsecs=60

[program:routemq-queue-emails]
command=/path/to/venv/bin/python main.py --queue-work --queue emails --sleep 5
directory=/path/to/RouteMQ
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/routemq/queue-emails.log
startsecs=10
stopwaitsecs=60
```

Then manage with supervisorctl:

```bash
# Reload configuration
sudo supervisorctl reread
sudo supervisorctl update

# Start workers
sudo supervisorctl start routemq-queue-default
sudo supervisorctl start routemq-queue-high
sudo supervisorctl start routemq-queue-emails

# Check status
sudo supervisorctl status

# View logs
sudo supervisorctl tail -f routemq-queue-default

# Restart worker
sudo supervisorctl restart routemq-queue-default

# Stop worker
sudo supervisorctl stop routemq-queue-default
```

### Using systemd

Create systemd service files:

```ini
# /etc/systemd/system/routemq-queue-default.service

[Unit]
Description=RouteMQ Queue Worker (Default)
After=network.target redis.service mysql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/RouteMQ
ExecStart=/path/to/venv/bin/python main.py --queue-work --queue default --sleep 3
Restart=always
RestartSec=10
StandardOutput=append:/var/log/routemq/queue-default.log
StandardError=append:/var/log/routemq/queue-default-error.log

[Install]
WantedBy=multi-user.target
```

Manage with systemctl:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable routemq-queue-default

# Start service
sudo systemctl start routemq-queue-default

# Check status
sudo systemctl status routemq-queue-default

# View logs
sudo journalctl -u routemq-queue-default -f

# Restart service
sudo systemctl restart routemq-queue-default

# Stop service
sudo systemctl stop routemq-queue-default
```

## Worker Lifecycle

Understanding how workers process jobs:

```
1. Worker Starts
   ↓
2. Connect to Queue (Redis/MySQL)
   ↓
3. Poll for Jobs
   ↓
   ├─ Job Available
   │  ↓
   │  Reserve Job (mark as processing)
   │  ↓
   │  Execute job.handle()
   │  ↓
   │  ├─ Success → Delete Job
   │  └─ Failure → Release or Move to Failed
   │  ↓
   │  Loop back to Poll
   │
   └─ No Jobs → Sleep → Loop back to Poll
```

## Graceful Shutdown

Workers handle shutdown signals gracefully:

```bash
# Send SIGTERM (recommended)
kill -TERM <pid>

# Or Ctrl+C (sends SIGINT)
^C

# Worker will:
# 1. Stop accepting new jobs
# 2. Finish current job
# 3. Clean up connections
# 4. Exit
```

## Monitoring Workers

### View Worker Output

```bash
# In terminal
python main.py --queue-work --queue default

# Output:
# 2024-01-15 10:30:00 - RouteMQ.QueueWorker - INFO - Queue worker started for queue 'default'
# 2024-01-15 10:30:05 - RouteMQ.QueueWorker - INFO - Processing job 123 (attempt 1)
# 2024-01-15 10:30:07 - RouteMQ.QueueWorker - INFO - Job 123 completed successfully
```

### Check Queue Size

```python
from core.queue.queue_manager import queue

# Check how many jobs are waiting
size = await queue.size("default")
print(f"Pending jobs: {size}")
```

### Monitor with Redis CLI

```bash
# Connect to Redis
redis-cli

# Check queue length
LLEN routemq:queue:default

# Check delayed jobs
ZCARD routemq:queue:default:delayed

# Check reserved jobs
LLEN routemq:queue:default:reserved

# View queue contents
LRANGE routemq:queue:default 0 9  # First 10 jobs
```

### Monitor with MySQL

```sql
-- Connect to MySQL
mysql -u root -p routemq_production

-- Check pending jobs
SELECT queue, COUNT(*) as pending
FROM queue_jobs
WHERE reserved_at IS NULL
GROUP BY queue;

-- Check reserved jobs (being processed)
SELECT queue, COUNT(*) as processing
FROM queue_jobs
WHERE reserved_at IS NOT NULL
GROUP BY queue;

-- Check failed jobs
SELECT queue, COUNT(*) as failed
FROM queue_failed_jobs
GROUP BY queue;

-- View job details
SELECT * FROM queue_jobs
WHERE queue = 'default'
ORDER BY created_at DESC
LIMIT 10;
```

## Troubleshooting

### Worker Not Processing Jobs

**Check if worker is running:**
```bash
ps aux | grep "queue-work"
```

**Check worker logs for errors:**
```bash
# Docker
docker compose logs queue-worker-default

# Supervisor
sudo supervisorctl tail -f routemq-queue-default

# systemd
sudo journalctl -u routemq-queue-default -n 50
```

**Common issues:**
- Queue name mismatch between dispatch and worker
- Redis/MySQL connection issues
- Jobs failing during execution

### Jobs Timing Out

If jobs are timing out:

```bash
# Increase timeout
python main.py --queue-work --timeout 300

# Or set timeout in job class
class MyJob(Job):
    timeout = 300  # 5 minutes
```

### High Memory Usage

If worker memory grows:

```bash
# Restart worker after processing N jobs
python main.py --queue-work --max-jobs 1000

# Then use supervisor/systemd to auto-restart
```

### Worker Stuck

If worker seems stuck:

1. Send SIGTERM to gracefully stop
2. Check for infinite loops in job code
3. Add timeouts to external API calls
4. Review job logs for errors

## Best Practices

### 1. Run Multiple Workers

```bash
# Scale workers based on load
docker compose up -d --scale queue-worker-default=5
```

### 2. Use Different Queues

```bash
# High priority - fast polling
python main.py --queue-work --queue critical --sleep 1

# Normal priority
python main.py --queue-work --queue default --sleep 3

# Low priority - slow polling
python main.py --queue-work --queue cleanup --sleep 30
```

### 3. Set Resource Limits

```ini
# In supervisor config
[program:routemq-queue]
environment=PYTHONUNBUFFERED="1"
priority=999
startsecs=10
stopwaitsecs=60
killasgroup=true
```

### 4. Log Everything

```python
# In jobs
logger.info(f"Processing job {self.job_id}")
logger.info(f"Job completed in {elapsed}s")
```

### 5. Monitor Queue Depth

```python
# Alert if queue grows too large
size = await queue.size("default")
if size > 1000:
    await send_alert("Queue backlog detected")
```

## Next Steps

- [Understand queue drivers](./drivers.md)
- [Handle failed jobs](./failed-jobs.md)
- [Review best practices](./best-practices.md)
