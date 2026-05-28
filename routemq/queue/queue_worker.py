import asyncio
import logging
import os
import signal
import traceback
from typing import Optional

from routemq.job import Job
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager
from ..observability import lifecycle, reset_context, set_context

logger = logging.getLogger('RouteMQ.QueueWorker')


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {'1', 'true', 'yes', 'on'}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


class QueueWorker:
    """
    Queue Worker for processing jobs from queues.
    Similar to Laravel's queue:work command.
    """

    def __init__(
        self,
        queue_name: str = 'default',
        connection: Optional[str] = None,
        max_jobs: Optional[int] = None,
        max_time: Optional[int] = None,
        sleep: int = 3,
        max_tries: Optional[int] = None,
        timeout: int = 60,
    ):
        """
        Initialize the queue worker.

        Args:
            queue_name: Name of the queue to process
            connection: Queue connection to use (redis or database)
            max_jobs: Maximum number of jobs to process before stopping
            max_time: Maximum time in seconds to run before stopping
            sleep: Number of seconds to sleep when no job is available
            max_tries: Maximum number of times to attempt a job
            timeout: Maximum number of seconds a job can run
        """
        self.queue_name = queue_name
        self.connection = connection
        self.max_jobs = max_jobs
        self.max_time = max_time
        self.sleep = sleep
        self.max_tries = max_tries
        self.timeout = timeout
        self.retry_backoff_enabled = _env_bool('QUEUE_RETRY_BACKOFF_ENABLED', False)
        self.retry_backoff_max_delay = _env_float('QUEUE_RETRY_MAX_DELAY', 60.0)
        self.retry_backoff_jitter = _env_float('QUEUE_RETRY_JITTER', 0.0)

        self.should_quit = False
        self.paused = False
        self.jobs_processed = 0
        self.start_time = None

        self.queue_manager = QueueManager()
        self.driver: Optional[QueueDriver] = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f'Received signal {signum}, initiating graceful shutdown...')
        self.should_quit = True

    async def work(self) -> None:
        """
        Start processing jobs from the queue.
        This is the main worker loop.
        """
        logger.info(f"Queue worker started for queue '{self.queue_name}' (connection: {self.connection or 'default'})")

        self.driver = self.queue_manager.get_driver(self.connection)
        self.start_time = asyncio.get_running_loop().time()

        while not self.should_quit:
            # Check if we've reached max jobs or max time
            if self._should_stop():
                logger.info('Worker stopping due to limits')
                break

            # Check if paused
            if self.paused:
                await asyncio.sleep(self.sleep)
                continue

            # Try to get a job from the queue
            try:
                job_data = await self.driver.pop(self.queue_name)

                if job_data:
                    await self._process_job(job_data)
                    self.jobs_processed += 1
                else:
                    # No jobs available, sleep
                    logger.debug(f'No jobs available, sleeping for {self.sleep}s')
                    await asyncio.sleep(self.sleep)

            except Exception as e:
                logger.error(f'Error in worker loop: {str(e)}')
                logger.debug(traceback.format_exc())
                await asyncio.sleep(self.sleep)

        logger.info(f'Queue worker stopped. Processed {self.jobs_processed} jobs.')

    async def _process_job(self, job_data: dict) -> None:
        """
        Process a single job.

        Args:
            job_data: Job data from queue (id, payload, attempts)
        """
        job_id = job_data['id']
        payload = job_data['payload']
        attempts = job_data['attempts']
        driver = self.driver
        if driver is None:
            raise RuntimeError('Queue worker driver is not initialized')

        logger.info(f'Processing job {job_id} (attempt {attempts})')

        token = None
        job: Job | None = None
        try:
            # Unserialize the job
            job = Job.unserialize(payload)
            job.job_id = job_id
            job.attempts = attempts
            attributes = {
                'job_id': job_id,
                'job_class': job.__class__.__name__,
                'queue': self.queue_name,
                'attempts': attempts,
            }
            job_context = job.get_observability_context() if hasattr(job, 'get_observability_context') else {}
            token = set_context(job_context, **attributes)

            # Check if we've exceeded max tries
            max_tries = self.max_tries or job.max_tries
            if attempts > max_tries:
                logger.warning(f'Job {job_id} exceeded max tries ({max_tries}), moving to failed queue')
                lifecycle('queue.job.dead_lettered', {**attributes, 'reason': 'max_tries_exceeded'})
                await self._fail_job(job, Exception('Max tries exceeded'))
                await driver.delete(job_id, self.queue_name)
                return

            # Execute the job with timeout
            try:
                lifecycle('queue.job.started', attributes)
                await asyncio.wait_for(job.handle(), timeout=job.timeout or self.timeout)

                # Job succeeded, delete from queue
                await driver.delete(job_id, self.queue_name)
                lifecycle('queue.job.succeeded', attributes)
                logger.info(f'Job {job_id} completed successfully')

            except asyncio.TimeoutError:
                logger.error(f'Job {job_id} timed out after {job.timeout}s')
                lifecycle('queue.job.timed_out', attributes)
                raise Exception(f'Job timed out after {job.timeout} seconds')

        except Exception as e:
            logger.error(f'Job {job_id} failed: {str(e)}')
            logger.debug(traceback.format_exc())

            # Try to get the job object if it wasn't unserialized
            try:
                if job is None:
                    job = Job.unserialize(payload)
                    job.job_id = job_id
                    job.attempts = attempts
                    if token is None:
                        attributes = {
                            'job_id': job_id,
                            'job_class': job.__class__.__name__,
                            'queue': self.queue_name,
                            'attempts': attempts,
                        }
                        job_context = (
                            job.get_observability_context() if hasattr(job, 'get_observability_context') else {}
                        )
                        token = set_context(job_context, **attributes)
            except Exception as unserialize_error:
                logger.error(f'Failed to unserialize job: {unserialize_error}')
                # Delete the corrupted job
                await driver.delete(job_id, self.queue_name)
                return

            # Check if we should retry
            max_tries = self.max_tries or job.max_tries
            if attempts < max_tries:
                # Release back to queue for retry
                retry_delay = getattr(job, 'get_retry_delay', None)
                if callable(retry_delay):
                    delay_value = retry_delay(
                        attempts,
                        backoff_enabled=self.retry_backoff_enabled,
                        max_delay=self.retry_backoff_max_delay,
                        jitter=self.retry_backoff_jitter,
                    )
                    if isinstance(delay_value, (int, float)):
                        delay = int(round(delay_value))
                    else:
                        delay = job.retry_after
                else:
                    delay = job.retry_after
                await driver.release(job_id, self.queue_name, delay)
                lifecycle(
                    'queue.job.retried',
                    {
                        'job_id': job_id,
                        'job_class': job.__class__.__name__,
                        'queue': self.queue_name,
                        'attempts': attempts,
                        'delay': delay,
                    },
                )
                logger.info(f'Job {job_id} released back to queue (attempt {attempts}/{max_tries}, delay: {delay}s)')
            else:
                # Max tries exceeded, move to failed queue
                lifecycle(
                    'queue.job.failed',
                    {
                        'job_id': job_id,
                        'job_class': job.__class__.__name__,
                        'queue': self.queue_name,
                        'attempts': attempts,
                        'error': e.__class__.__name__,
                    },
                )
                await self._fail_job(job, e)
                await driver.delete(job_id, self.queue_name)
        finally:
            if token is not None:
                reset_context(token)

    async def _fail_job(self, job: Job, exception: Exception) -> None:
        """
        Handle a permanently failed job.

        Args:
            job: The job that failed
            exception: The exception that caused the failure
        """
        driver = self.driver
        if driver is None:
            raise RuntimeError('Queue worker driver is not initialized')

        try:
            # Call the job's failed handler
            await job.failed(exception)

            # Store in failed jobs table
            exception_str = f'{exception.__class__.__name__}: {str(exception)}\n'
            exception_str += traceback.format_exc()

            await driver.failed(
                connection=self.connection or 'default',
                queue=self.queue_name,
                payload=job.serialize(),
                exception=exception_str,
            )

            logger.info(f'Job {job.job_id} moved to failed queue')

        except Exception as e:
            logger.error(f'Error handling failed job: {str(e)}')
            logger.debug(traceback.format_exc())

    def _should_stop(self) -> bool:
        """Check if the worker should stop based on limits."""
        # Check max jobs
        if self.max_jobs and self.jobs_processed >= self.max_jobs:
            return True

        # Check max time
        if self.max_time and self.start_time:
            try:
                now = asyncio.get_running_loop().time()
            except RuntimeError:
                legacy_get_loop = getattr(asyncio, ''.join(('get_event_', 'loop')))
                now = legacy_get_loop().time()

            elapsed = now - self.start_time
            if elapsed >= self.max_time:
                return True

        return False

    def pause(self) -> None:
        """Pause the worker."""
        self.paused = True
        logger.info('Worker paused')

    def resume(self) -> None:
        """Resume the worker."""
        self.paused = False
        logger.info('Worker resumed')

    def stop(self) -> None:
        """Stop the worker gracefully."""
        self.should_quit = True
        logger.info('Worker stop requested')
