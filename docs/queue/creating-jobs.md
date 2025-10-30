# Creating Jobs

Jobs are classes that extend the `Job` base class. Each job must implement the `handle()` method which contains the logic to be executed in the background.

## Basic Job Structure

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

## Job Properties

Configure your job's behavior with these class attributes:

| Property | Description | Default | Example |
|----------|-------------|---------|---------|
| `max_tries` | Maximum number of retry attempts | 3 | `max_tries = 5` |
| `timeout` | Maximum seconds the job can run | 60 | `timeout = 120` |
| `retry_after` | Seconds to wait before retrying after failure | 0 | `retry_after = 30` |
| `queue` | Queue name | "default" | `queue = "emails"` |

## Custom Data in Jobs

All public instance attributes are automatically serialized and restored when the job is processed:

```python
class ProcessOrderJob(Job):
    def __init__(self):
        super().__init__()
        self.order_id = None
        self.customer_email = None
        self.items = []  # Lists and dicts are supported
        self.metadata = {}  # Nested structures work too

    async def handle(self):
        # All attributes are available
        print(f"Processing order {self.order_id}")
        print(f"Customer: {self.customer_email}")
        print(f"Items: {self.items}")
        print(f"Metadata: {self.metadata}")
```

### Supported Data Types

- ✅ Strings, integers, floats, booleans
- ✅ Lists and tuples
- ✅ Dictionaries
- ✅ None values
- ❌ Objects (they won't serialize - store IDs instead)
- ❌ File handles
- ❌ Database connections

## The handle() Method

The `handle()` method is where your job's logic lives:

```python
async def handle(self) -> None:
    """
    Execute the job.
    This method is called by the queue worker.
    """
    # Your job logic here
    pass
```

**Key points:**
- Must be `async` (asynchronous)
- Should return `None`
- Can raise exceptions (will trigger retry)
- Has access to `self.attempts` (current attempt number)
- Has access to `self.job_id` (unique job identifier)

## The failed() Method

The `failed()` method is called when a job fails permanently (exceeds `max_tries`):

```python
async def failed(self, exception: Exception) -> None:
    """
    Handle permanent job failure.
    Called after max_tries is exceeded.

    Args:
        exception: The exception that caused the final failure
    """
    logger.error(f"Job failed permanently: {exception}")

    # Send alert
    await send_admin_alert(f"Job failed: {self.__class__.__name__}")

    # Log to monitoring service
    await log_to_sentry(exception)

    # Store for manual review
    # ... custom logic ...
```

## Job Examples

### Example 1: Email Job

```python
import asyncio
from core.job import Job

class SendEmailJob(Job):
    max_tries = 3
    timeout = 30
    retry_after = 10
    queue = "emails"

    def __init__(self):
        super().__init__()
        self.to = None
        self.subject = None
        self.body = None

    async def handle(self):
        # Simulate email sending
        await asyncio.sleep(2)

        # In production, use real email service
        # await send_email(self.to, self.subject, self.body)

        print(f"Email sent to {self.to}")

    async def failed(self, exception: Exception):
        print(f"Failed to send email to {self.to}: {exception}")
```

### Example 2: Data Processing Job

```python
from core.job import Job

class ProcessDataJob(Job):
    max_tries = 5
    timeout = 120  # Longer timeout for data processing
    retry_after = 5
    queue = "data-processing"

    def __init__(self):
        super().__init__()
        self.device_id = None
        self.sensor_data = None

    async def handle(self):
        # Process sensor data
        temperature = self.sensor_data.get("temperature")
        humidity = self.sensor_data.get("humidity")

        # Calculate statistics
        if temperature and temperature > 30:
            await send_alert(f"High temperature: {temperature}°C")

        # Store in database
        # await store_sensor_data(self.device_id, self.sensor_data)

        print(f"Processed data from device {self.device_id}")

    async def failed(self, exception: Exception):
        print(f"Failed to process data from {self.device_id}")
```

### Example 3: Report Generation Job

```python
from datetime import datetime
from core.job import Job

class GenerateReportJob(Job):
    max_tries = 2
    timeout = 300  # 5 minutes for report generation
    retry_after = 60
    queue = "reports"

    def __init__(self):
        super().__init__()
        self.report_type = None
        self.user_id = None

    async def handle(self):
        # Generate report
        report_file = f"{self.report_type}_{datetime.now().strftime('%Y%m%d')}.pdf"

        # In production:
        # - Query database
        # - Generate PDF
        # - Upload to storage
        # - Send notification

        print(f"Report generated: {report_file}")

    async def failed(self, exception: Exception):
        # Notify user that report generation failed
        print(f"Failed to generate report for user {self.user_id}")
```

## Job Lifecycle

Understanding how jobs are processed:

```
1. Job Created
   ↓
2. Job Serialized
   ↓
3. Job Pushed to Queue
   ↓
4. Worker Pops Job
   ↓
5. Job Deserialized
   ↓
6. handle() Called
   ↓
   ├─ Success → Job Deleted
   │
   └─ Failure → attempts < max_tries?
               ├─ Yes → Release Back to Queue (with delay)
               └─ No  → failed() Called → Move to Failed Jobs
```

## Best Practices

### 1. Keep Jobs Small and Focused

```python
# ✅ Good - focused on one task
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

### 3. Set Appropriate Timeouts

```python
class QuickJob(Job):
    timeout = 30  # Quick tasks

class DataProcessingJob(Job):
    timeout = 300  # Data processing

class ReportJob(Job):
    timeout = 600  # Long-running reports
```

### 4. Use Descriptive Class Names

```python
# ✅ Good
class SendPasswordResetEmailJob(Job):
    pass

class ProcessIoTSensorDataJob(Job):
    pass

# ❌ Bad
class Job1(Job):
    pass

class DoStuff(Job):
    pass
```

### 5. Log Appropriately

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

## Next Steps

- [Learn how to dispatch jobs](./dispatching-jobs.md)
- [Run queue workers](./running-workers.md)
- [Handle failed jobs](./failed-jobs.md)
