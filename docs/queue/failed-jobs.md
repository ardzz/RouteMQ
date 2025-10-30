# Failed Jobs

When jobs fail permanently (exceed max_tries), they're moved to the failed jobs storage for inspection and potential retry. This guide explains how to handle failed jobs.

## What Makes a Job Fail?

A job fails permanently when:

1. **Exceeds max_tries** - Retried the maximum number of times
2. **Unrecoverable error** - Exception that can't be resolved by retrying
3. **Timeout** - Job exceeds its timeout limit repeatedly

## Where Failed Jobs Are Stored

### Database Storage (Recommended)

Failed jobs are stored in the `queue_failed_jobs` table:

```sql
CREATE TABLE queue_failed_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    connection VARCHAR(255) NOT NULL,
    queue VARCHAR(255) NOT NULL,
    payload TEXT NOT NULL,
    exception TEXT NOT NULL,
    failed_at DATETIME NOT NULL,
    INDEX(queue)
);
```

### Redis Storage (Fallback)

If MySQL is disabled, failed jobs are stored in Redis:

```
routemq:queue:failed:{queue_name}
```

## Viewing Failed Jobs

### Using MySQL

```sql
-- View all failed jobs
SELECT * FROM queue_failed_jobs
ORDER BY failed_at DESC;

-- Failed jobs by queue
SELECT queue, COUNT(*) as count
FROM queue_failed_jobs
GROUP BY queue;

-- Recent failures
SELECT * FROM queue_failed_jobs
WHERE failed_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
ORDER BY failed_at DESC;

-- View specific failure
SELECT id, queue, exception, failed_at
FROM queue_failed_jobs
WHERE id = 123;

-- View full payload
SELECT payload FROM queue_failed_jobs WHERE id = 123;
```

### Using Redis CLI

```bash
# Connect to Redis
redis-cli

# Check failed job count
LLEN routemq:queue:failed:default

# View failed jobs
LRANGE routemq:queue:failed:default 0 9

# View specific job
LINDEX routemq:queue:failed:default 0
```

## The failed() Method

Override the `failed()` method in your job to handle permanent failures:

```python
from core.job import Job
import logging

logger = logging.getLogger("MyJob")


class MyJob(Job):
    async def handle(self):
        # Job logic
        pass

    async def failed(self, exception: Exception):
        """
        Called when job fails permanently.

        Args:
            exception: The exception that caused the final failure
        """
        logger.error(f"Job failed permanently: {exception}")

        # Send alert to admin
        await send_admin_alert(
            f"Job {self.__class__.__name__} failed",
            str(exception)
        )

        # Log to monitoring service
        await log_to_sentry(exception)

        # Clean up resources
        await cleanup_resources(self.resource_id)

        # Update database status
        await mark_as_failed(self.task_id)
```

## Common Failed Job Scenarios

### Scenario 1: External API Failure

```python
class CallExternalAPIJob(Job):
    max_tries = 5
    retry_after = 60  # Wait 1 minute between retries

    async def handle(self):
        response = await call_external_api(self.endpoint, self.data)
        if not response.success:
            raise Exception("API call failed")

    async def failed(self, exception: Exception):
        # API still failing after 5 tries
        logger.error(f"API {self.endpoint} unreachable: {exception}")

        # Store for manual retry later
        await store_for_manual_processing(self.endpoint, self.data)

        # Notify operations team
        await send_slack_message("#ops", f"API {self.endpoint} is down")
```

### Scenario 2: Invalid Data

```python
class ProcessDataJob(Job):
    max_tries = 1  # Don't retry invalid data

    async def handle(self):
        if not self.validate_data():
            raise ValueError("Invalid data format")

        await process_data(self.data)

    async def failed(self, exception: Exception):
        # Log invalid data for investigation
        logger.error(f"Invalid data: {self.data}")

        # Store in error log
        await save_error_log({
            "data": self.data,
            "error": str(exception),
            "timestamp": datetime.now()
        })
```

### Scenario 3: Resource Unavailable

```python
class GenerateReportJob(Job):
    max_tries = 3
    retry_after = 300  # Wait 5 minutes

    async def handle(self):
        # Check if data is ready
        if not await data_ready(self.report_id):
            raise Exception("Data not ready")

        await generate_report(self.report_id)

    async def failed(self, exception: Exception):
        # Data still not ready after 3 tries
        logger.warning(f"Report {self.report_id} data not ready")

        # Notify user
        await send_email(
            self.user_email,
            "Report Delayed",
            f"Your report is delayed due to data availability"
        )
```

## Inspecting Failed Jobs

### Get Job Details

```python
from core.model import Model
from app.models.queue_failed_job import QueueFailedJob
from sqlalchemy import select

async def inspect_failed_job(job_id: int):
    session = await Model.get_session()

    result = await session.execute(
        select(QueueFailedJob).where(QueueFailedJob.id == job_id)
    )
    failed_job = result.scalars().first()

    if failed_job:
        print(f"Queue: {failed_job.queue}")
        print(f"Failed at: {failed_job.failed_at}")
        print(f"Exception: {failed_job.exception}")
        print(f"Payload: {failed_job.payload}")

    await session.close()
```

### Analyze Failure Patterns

