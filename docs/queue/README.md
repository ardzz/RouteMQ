# Queue System

RouteMQ includes a powerful background task queue system similar to Laravel's queue functionality. This allows you to defer time-consuming tasks (like sending emails, processing data, generating reports) to background workers, keeping your MQTT message handlers fast and responsive.

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

## Quick Start

```python
# 1. Create a job
from core.job import Job

class SendEmailJob(Job):
    max_tries = 3
    queue = "emails"

    def __init__(self):
        super().__init__()
        self.to = None
        self.subject = None

    async def handle(self):
        # Send email logic
        print(f"Sending email to {self.to}")

# 2. Dispatch the job
from core.queue.queue_manager import dispatch

job = SendEmailJob()
job.to = "user@example.com"
job.subject = "Welcome!"
await dispatch(job)

# 3. Run the worker
# python main.py --queue-work --queue emails
```

## Key Features

- ✅ **Laravel-style API** - Familiar syntax for Laravel developers
- ✅ **Two Queue Drivers** - Redis (fast) or Database (persistent)
- ✅ **Automatic Retries** - Configurable retry logic with delays
- ✅ **Multiple Queues** - Organize jobs by priority or type
- ✅ **Delayed Jobs** - Schedule jobs to run later
- ✅ **Failed Job Tracking** - Inspect and retry failed jobs
- ✅ **Docker Support** - Production-ready deployment
- ✅ **Graceful Shutdown** - Workers handle SIGTERM/SIGINT

## Documentation

- [Getting Started](./getting-started.md) - Installation and configuration
- [Creating Jobs](./creating-jobs.md) - Define background tasks
- [Dispatching Jobs](./dispatching-jobs.md) - Send jobs to queues
- [Running Workers](./running-workers.md) - Process jobs in background
- [Queue Drivers](./drivers.md) - Redis vs Database queues
- [Failed Jobs](./failed-jobs.md) - Handle and retry failures
- [Best Practices](./best-practices.md) - Tips for production use

## Example Use Cases

### 1. Email Notifications

```python
from core.queue.queue_manager import dispatch
from app.jobs.send_email_job import SendEmailJob

async def handle_user_signup(context):
    job = SendEmailJob()
    job.to = context["payload"]["email"]
    job.template = "welcome"
    await dispatch(job)
```

### 2. Data Processing

```python
from core.queue.queue_manager import queue

job = ProcessDataJob()
job.device_id = device_id
job.sensor_data = data
await queue.push(job, queue="data-processing")
```

### 3. Scheduled Reports

```python
# Schedule report for 1 hour later
job = GenerateReportJob()
job.user_id = user_id
await queue.later(3600, job)  # 3600 seconds = 1 hour
```

## Next Steps

1. [Configure your queue](./getting-started.md) - Set up Redis or Database
2. [Create your first job](./creating-jobs.md) - Define a background task
3. [Dispatch jobs](./dispatching-jobs.md) - Send jobs from your code
4. [Run workers](./running-workers.md) - Process jobs in background
