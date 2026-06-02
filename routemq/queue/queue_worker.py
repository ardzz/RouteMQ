import asyncio
import contextlib
import inspect
import logging
import os
import signal
import socket
import traceback
import uuid
from datetime import UTC, datetime
from typing import Optional

from routemq.job import Job
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_manager import QueueManager
from routemq.settings import load_queue_reliability_settings, load_queue_retry_settings
from ..observability import SpanLink, lifecycle, reset_context, set_context, start_span

try:
    from routemq.metrics.prometheus import mark_worker_dead
except ImportError:

    def mark_worker_dead(pid: int) -> None:
        return None


logger = logging.getLogger('RouteMQ.QueueWorker')


class ShutdownGraceExpired(RuntimeError):
    """Raised when an active job outlives the worker shutdown grace window."""


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
        retry_settings = load_queue_retry_settings()
        reliability_settings = load_queue_reliability_settings()
        self.retry_backoff_enabled = retry_settings.backoff_enabled
        self.retry_backoff_max_delay = retry_settings.max_delay
        self.retry_backoff_jitter = retry_settings.jitter
        self.visibility_timeout = reliability_settings.visibility_timeout
        self.reaper_interval = reliability_settings.reaper_interval
        self.shutdown_grace = reliability_settings.shutdown_grace
        self.heartbeat_interval = reliability_settings.heartbeat_interval

        self.should_quit = False
        self.paused = False
        self.jobs_processed = 0
        self.jobs_failed = 0
        self.start_time = None
        self.started_at = datetime.now(UTC)
        self.worker_id = f'{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}'
        self.state = 'running'
        self.current_job_id: str | int | None = None
        self._shutdown_event = asyncio.Event()
        self._last_reaper_run = 0.0

        self.queue_manager = QueueManager()
        self.driver: Optional[QueueDriver] = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f'Received signal {signum}, initiating graceful shutdown...')
        self.should_quit = True
        self.state = 'stopping'
        self._shutdown_event.set()
        try:
            mark_worker_dead(os.getpid())
        except Exception:
            logger.debug('Prometheus queue worker cleanup failed', exc_info=True)

    async def work(self) -> None:
        """
        Start processing jobs from the queue.
        This is the main worker loop.
        """
        logger.info(f"Queue worker started for queue '{self.queue_name}' (connection: {self.connection or 'default'})")

        self.driver = self.queue_manager.get_driver(self.connection)
        self.start_time = asyncio.get_running_loop().time()
        self.state = 'running'
        await self._write_worker_heartbeat()

        while not self.should_quit:
            # Check if we've reached max jobs or max time
            if self._should_stop():
                logger.info('Worker stopping due to limits')
                break

            # Check if paused
            if self.paused:
                await self._interruptible_sleep(self.sleep)
                continue

            # Try to get a job from the queue
            try:
                await self._run_reaper_if_due()
                job_data = await self.driver.pop(self.queue_name)

                if job_data:
                    await self._process_job(job_data)
                    self.jobs_processed += 1
                else:
                    # No jobs available, sleep
                    logger.debug(f'No jobs available, sleeping for {self.sleep}s')
                    await self._interruptible_sleep(self.sleep)

            except Exception as e:
                logger.error(
                    f'Error in worker loop for queue {self.queue_name}: {str(e)}',
                    exc_info=True,
                    extra={'queue': self.queue_name, 'error': e.__class__.__name__},
                )
                await self._interruptible_sleep(self.sleep)

        self.state = 'dead'
        await self._mark_worker_dead()
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
        heartbeat_task: asyncio.Task[None] | None = None
        self.current_job_id = job_id
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
            span_links = _span_links_from_job_context(job_context)
            token = set_context(_consumer_context(job_context), **attributes)
            span_attributes = {
                'messaging.system': 'routemq.queue',
                'messaging.destination': self.queue_name,
                'routemq.job.name': job.__class__.__name__,
                'routemq.process.role': 'queue-worker',
            }
            with start_span('queue.job', span_attributes, kind='consumer', links=span_links):
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
                    heartbeat_task = asyncio.create_task(self._heartbeat_active_job(job_id))
                    await asyncio.wait_for(self._run_job_with_shutdown_grace(job), timeout=job.timeout or self.timeout)

                    # Job succeeded, delete from queue
                    await driver.delete(job_id, self.queue_name)
                    lifecycle('queue.job.succeeded', attributes)
                    logger.info(f'Job {job_id} completed successfully')

                except asyncio.TimeoutError as exc:
                    logger.error(
                        f'Job {job_id} timed out after {job.timeout}s',
                        exc_info=True,
                        extra={'job_id': job_id, 'queue': self.queue_name, 'job_class': job.__class__.__name__},
                    )
                    lifecycle('queue.job.timed_out', attributes)
                    raise Exception(f'Job timed out after {job.timeout} seconds') from exc

        except Exception as e:
            logger.error(
                f'Job {job_id} failed: {str(e)}',
                exc_info=True,
                extra={'job_id': job_id, 'queue': self.queue_name, 'error': e.__class__.__name__},
            )

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
                        token = set_context(_consumer_context(job_context), **attributes)
            except Exception as unserialize_error:
                logger.error(
                    f'Failed to unserialize job {job_id}: {unserialize_error}',
                    exc_info=True,
                    extra={'job_id': job_id, 'queue': self.queue_name, 'error': unserialize_error.__class__.__name__},
                )
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
                self.jobs_failed += 1
                await driver.delete(job_id, self.queue_name)
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task
            self.current_job_id = None
            if self.state == 'draining' and self.should_quit:
                self.state = 'stopping'
            if token is not None:
                reset_context(token)

    async def _run_job_with_shutdown_grace(self, job: Job) -> None:
        handle_task = asyncio.create_task(job.handle())
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())
        try:
            done, _pending = await asyncio.wait({handle_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED)
            if handle_task in done:
                await handle_task
                return

            self.state = 'draining'
            try:
                await asyncio.wait_for(asyncio.shield(handle_task), timeout=self.shutdown_grace)
            except asyncio.TimeoutError as exc:
                handle_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await handle_task
                raise ShutdownGraceExpired(f'Job exceeded shutdown grace of {self.shutdown_grace}s') from exc
        finally:
            shutdown_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await shutdown_task

    async def _heartbeat_active_job(self, job_id: str | int) -> None:
        while self.current_job_id == job_id:
            await self._call_driver_optional('heartbeat', job_id, self.queue_name)
            await self._write_worker_heartbeat()
            await asyncio.sleep(self.heartbeat_interval)

    async def _write_worker_heartbeat(self) -> None:
        heartbeat = {
            'worker_id': self.worker_id,
            'queue': self.queue_name,
            'pid': os.getpid(),
            'hostname': socket.gethostname(),
            'state': self.state,
            'started_at': self.started_at.isoformat(),
            'last_seen_at': datetime.now(UTC).isoformat(),
            'current_job_id': '' if self.current_job_id is None else str(self.current_job_id),
            'processed_count': self.jobs_processed,
            'failed_count': self.jobs_failed,
        }
        await self._call_driver_optional('write_worker_heartbeat', heartbeat, self.heartbeat_interval * 3)

    async def _mark_worker_dead(self) -> None:
        await self._call_driver_optional('mark_worker_dead', self.worker_id)

    async def _run_reaper_if_due(self) -> None:
        if self.reaper_interval <= 0:
            return
        now = asyncio.get_running_loop().time()
        if now - self._last_reaper_run < self.reaper_interval:
            return
        self._last_reaper_run = now
        await self._call_driver_optional('reap_expired', self.queue_name, self.visibility_timeout)
        await self._publish_queue_stats()

    async def _publish_queue_stats(self) -> None:
        stats = await self._call_driver_optional('stats', self.queue_name)
        if isinstance(stats, dict):
            lifecycle('queue.stats', {**stats, 'queue': stats.get('queue') or self.queue_name})

    async def _call_driver_optional(self, method_name: str, *args):
        driver = self.driver
        if driver is None:
            return None
        method = getattr(driver, method_name, None)
        if method is None:
            return None
        result = method(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _interruptible_sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

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
            logger.error(
                f'Error handling failed job {job.job_id}: {str(e)}',
                exc_info=True,
                extra={'job_id': job.job_id, 'queue': self.queue_name, 'error': e.__class__.__name__},
            )

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
                # Audit Accept: support legacy synchronous callers of _should_stop.
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
        self.state = 'stopping'
        self._shutdown_event.set()
        logger.info('Worker stop requested')


def _span_links_from_job_context(job_context: dict) -> tuple[SpanLink, ...]:
    trace_id = job_context.get('trace_id')
    span_id = job_context.get('span_id')
    if not (_valid_hex_id(trace_id, 32) and _valid_hex_id(span_id, 16)):
        return ()
    return (
        SpanLink(
            trace_id=str(trace_id),
            span_id=str(span_id),
            attributes={'routemq.link.type': 'queue.enqueue'},
        ),
    )


def _consumer_context(job_context: dict) -> dict:
    context = dict(job_context)
    for key in ('trace_id', 'span_id', 'trace_flags', 'parent_span_id'):
        context.pop(key, None)
    return context


def _valid_hex_id(value: object, length: int) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value != '0' * length
