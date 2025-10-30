# Dispatching Jobs

Once you've created a job, you need to dispatch it to the queue for processing. RouteMQ provides several methods for dispatching jobs.

## Using the dispatch() Helper

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

The `dispatch()` helper:
- Uses the queue specified in the job (`job.queue`)
- Uses the default connection from `.env`
- Returns immediately after pushing to queue

## Using the Queue Manager

For more control, use the `QueueManager` directly:

```python
from core.queue.queue_manager import queue
from app.jobs.send_email_job import SendEmailJob

# Create job
job = SendEmailJob()
job.to = "user@example.com"
job.subject = "Welcome!"
job.body = "Thanks for signing up!"

# Dispatch to default queue
await queue.push(job)

# Dispatch to specific queue
await queue.push(job, queue="emails")

# Dispatch to specific connection
await queue.push(job, connection="database")
```

## Delayed Jobs

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

# Run after 24 hours
await queue.later(86400, job)
```

**How delayed jobs work:**
- Job is stored with an `available_at` timestamp
- Worker ignores the job until the timestamp is reached
- Redis uses sorted sets for efficient delay handling
- Database uses datetime comparison

## Bulk Dispatching

Dispatch multiple jobs at once:

```python
from core.queue.queue_manager import queue
from app.jobs.send_notification_job import SendNotificationJob

jobs = []
for user_id in user_ids:
    job = SendNotificationJob()
    job.user_id = user_id
    job.message = "System maintenance tonight"
    jobs.append(job)

# Dispatch all jobs
await queue.bulk(jobs)
```

This is more efficient than dispatching jobs one by one in a loop.

## Dispatching from MQTT Handlers

### Example 1: Dispatch from Controller

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

### Example 2: Dispatch with Middleware

```python
# app/middleware/queue_middleware.py
from core.middleware import Middleware
from core.queue.queue_manager import dispatch
from app.jobs.log_message_job import LogMessageJob


class QueueMiddleware(Middleware):
    async def handle(self, context, next_handler):
        # Dispatch logging job
        job = LogMessageJob()
        job.topic = context['topic']
        job.payload = context['payload']
        await dispatch(job)

        # Continue processing
        return await next_handler(context)
```

### Example 3: Conditional Dispatching

```python
async def handle_sensor_data(device_id: str, payload, client):
    temperature = payload.get('temperature')

    # Only queue processing for high temperatures
    if temperature > 30:
        job = ProcessHighTempJob()
        job.device_id = device_id
        job.temperature = temperature
        await dispatch(job)

    return {"status": "received"}
```

## Checking Queue Size

Monitor how many jobs are pending:

```python
from core.queue.queue_manager import queue

# Check queue size
size = await queue.size("default")
print(f"Pending jobs: {size}")

# Check multiple queues
for queue_name in ["default", "emails", "reports"]:
    size = await queue.size(queue_name)
    print(f"{queue_name}: {size} jobs")
```

## Queue Manager API Reference

### push()

Push a job to the queue immediately.

```python
await queue.push(
    job,                    # Job instance (required)
    queue="default",        # Queue name (optional)
    connection="redis"      # Connection (optional)
)
```

### later()

Push a job with a delay.

```python
await queue.later(
    delay,                  # Delay in seconds (required)
    job,                    # Job instance (required)
    queue="default",        # Queue name (optional)
    connection="redis"      # Connection (optional)
)
```

### bulk()

Push multiple jobs at once.

```python
await queue.bulk(
    jobs,                   # List of Job instances (required)
    queue="default",        # Queue name (optional)
    connection="redis"      # Connection (optional)
)
```

### size()

Get the number of pending jobs in a queue.

```python
size = await queue.size(
    queue="default",        # Queue name (optional)
    connection="redis"      # Connection (optional)
)
```

## Common Patterns

### Pattern 1: Fan-out

Dispatch multiple jobs from one event:

```python
async def handle_user_signup(user_id, email):
    # Send welcome email
    email_job = SendEmailJob()
    email_job.to = email
    email_job.template = "welcome"
    await dispatch(email_job)

    # Create user profile
    profile_job = CreateProfileJob()
    profile_job.user_id = user_id
    await dispatch(profile_job)

    # Send SMS verification
    sms_job = SendSMSJob()
    sms_job.user_id = user_id
    await dispatch(sms_job)
