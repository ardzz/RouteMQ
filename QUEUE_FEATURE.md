# Background Task Queue System

This PR adds a comprehensive background task queue system to RouteMQ, similar to Laravel's queue functionality.

## Features Added

### Core Components

1. **Job Base Class** (`core/job.py`)
   - Abstract base class for all background jobs
   - Automatic serialization/deserialization
   - Configurable retries, timeouts, and delays
   - Failed job handling

2. **Queue Drivers** (`core/queue/`)
   - **Redis Queue** - Fast, in-memory queue using Redis lists and sorted sets
   - **Database Queue** - Persistent queue using MySQL with ACID guarantees
   - Abstract driver interface for extensibility

3. **Queue Manager** (`core/queue/queue_manager.py`)
   - Job dispatching with `dispatch()` helper
   - Support for delayed jobs
   - Bulk job dispatching
   - Multiple queue support

4. **Queue Worker** (`core/queue/queue_worker.py`)
   - Background worker to process queued jobs
   - Graceful shutdown support (SIGTERM, SIGINT)
   - Configurable limits (max jobs, max time)
   - Automatic retry logic with delays
   - Failed job tracking

### Database Models

- `queue_jobs` table - Stores pending and reserved jobs
- `queue_failed_jobs` table - Stores permanently failed jobs

### CLI Integration

New command: `--queue-work`

```bash
# Basic usage
python main.py --queue-work

# Advanced options
python main.py --queue-work \
    --queue default \
    --connection redis \
    --max-jobs 100 \
    --max-time 3600 \
    --sleep 3 \
    --timeout 60
```

### Example Jobs

Three example jobs demonstrating different use cases:

1. **SendEmailJob** - Email notifications with retry logic
2. **ProcessDataJob** - IoT sensor data processing
3. **GenerateReportJob** - Long-running report generation with delays

### Documentation

Comprehensive documentation in `docs/queue-system.md` covering:
- Configuration
- Creating jobs
- Dispatching jobs
- Running workers
- Queue drivers
- Failed job handling
- Best practices
- Troubleshooting

## Usage Example

### 1. Create a Job

```python
# app/jobs/send_notification_job.py
from core.job import Job

class SendNotificationJob(Job):
    max_tries = 3
    timeout = 60
    queue = "notifications"

    def __init__(self):
        super().__init__()
        self.user_id = None
        self.message = None

    async def handle(self):
        # Send notification logic
        print(f"Sending to user {self.user_id}: {self.message}")
```

### 2. Dispatch the Job

```python
from core.queue.queue_manager import dispatch
from app.jobs.send_notification_job import SendNotificationJob

# In your MQTT handler
async def handle_message(context):
    job = SendNotificationJob()
    job.user_id = 123
    job.message = "Hello!"
    await dispatch(job)
```

### 3. Run the Worker

```bash
python main.py --queue-work --queue notifications
```

## Configuration

Add to `.env`:

```env
# Queue connection: 'redis' or 'database'
QUEUE_CONNECTION=redis

# Enable Redis (for Redis queue)
ENABLE_REDIS=true

# Enable MySQL (for Database queue or failed job storage)
ENABLE_MYSQL=true
```

## Benefits

- ✅ **Non-blocking** - Keep MQTT handlers fast and responsive
- ✅ **Scalable** - Run multiple workers for high throughput
- ✅ **Reliable** - Automatic retries and failure tracking
- ✅ **Flexible** - Multiple queues for different priorities
- ✅ **Persistent** - Database queue survives restarts
- ✅ **Fast** - Redis queue for low-latency processing

## Files Changed/Added

### Core Infrastructure
- `core/job.py` - Base Job class
- `core/queue/__init__.py` - Queue module exports
- `core/queue/queue_driver.py` - Abstract queue driver
- `core/queue/queue_manager.py` - Queue manager and dispatch helper
- `core/queue/queue_worker.py` - Queue worker implementation
- `core/queue/redis_queue.py` - Redis queue driver
- `core/queue/database_queue.py` - Database queue driver

### Database Models
- `app/models/queue_job.py` - QueueJob model
- `app/models/queue_failed_job.py` - QueueFailedJob model

### Examples
- `app/jobs/__init__.py` - Jobs package
- `app/jobs/example_email_job.py` - Email job example
- `app/jobs/example_data_processing_job.py` - Data processing example
- `app/jobs/example_report_job.py` - Report generation example

### Configuration
- `.env.example` - Added QUEUE_CONNECTION setting
- `main.py` - Added --queue-work CLI command and options
- `bootstrap/app.py` - Added connection helper methods

### Documentation
- `docs/queue-system.md` - Comprehensive queue system documentation
- `QUEUE_FEATURE.md` - This feature summary
- `test_queue.py` - Basic test script

## Testing

1. **Syntax validation** - All Python files compile successfully
2. **Example jobs** - Three working job examples provided
3. **Documentation** - Complete usage guide with examples

## Next Steps

Users can now:
1. Create custom jobs by extending the `Job` class
2. Dispatch jobs from MQTT handlers or anywhere in the application
3. Run workers to process queued jobs
4. Monitor failed jobs for debugging
5. Scale horizontally by adding more workers

## Migration Notes

This is a new feature with no breaking changes. Existing RouteMQ applications will continue to work without modification. The queue system is opt-in and requires:

1. Adding `QUEUE_CONNECTION` to `.env`
2. Enabling Redis or MySQL
3. Running `python main.py --queue-work` to start workers

## References

- Inspired by Laravel's Queue system
- Uses similar patterns and naming conventions
- Adapted for Python's async/await paradigm
- Integrated seamlessly with RouteMQ's architecture
