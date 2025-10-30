# Best Practices

Follow these best practices to build reliable and efficient queue-based systems with RouteMQ.

## Job Design

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

**Why?**
- Easier to test and debug
- Better error handling
- Can retry individual steps
- More flexible composition

### 2. Make Jobs Idempotent

Jobs should be safe to run multiple times:

```python
# ✅ Good - idempotent (SET operation)
class UpdateUserScoreJob(Job):
    async def handle(self):
        await db.execute(
            "UPDATE users SET score = ? WHERE id = ?",
            (self.new_score, self.user_id)
        )

# ❌ Bad - not idempotent (INCREMENT operation)
class IncrementScoreJob(Job):
    async def handle(self):
        await db.execute(
            "UPDATE users SET score = score + 10 WHERE id = ?",
            (self.user_id,)
        )
```

**Why?**
- Jobs may be retried on failure
- Network issues can cause duplicates
- Worker crashes might re-process jobs

### 3. Set Appropriate Timeouts

```python
class QuickJob(Job):
    timeout = 30  # Quick tasks (30 seconds)

class DataProcessingJob(Job):
    timeout = 300  # Data processing (5 minutes)

class ReportGenerationJob(Job):
    timeout = 600  # Long-running reports (10 minutes)
```

**Guidelines:**
- API calls: 30-60 seconds
- Data processing: 2-5 minutes
- Report generation: 5-10 minutes
- Don't exceed 10 minutes (consider breaking into smaller jobs)

### 4. Use Descriptive Names

```python
# ✅ Good - clear purpose
class SendPasswordResetEmailJob(Job):
    pass

class ProcessIoTSensorDataJob(Job):
    pass

class GenerateMonthlySalesReportJob(Job):
    pass

# ❌ Bad - unclear
class Job1(Job):
    pass

class ProcessJob(Job):
    pass

class DoStuff(Job):
    pass
```

## Queue Organization

### 5. Use Different Queues for Different Priorities

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
# Critical queue - check every second
python main.py --queue-work --queue critical --sleep 1

# Emails - normal priority
python main.py --queue-work --queue emails --sleep 3

# Low priority - check every 10 seconds
python main.py --queue-work --queue low-priority --sleep 10
```

### 6. Organize by Function

```python
# By type
queue = "emails"
queue = "reports"
queue = "notifications"

# By priority
queue = "high-priority"
queue = "default"
queue = "low-priority"

# By service
queue = "payment-processing"
queue = "data-sync"
queue = "cleanup"
```

## Data Handling

### 7. Don't Store Large Payloads

```python
# ✅ Good - store ID only
class ProcessOrderJob(Job):
    def __init__(self):
        super().__init__()
        self.order_id = None  # Small

    async def handle(self):
        # Fetch data when needed
        order = await fetch_order(self.order_id)
        await process_order(order)

# ❌ Bad - storing large data
class ProcessOrderJob(Job):
    def __init__(self):
        super().__init__()
        self.order_data = None  # Could be huge!

    async def handle(self):
        await process_order(self.order_data)
```

**Why?**
- Keeps queue storage small
- Reduces serialization overhead
- Always gets fresh data
- Avoids stale data issues

### 8. Handle Sensitive Data Carefully

Don't store passwords or tokens in job payloads:

```python
# ❌ Bad - storing credentials
class BadJob(Job):
    def __init__(self):
        super().__init__()
        self.password = None  # Stored in queue!
        self.api_token = None  # Visible in logs!

# ✅ Good - fetch credentials when needed
class GoodJob(Job):
    def __init__(self):
        super().__init__()
        self.user_id = None

    async def handle(self):
        credentials = await get_user_credentials(self.user_id)
        api_token = await get_api_token()
        # Use credentials...
```

### 9. Validate Data Before Dispatching

```python
def dispatch_email_job(to: str, subject: str, body: str):
    # Validate before dispatching
    if not to or '@' not in to:
        raise ValueError("Invalid email address")

    if not subject:
        raise ValueError("Subject is required")

    if len(body) > 10000:
        raise ValueError("Body too long")

    job = SendEmailJob()
    job.to = to
    job.subject = subject
    job.body = body

    return job
```

## Error Handling

### 10. Always Implement failed()

```python
class MyJob(Job):
    async def failed(self, exception: Exception):
        # Log the failure
        logger.error(f"Job failed permanently: {exception}")

        # Clean up resources
        await cleanup_resources(self.resource_id)

        # Notify stakeholders
        await send_admin_alert(f"Job {self.__class__.__name__} failed")

        # Update status
        await update_status(self.task_id, "failed")
```

### 11. Use Appropriate Retry Strategies

```python
# Quick tasks - fail fast
class QuickAPICallJob(Job):
    max_tries = 2
    retry_after = 5

# External services - be patient
class ExternalAPIJob(Job):
    max_tries = 5
    retry_after = 60

# Critical operations - many retries
class CriticalJob(Job):
    max_tries = 10
    retry_after = 300
```

### 12. Log Appropriately

```python
class MyJob(Job):
    async def handle(self):
        logger.info(f"Processing job {self.job_id} (attempt {self.attempts})")
        logger.debug(f"Job data: {self.data}")

        try:
            result = await do_work()
            logger.info(f"Job completed: {result}")
        except Exception as e:
            logger.error(f"Job failed: {e}", exc_info=True)
            raise
```

## Monitoring

### 13. Monitor Queue Size

```python
from core.queue.queue_manager import queue