```

### Pattern 2: Delayed Chain

Schedule a series of jobs:

```python
from core.queue.queue_manager import queue

# Send welcome email immediately
welcome_job = SendEmailJob()
welcome_job.to = email
welcome_job.template = "welcome"
await dispatch(welcome_job)

# Send tips email after 1 day
tips_job = SendEmailJob()
tips_job.to = email
tips_job.template = "tips"
await queue.later(86400, tips_job)  # 24 hours

# Send feedback request after 7 days
feedback_job = SendEmailJob()
feedback_job.to = email
feedback_job.template = "feedback"
await queue.later(604800, feedback_job)  # 7 days
```

### Pattern 3: Priority Queues

Use different queues for different priorities:

```python
# High priority - immediate processing
if is_urgent:
    job.queue = "high-priority"
    await dispatch(job)

# Normal priority
elif is_normal:
    job.queue = "default"
    await dispatch(job)

# Low priority - background cleanup
else:
    job.queue = "low-priority"
    await dispatch(job)
```

Then run workers with appropriate settings:

```bash
# High priority - check every second
python main.py --queue-work --queue high-priority --sleep 1

# Normal priority - check every 3 seconds
python main.py --queue-work --queue default --sleep 3

# Low priority - check every 10 seconds
python main.py --queue-work --queue low-priority --sleep 10
```

### Pattern 4: Rate Limiting

Prevent overwhelming external services:

```python
async def send_to_external_api(data):
    # Dispatch job instead of calling API directly
    job = ExternalAPIJob()
    job.data = data
    await dispatch(job)

    # Worker processes these at controlled rate
    # Can even add delays: await queue.later(5, job)
```

## Error Handling

### Handle Dispatch Errors

```python
from core.queue.queue_manager import dispatch

try:
    job = SendEmailJob()
    job.to = "user@example.com"
    await dispatch(job)
    print("Job dispatched successfully")

except Exception as e:
    print(f"Failed to dispatch job: {e}")
    # Handle error (log, retry, alert, etc.)
```

### Verify Job Data

```python
def create_email_job(to, subject, body):
    # Validate data before dispatching
    if not to or '@' not in to:
        raise ValueError("Invalid email address")

    if not subject:
        raise ValueError("Subject is required")

    job = SendEmailJob()
    job.to = to
    job.subject = subject
    job.body = body

    return job

# Use it
try:
    job = create_email_job(email, subject, body)
    await dispatch(job)
except ValueError as e:
    print(f"Invalid job data: {e}")
```

## Best Practices

### 1. Dispatch Early, Process Later

```python
# ✅ Good - dispatch and return quickly
async def handle_order(order_data):
    job = ProcessOrderJob()
    job.order_data = order_data
    await dispatch(job)
    return {"status": "accepted"}

# ❌ Bad - blocking the handler
async def handle_order(order_data):
    await process_order(order_data)  # Takes 30 seconds!
    return {"status": "processed"}
```

### 2. Don't Dispatch Too Much Data

```python
# ✅ Good - store ID only
job = ProcessOrderJob()
job.order_id = order_id  # Small
await dispatch(job)

# In handle():
# order = await fetch_order(self.order_id)

# ❌ Bad - storing large data
job = ProcessOrderJob()
job.order_data = huge_dictionary  # Large payload
await dispatch(job)
```

### 3. Use Appropriate Delays

```python
# ✅ Good - reasonable delays
await queue.later(60, job)      # 1 minute
await queue.later(3600, job)    # 1 hour
await queue.later(86400, job)   # 1 day

# ❌ Bad - very long delays
await queue.later(31536000, job)  # 1 year - use a scheduler instead
```

### 4. Choose the Right Queue

```python
# ✅ Good - organized by purpose
email_job.queue = "emails"
report_job.queue = "reports"
cleanup_job.queue = "low-priority"

# ❌ Bad - everything in default
job.queue = "default"  # For all jobs
```

## Next Steps

- [Learn how to run queue workers](./running-workers.md)
- [Understand queue drivers](./drivers.md)
- [Handle failed jobs](./failed-jobs.md)
