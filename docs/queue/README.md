# Queue System

RouteMQ includes a background task queue similar to Laravel's queue API. Use it to move slow work, such as alerts, telemetry processing, reports, or notifications, out of MQTT handlers.

## Overview

The queue system consists of several components:

- **Job**: A class that defines a task to be executed in the background
- **Queue Manager**: Dispatches jobs to queues
- **Queue Driver**: Handles storage and retrieval of jobs (Redis, Database, or registered custom drivers)
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
│Redis/DB/Custom  │
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
from routemq.job import Job


@Job.register
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

from routemq.queue import dispatch

job = SendEmailJob()
job.to = "user@example.com"
job.subject = "Welcome!"
await dispatch(job)

# Run the worker with:
# routemq queue-work --queue emails
```

## Key Features

- Laravel-style job classes with `handle()` and `failed()` hooks
- Redis or database queue drivers
- Custom drivers registered in code or with Python package entry points
- Retries, delays, multiple queues, and failed-job storage
- Workers that handle SIGTERM/SIGINT cleanly

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
from routemq.queue.queue_manager import dispatch
from app.jobs.send_email_job import SendEmailJob

async def handle_user_signup(context):
    job = SendEmailJob()
    job.to = context["payload"]["email"]
    job.template = "welcome"
    await dispatch(job)
```

### 2. Data Processing

```python
from routemq.queue.queue_manager import queue

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