# Check queue size periodically
size = await queue.size("default")
if size > 1000:
    logger.warning(f"Queue backlog: {size} jobs pending")
    await send_alert("High queue backlog detected")
```

### 14. Track Processing Time

```python
import time

class MyJob(Job):
    async def handle(self):
        start_time = time.time()

        await do_work()

        elapsed = time.time() - start_time
        logger.info(f"Job completed in {elapsed:.2f}s")

        # Alert on slow jobs
        if elapsed > 60:
            logger.warning(f"Slow job detected: {elapsed:.2f}s")
```

### 15. Monitor Failure Rates

```python
async def check_failure_rate():
    """Alert if too many jobs are failing."""
    session = await Model.get_session()

    # Count failures in last hour
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    result = await session.execute(
        select(func.count(QueueFailedJob.id))
        .where(QueueFailedJob.failed_at >= one_hour_ago)
    )
    failures = result.scalar()

    if failures > 100:  # Threshold
        await send_alert(f"High failure rate: {failures} jobs failed in last hour")

    await session.close()
```

## Performance

### 16. Use Bulk Operations

```python
# ✅ Good - bulk dispatch
jobs = []
for user_id in user_ids:
    job = SendNotificationJob()
    job.user_id = user_id
    jobs.append(job)

await queue.bulk(jobs)  # Single operation

# ❌ Bad - individual dispatches
for user_id in user_ids:
    job = SendNotificationJob()
    job.user_id = user_id
    await dispatch(job)  # Multiple operations
```

### 17. Choose the Right Driver

```python
# High volume, speed critical → Redis
QUEUE_CONNECTION=redis

# Persistence critical, low volume → Database
QUEUE_CONNECTION=database
```

### 18. Scale Workers Appropriately

```bash
# High load - scale up
docker compose up -d --scale queue-worker-default=10

# Low load - scale down
docker compose up -d --scale queue-worker-default=2
```

## Deployment

### 19. Use Process Managers

```ini
# supervisor.conf
[program:routemq-queue]
command=/path/to/venv/bin/python main.py --queue-work
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=60
```

### 20. Regular Maintenance

```python
# Clean up old failed jobs weekly
async def weekly_cleanup():
    await cleanup_old_failed_jobs(days=30)

# Monitor queue health daily
async def daily_health_check():
    for queue_name in ["default", "emails", "reports"]:
        size = await queue.size(queue_name)
        logger.info(f"Queue {queue_name}: {size} jobs")
```

## Testing

### 21. Test Jobs in Isolation

```python
import pytest

@pytest.mark.asyncio
async def test_send_email_job():
    job = SendEmailJob()
    job.to = "test@example.com"
    job.subject = "Test"
    job.body = "Test body"

    # Mock external services
    with patch('app.jobs.send_email_job.send_email') as mock_send:
        await job.handle()
        mock_send.assert_called_once()
```

### 22. Test with Limited Retries

```bash
# Test job with single retry
python main.py --queue-work --max-jobs 1 --max-tries 1
```

## Common Anti-Patterns

### ❌ Don't Block Workers

```python
# ❌ Bad - blocking
class BadJob(Job):
    async def handle(self):
        time.sleep(10)  # Blocks worker!

# ✅ Good - non-blocking
class GoodJob(Job):
    async def handle(self):
        await asyncio.sleep(10)  # Non-blocking
```

### ❌ Don't Chain Jobs Inside handle()

```python
# ❌ Bad - chaining inside job
class BadJob(Job):
    async def handle(self):
        await do_work()
        # Dispatching from inside job
        next_job = AnotherJob()
        await dispatch(next_job)

# ✅ Good - dispatch from controller
async def handle_message(context):
    job1 = FirstJob()
    await dispatch(job1)

    job2 = SecondJob()
    await dispatch(job2)
```

### ❌ Don't Store Job State in Class Variables

```python
# ❌ Bad - class variable (shared across instances!)
class BadJob(Job):
    counter = 0  # Shared!

    async def handle(self):
        self.counter += 1

# ✅ Good - instance variable
class GoodJob(Job):
    def __init__(self):
        super().__init__()
        self.counter = 0  # Per-instance

    async def handle(self):
        self.counter += 1
```

## Checklist

Before deploying to production:

- [ ] All jobs have descriptive names
- [ ] Jobs are idempotent
- [ ] Appropriate timeouts set
- [ ] `failed()` method implemented
- [ ] Sensitive data not in payloads
- [ ] Data validated before dispatch
- [ ] Proper logging in place
- [ ] Queue sizes monitored
- [ ] Workers managed by process manager
- [ ] Regular cleanup scheduled
- [ ] Tests written for jobs
- [ ] Documentation updated

## Summary

**Do:**
- Keep jobs small and focused
- Make jobs idempotent
- Set appropriate timeouts
- Use different queues for priorities
- Store IDs, not large data
- Handle sensitive data carefully
- Implement `failed()` method
- Monitor queue health
- Use bulk operations
- Test thoroughly

**Don't:**
- Store large payloads
- Store sensitive data
- Chain jobs inside jobs
- Block workers
- Use class variables for state
- Skip error handling
- Forget to log
- Ignore failed jobs
- Over-complicate jobs

## Next Steps

- [Run workers in production](./running-workers.md)
- [Docker deployment guide](../docker-deployment.md)
- [Monitor and troubleshoot](./failed-jobs.md)