```sql
-- Most common failure reasons
SELECT
    SUBSTRING_INDEX(exception, ':', 1) as error_type,
    COUNT(*) as count
FROM queue_failed_jobs
GROUP BY error_type
ORDER BY count DESC;

-- Failures by hour
SELECT
    DATE_FORMAT(failed_at, '%Y-%m-%d %H:00') as hour,
    COUNT(*) as failures
FROM queue_failed_jobs
WHERE failed_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY hour
ORDER BY hour;

-- Failure rate by queue
SELECT
    queue,
    COUNT(*) as total_failures,
    COUNT(DISTINCT DATE(failed_at)) as days_with_failures
FROM queue_failed_jobs
GROUP BY queue;
```

## Retrying Failed Jobs

### Manual Retry

```python
from core.job import Job
from core.queue.queue_manager import dispatch

async def retry_failed_job(failed_job_id: int):
    """Retry a specific failed job."""
    # Fetch failed job from database
    session = await Model.get_session()
    result = await session.execute(
        select(QueueFailedJob).where(QueueFailedJob.id == failed_job_id)
    )
    failed_job = result.scalars().first()

    if not failed_job:
        print(f"Failed job {failed_job_id} not found")
        return

    # Deserialize and dispatch again
    job = Job.unserialize(failed_job.payload)
    await dispatch(job)

    # Delete from failed jobs
    await session.delete(failed_job)
    await session.commit()
    await session.close()

    print(f"Retried failed job {failed_job_id}")
```

### Bulk Retry

```python
async def retry_all_failed_jobs(queue: str = "default"):
    """Retry all failed jobs in a queue."""
    session = await Model.get_session()

    result = await session.execute(
        select(QueueFailedJob).where(QueueFailedJob.queue == queue)
    )
    failed_jobs = result.scalars().all()

    retried = 0
    for failed_job in failed_jobs:
        try:
            job = Job.unserialize(failed_job.payload)
            await dispatch(job)
            await session.delete(failed_job)
            retried += 1
        except Exception as e:
            print(f"Failed to retry job {failed_job.id}: {e}")

    await session.commit()
    await session.close()

    print(f"Retried {retried} failed jobs from queue '{queue}'")
```

## Cleaning Up Failed Jobs

### Delete Old Failed Jobs

```sql
-- Delete failed jobs older than 30 days
DELETE FROM queue_failed_jobs
WHERE failed_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- Delete all failed jobs from a specific queue
DELETE FROM queue_failed_jobs
WHERE queue = 'old-queue';

-- Keep only last 1000 failed jobs
DELETE FROM queue_failed_jobs
WHERE id NOT IN (
    SELECT id FROM (
        SELECT id FROM queue_failed_jobs
        ORDER BY failed_at DESC
        LIMIT 1000
    ) as recent
);
```

### Automated Cleanup Script

```python
# cleanup_failed_jobs.py
import asyncio
from datetime import datetime, timedelta
from core.model import Model
from app.models.queue_failed_job import QueueFailedJob

async def cleanup_old_failed_jobs(days: int = 30):
    """Delete failed jobs older than specified days."""
    session = await Model.get_session()

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await session.execute(
        delete(QueueFailedJob).where(QueueFailedJob.failed_at < cutoff_date)
    )

    deleted_count = result.rowcount
    await session.commit()
    await session.close()

    print(f"Deleted {deleted_count} failed jobs older than {days} days")

if __name__ == "__main__":
    asyncio.run(cleanup_old_failed_jobs(30))
```

Schedule with cron:

```cron
# Run cleanup daily at 2 AM
0 2 * * * cd /path/to/RouteMQ && /path/to/venv/bin/python cleanup_failed_jobs.py
```

## Monitoring Failed Jobs

### Alert on Failure Threshold

```python
async def check_failure_rate():
    """Alert if failure rate exceeds threshold."""
    session = await Model.get_session()

    # Count failures in last hour
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)

    result = await session.execute(
        select(func.count(QueueFailedJob.id))
        .where(QueueFailedJob.failed_at >= one_hour_ago)
    )
    failure_count = result.scalar()

    if failure_count > 100:  # Threshold
        await send_alert(
            "High Failure Rate",
            f"{failure_count} jobs failed in the last hour"
        )

    await session.close()
```

### Dashboard Query

```sql
-- Failed jobs summary for dashboard
SELECT
    queue,
    COUNT(*) as total_failures,
    MAX(failed_at) as last_failure,
    MIN(failed_at) as first_failure
FROM queue_failed_jobs
WHERE failed_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY queue
ORDER BY total_failures DESC;
```

## Best Practices

### 1. Always Implement failed()

```python
class MyJob(Job):
    async def failed(self, exception: Exception):
        # Log the failure
        logger.error(f"Job failed: {exception}")

        # Clean up resources
        # Notify stakeholders
        # Update status
```

### 2. Set Appropriate max_tries

```python
# Quick tasks - fail fast
class QuickJob(Job):
    max_tries = 2

# External API calls - retry more
class APIJob(Job):
    max_tries = 5
    retry_after = 60

# Critical jobs - many retries
class CriticalJob(Job):
    max_tries = 10
    retry_after = 300
```

### 3. Regular Cleanup

```python
# Clean up old failed jobs weekly
async def weekly_cleanup():
    await cleanup_old_failed_jobs(days=30)
```

### 4. Monitor Failure Patterns

```python
# Track failure types
failures_by_type = {}
for exception_type in failure_exceptions:
    failures_by_type[exception_type] = count

# Alert on unusual patterns
```

## Next Steps

- [Review best practices](./best-practices.md)
- [Learn about queue drivers](./drivers.md)
- [Docker deployment](../docker-deployment.md)
