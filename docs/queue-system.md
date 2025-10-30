# Queue System

RouteMQ includes a powerful background task queue system similar to Laravel's queue functionality. This allows you to defer time-consuming tasks (like sending emails, processing data, generating reports) to background workers, keeping your MQTT message handlers fast and responsive.

## Table of Contents

- [Overview](#overview)
- [Configuration](#configuration)
- [Creating Jobs](#creating-jobs)
- [Dispatching Jobs](#dispatching-jobs)
- [Running Queue Workers](#running-queue-workers)
- [Queue Drivers](#queue-drivers)
- [Failed Jobs](#failed-jobs)
- [Best Practices](#best-practices)

## Overview

The queue system consists of several components:

- **Job**: A class that defines a task to be executed in the background
- **Queue Manager**: Dispatches jobs to queues
- **Queue Driver**: Handles storage and retrieval of jobs (Redis or Database)
- **Queue Worker**: Processes jobs from the queue

### Architecture

```
┌─────────────┐
│  Your Code  │
└──────┬──────┘
       │ dispatch(job)
       ▼
┌─────────────┐
│Queue Manager│
└──────┬──────┘
       │ push
       ▼
┌─────────────────┐
│  Queue Driver   │
│ (Redis/Database)│
└──────┬──────────┘
       │ pop
       ▼
┌─────────────┐
│Queue Worker │
│ job.handle()│
└─────────────┘
```

## Configuration

### Environment Variables

Add these variables to your `.env` file:

```env
# Queue Configuration
QUEUE_CONNECTION=redis  # 'redis' or 'database'

# Redis (required if using Redis queue)
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# MySQL (required if using Database queue)
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password
```

### Queue Drivers

**Redis Driver** (Recommended for production)
- ✅ Fast, in-memory storage
- ✅ Low latency
- ✅ Supports delayed jobs
- ⚠️ Requires Redis server
- ⚠️ Jobs are lost if Redis crashes (unless persistence is configured)

**Database Driver**
- ✅ Persistent storage
- ✅ ACID guarantees
- ✅ No additional services required
- ⚠️ Slower than Redis
- ⚠️ Higher database load

## Creating Jobs

Jobs are classes that extend the `Job` base class. Each job must implement the `handle()` method.

### Basic Job Example

```python
# app/jobs/send_notification_job.py
import logging
from core.job import Job

logger = logging.getLogger("RouteMQ.Jobs.SendNotificationJob")


class SendNotificationJob(Job):
    """Send a notification to a user."""

    # Job configuration
    max_tries = 3          # Maximum retry attempts
    timeout = 60           # Maximum seconds to run
    retry_after = 10       # Seconds to wait before retry
    queue = "default"      # Queue name

    def __init__(self):
        super().__init__()
        self.user_id = None
        self.message = None

    async def handle(self) -> None:
        """Execute the job."""
        logger.info(f"Sending notification to user {self.user_id}")
        logger.info(f"Message: {self.message}")

        # Your notification logic here
        # e.g., send push notification, SMS, email, etc.

        logger.info("Notification sent successfully")

    async def failed(self, exception: Exception) -> None:
        """Called when the job fails permanently."""
        logger.error(
            f"Failed to send notification to user {self.user_id}: {str(exception)}"
        )
        # Handle failure (e.g., log to monitoring service, alert admin)
```

### Job Properties

| Property | Description | Default |
|----------|-------------|---------|
| `max_tries` | Maximum number of retry attempts | 3 |
| `timeout` | Maximum seconds the job can run | 60 |
| `retry_after` | Seconds to wait before retrying after failure | 0 |
| `queue` | Queue name | "default" |

### Custom Data in Jobs

All public instance attributes are automatically serialized and restored when the job is processed:

```python
class ProcessOrderJob(Job):
    def __init__(self):
        super().__init__()
        self.order_id = None
        self.customer_email = None
        self.items = []  # Lists and dicts are supported

    async def handle(self):
        # All attributes are available
        print(f"Processing order {self.order_id}")
        print(f"Customer: {self.customer_email}")
        print(f"Items: {self.items}")
```

## Dispatching Jobs

### Using the `dispatch()` Helper

The simplest way to dispatch a job:

```python
from core.queue.queue_manager import dispatch
from app.jobs.send_notification_job import SendNotificationJob

# In your MQTT handler or anywhere in your code
async def handle_message(context):
    # Create and configure the job
    job = SendNotificationJob()
    job.user_id = 123
    job.message = "Your order has been shipped!"

    # Dispatch to queue
    await dispatch(job)
```

### Using the Queue Manager

For more control, use the `QueueManager` directly:

```python
from core.queue.queue_manager import queue
from app.jobs.send_email_job import SendEmailJob

# Dispatch to default queue
job = SendEmailJob()
job.to = "user@example.com"
job.subject = "Welcome!"
await queue.push(job)

# Dispatch to specific queue
await queue.push(job, queue="emails")

# Dispatch to specific connection
await queue.push(job, connection="database")
```

### Delayed Jobs

Schedule a job to run after a delay:

```python
from core.queue.queue_manager import queue
from app.jobs.generate_report_job import GenerateReportJob

job = GenerateReportJob()
job.report_type = "monthly"
job.user_id = 456

# Run after 1 hour (3600 seconds)
await queue.later(3600, job)

# Run after 5 minutes
await queue.later(300, job)
```

### Bulk Dispatching

Dispatch multiple jobs at once:

```python
from core.queue.queue_manager import queue

jobs = []
for user_id in user_ids:
    job = SendNotificationJob()
    job.user_id = user_id
    job.message = "System maintenance tonight"
    jobs.append(job)

# Dispatch all jobs
await queue.bulk(jobs)
```

### Example: Dispatching from MQTT Handler

```python
# app/controllers/order_controller.py
from core.controller import Controller
from core.queue.queue_manager import dispatch
from app.jobs.process_order_job import ProcessOrderJob


class OrderController(Controller):
    @staticmethod
    async def handle_new_order(order_id: str, payload, client):
        print(f"Received new order {order_id}")

        # Dispatch background job for processing
        job = ProcessOrderJob()
        job.order_id = order_id
        job.order_data = payload
        await dispatch(job)

        # Respond immediately without waiting for processing
        return {"status": "accepted", "order_id": order_id}
```

## Running Queue Workers

### Start a Queue Worker

Start a worker to process jobs from the queue:

```bash
# Process jobs from 'default' queue
python main.py --queue-work

# Or using the global command
routemq --queue-work
```

### Worker Options

```bash
# Process specific queue
python main.py --queue-work --queue emails

# Specify connection (redis or database)
python main.py --queue-work --connection database

# Process max 100 jobs then stop
python main.py --queue-work --max-jobs 100

# Run for max 1 hour (3600 seconds) then stop
python main.py --queue-work --max-time 3600

# Sleep for 5 seconds when no jobs available
python main.py --queue-work --sleep 5

# Override max tries for all jobs
python main.py --queue-work --max-tries 5

# Set job timeout (seconds)
python main.py --queue-work --timeout 120
```

### Multiple Workers

Run multiple workers for different queues:

```bash
# Terminal 1: High-priority queue
python main.py --queue-work --queue high-priority --sleep 1

# Terminal 2: Default queue
python main.py --queue-work --queue default

# Terminal 3: Low-priority/background tasks
python main.py --queue-work --queue low-priority --sleep 10
```

### Production Deployment

For production, use a process manager like **Supervisor** or **systemd**:

#### Supervisor Example

```ini
; /etc/supervisor/conf.d/routemq-queue.conf
[program:routemq-queue-default]
command=/path/to/venv/bin/python main.py --queue-work --queue default
directory=/path/to/RouteMQ
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/routemq/queue-default.log

[program:routemq-queue-emails]
command=/path/to/venv/bin/python main.py --queue-work --queue emails
directory=/path/to/RouteMQ
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/routemq/queue-emails.log
```

Then:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start routemq-queue-default
sudo supervisorctl start routemq-queue-emails
```

## Queue Drivers

### Redis Queue Driver

Fast, in-memory queue backed by Redis.

**Requirements:**
- Redis server running
- `ENABLE_REDIS=true` in `.env`
- `QUEUE_CONNECTION=redis` in `.env`

**Features:**
- Uses Redis lists for immediate jobs (FIFO)
- Uses Redis sorted sets for delayed jobs
- Atomic operations with `RPOPLPUSH` for job claiming
- Reserved list prevents job loss during processing

**Data Structure:**
```
routemq:queue:{queue_name}           # Pending jobs (list)
routemq:queue:{queue_name}:delayed   # Delayed jobs (sorted set)
routemq:queue:{queue_name}:reserved  # Reserved jobs being processed (list)
routemq:queue:failed:{queue_name}    # Failed jobs (list)
```

### Database Queue Driver

Persistent queue backed by MySQL.

**Requirements:**
- MySQL server running
- `ENABLE_MYSQL=true` in `.env`
- `QUEUE_CONNECTION=database` in `.env`

**Features:**
- Uses `queue_jobs` table for pending jobs
- Uses `queue_failed_jobs` table for failed jobs
- ACID transactions
- `SELECT ... FOR UPDATE SKIP LOCKED` for concurrency-safe job claiming

**Database Tables:**

**queue_jobs:**
| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| queue | VARCHAR(255) | Queue name |
| payload | TEXT | Serialized job data |
| attempts | INT | Number of attempts |
| reserved_at | DATETIME | When job was claimed |
| available_at | DATETIME | When job becomes available |
| created_at | DATETIME | When job was created |

**queue_failed_jobs:**
| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| connection | VARCHAR(255) | Connection name |
| queue | VARCHAR(255) | Queue name |
| payload | TEXT | Serialized job data |
| exception | TEXT | Exception message and trace |
| failed_at | DATETIME | When job failed |

## Failed Jobs

### Viewing Failed Jobs

Failed jobs are stored in:
- **Redis**: `routemq:queue:failed:{queue_name}` (if MySQL disabled)
- **Database**: `queue_failed_jobs` table (if MySQL enabled)

### Query Failed Jobs (Database)

```python
from core.model import Model
from app.models.queue_failed_job import QueueFailedJob
from sqlalchemy import select

session = await Model.get_session()
result = await session.execute(
    select(QueueFailedJob)
    .where(QueueFailedJob.queue == "emails")
    .order_by(QueueFailedJob.failed_at.desc())
)
failed_jobs = result.scalars().all()

for job in failed_jobs:
    print(f"Failed at: {job.failed_at}")
    print(f"Exception: {job.exception}")
    print(f"Payload: {job.payload}")
```

### Handling Failed Jobs

When a job exceeds `max_tries`, its `failed()` method is called:

```python
class MyJob(Job):
    async def failed(self, exception: Exception) -> None:
        """Called when job fails permanently."""
        # Log to monitoring service
        logger.error(f"Job failed: {exception}")

        # Send alert to admin
        await send_admin_alert(f"Job failed: {self.__class__.__name__}")

        # Store for manual review
        # ... custom logic ...
```

## Best Practices

### 1. Keep Jobs Small and Focused

Each job should do one thing well:

```python
# ✅ Good - focused job
class SendWelcomeEmailJob(Job):
    async def handle(self):
        await send_email(self.user_id, "welcome")

# ❌ Bad - doing too much
class UserSignupJob(Job):
    async def handle(self):
        await send_email()
        await create_profile()
        await setup_billing()
        await send_sms()
```

### 2. Make Jobs Idempotent

Jobs should be safe to run multiple times:

```python
class UpdateUserScoreJob(Job):
    async def handle(self):
        # ✅ Good - idempotent (SET operation)
        await db.execute(
            "UPDATE users SET score = ? WHERE id = ?",
            (self.new_score, self.user_id)
        )

        # ❌ Bad - not idempotent (INCREMENT operation)
        await db.execute(
            "UPDATE users SET score = score + ? WHERE id = ?",
            (10, self.user_id)
        )
```

### 3. Set Appropriate Timeouts

```python
class QuickJob(Job):
    timeout = 30  # Quick tasks

class DataProcessingJob(Job):
    timeout = 300  # Data processing

class ReportGenerationJob(Job):
    timeout = 600  # Long-running reports
```

### 4. Use Different Queues for Different Priorities

```python
class CriticalAlertJob(Job):
    queue = "critical"
    max_tries = 5

class EmailJob(Job):
    queue = "emails"
    max_tries = 3

class CleanupJob(Job):
    queue = "low-priority"
    max_tries = 1
```

Then run workers with appropriate settings:

```bash
# Critical queue - check constantly
python main.py --queue-work --queue critical --sleep 1

# Emails - normal priority
python main.py --queue-work --queue emails --sleep 3

# Low priority - check less frequently
python main.py --queue-work --queue low-priority --sleep 10
```

### 5. Monitor Queue Size

```python
from core.queue.queue_manager import queue

# Check queue size
size = await queue.size("default")
if size > 1000:
    logger.warning(f"Queue backlog: {size} jobs pending")
```

### 6. Handle Sensitive Data Carefully

Don't store passwords or tokens in job payloads:

```python
# ❌ Bad
class BadJob(Job):
    def __init__(self):
        super().__init__()
        self.password = None  # Stored in queue!

# ✅ Good
class GoodJob(Job):
    def __init__(self):
        super().__init__()
        self.user_id = None  # Lookup credentials in handle()

    async def handle(self):
        credentials = await get_user_credentials(self.user_id)
        # Use credentials...
```

### 7. Log Appropriately

```python
class MyJob(Job):
    async def handle(self):
        logger.info(f"Processing job {self.job_id} (attempt {self.attempts})")

        try:
            # ... work ...
            logger.info("Job completed successfully")
        except Exception as e:
            logger.error(f"Job failed: {e}", exc_info=True)
            raise
```

## Example Use Cases

### 1. Email Notifications

```python
# Dispatch from MQTT handler
from core.queue.queue_manager import dispatch
from app.jobs.send_email_job import SendEmailJob

async def handle_user_signup(context):
    user_id = context["params"]["user_id"]

    # Queue welcome email
    job = SendEmailJob()
    job.to = context["payload"]["email"]
    job.subject = "Welcome!"
    job.template = "welcome"
    await dispatch(job)
```

### 2. Data Processing Pipeline

```python
# Chain multiple jobs
async def process_sensor_data(device_id, data):
    # 1. Store raw data
    job1 = StoreRawDataJob()
    job1.device_id = device_id
    job1.data = data
    await dispatch(job1)

    # 2. Process and analyze
    job2 = AnalyzeDataJob()
    job2.device_id = device_id
    await dispatch(job2)

    # 3. Generate alerts if needed
    job3 = GenerateAlertsJob()
    job3.device_id = device_id
    await queue.later(60, job3)  # After 1 minute
```

### 3. Scheduled Reports

```python
# Daily report generation
from core.queue.queue_manager import queue
from app.jobs.generate_report_job import GenerateReportJob

async def schedule_daily_reports():
    for user_id in active_users:
        job = GenerateReportJob()
        job.user_id = user_id
        job.report_type = "daily"

        # Schedule for midnight
        seconds_until_midnight = calculate_seconds_until_midnight()
        await queue.later(seconds_until_midnight, job)
```

## Troubleshooting

### Jobs Not Processing

1. Check if queue worker is running
2. Verify queue name matches between dispatch and worker
3. Check connection settings (Redis/Database)
4. Look for errors in worker logs

### Jobs Failing Repeatedly

1. Check exception in failed jobs table
2. Verify job timeout is adequate
3. Test job logic independently
4. Check external service availability

### Queue Growing Too Large

1. Add more workers
2. Optimize job execution time
3. Use multiple queues for different priorities
4. Check for failing jobs blocking the queue

## Summary

The RouteMQ queue system provides a robust solution for background task processing:

- ✅ Similar to Laravel's queue system
- ✅ Two drivers: Redis (fast) and Database (persistent)
- ✅ Job retries and failure handling
- ✅ Delayed job execution
- ✅ Multiple queues and priorities
- ✅ Easy to use and integrate

Start using queues to make your RouteMQ application more scalable and responsive!
