import logging
import os
from typing import Optional

from routemq.job import Job
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.redis_queue import RedisQueue
from routemq.queue.database_queue import DatabaseQueue
from routemq.redis_manager import RedisManager
from routemq.model import Model
from ..observability import lifecycle

logger = logging.getLogger('RouteMQ.QueueManager')


class QueueManager:
    """
    Queue Manager for dispatching jobs to queues.
    Similar to Laravel's Queue facade.
    """

    _instance: Optional['QueueManager'] = None
    _driver: Optional[QueueDriver] = None
    _default_connection: str = 'redis'

    def __new__(cls) -> 'QueueManager':
        """Singleton pattern to ensure one queue manager instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the queue manager."""
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._default_connection = os.getenv('QUEUE_CONNECTION', 'redis')
        logger.info(f'QueueManager initialized with default connection: {self._default_connection}')

    def get_driver(self, connection: Optional[str] = None) -> QueueDriver:
        """
        Get the queue driver for the specified connection.

        Args:
            connection: Connection name ('redis' or 'database'). If None, uses default.

        Returns:
            QueueDriver instance

        Raises:
            RuntimeError: If the requested driver is not available
        """
        connection = self._resolve_connection(connection)

        if connection == 'redis':
            return RedisQueue()

        if connection == 'database':
            return DatabaseQueue()

        raise RuntimeError(f'Unknown queue connection: {connection}')

    def _resolve_connection(self, connection: Optional[str] = None) -> str:
        """Resolve the requested queue connection, including Redis-to-database fallback."""
        resolved = connection or self._default_connection

        if resolved == 'redis':
            redis_manager = RedisManager()
            if redis_manager.is_enabled():
                return 'redis'

            logger.warning('Redis is not available, falling back to database queue')
            resolved = 'database'

        if resolved == 'database':
            if not Model._is_enabled:
                raise RuntimeError(
                    'Cannot use database queue - MySQL is disabled. '
                    'Enable MySQL or configure Redis as queue connection.'
                )
            return 'database'

        raise RuntimeError(f'Unknown queue connection: {resolved}')

    async def push(
        self,
        job: Job,
        queue: Optional[str] = None,
        connection: Optional[str] = None,
    ) -> None:
        """
        Push a job to the queue.

        Args:
            job: Job instance to push
            queue: Queue name (uses job's queue if not specified)
            connection: Connection name (uses default if not specified)
        """
        queue = queue or job.queue
        driver = self.get_driver(connection)

        attributes = {
            'job_class': job.__class__.__name__,
            'queue': queue,
            'connection': connection or self._default_connection,
        }
        job.capture_observability_context(attributes)
        payload = job.serialize()
        lifecycle('queue.enqueue.started', attributes)
        try:
            await driver.push(payload, queue)
        except Exception as exc:
            lifecycle('queue.enqueue.failed', {**attributes, 'error': exc.__class__.__name__})
            raise
        else:
            lifecycle('queue.enqueue.succeeded', attributes)

        logger.info(f"Job {job.__class__.__name__} dispatched to queue '{queue}'")

    async def later(
        self,
        delay: int,
        job: Job,
        queue: Optional[str] = None,
        connection: Optional[str] = None,
    ) -> None:
        """
        Push a job to the queue with a delay.

        Args:
            delay: Delay in seconds before the job becomes available
            job: Job instance to push
            queue: Queue name (uses job's queue if not specified)
            connection: Connection name (uses default if not specified)
        """
        queue = queue or job.queue
        driver = self.get_driver(connection)

        attributes = {
            'job_class': job.__class__.__name__,
            'queue': queue,
            'connection': connection or self._default_connection,
            'delay': delay,
        }
        job.capture_observability_context(attributes)
        payload = job.serialize()
        lifecycle('queue.enqueue.started', attributes)
        try:
            await driver.push(payload, queue, delay)
        except Exception as exc:
            lifecycle('queue.enqueue.failed', {**attributes, 'error': exc.__class__.__name__})
            raise
        else:
            lifecycle('queue.enqueue.succeeded', attributes)

        logger.info(f"Job {job.__class__.__name__} scheduled to queue '{queue}' with {delay}s delay")

    async def bulk(
        self,
        jobs: list[Job],
        queue: Optional[str] = None,
        connection: Optional[str] = None,
    ) -> None:
        """
        Push multiple jobs to the queue.

        Args:
            jobs: List of Job instances to push
            queue: Queue name (uses each job's queue if not specified)
            connection: Connection name (uses default if not specified)
        """
        driver = self.get_driver(connection)

        for job in jobs:
            q = queue or job.queue
            attributes = {
                'job_class': job.__class__.__name__,
                'queue': q,
                'connection': connection or self._default_connection,
                'bulk': True,
            }
            job.capture_observability_context(attributes)
            payload = job.serialize()
            lifecycle('queue.enqueue.started', attributes)
            try:
                await driver.push(payload, q)
            except Exception as exc:
                lifecycle('queue.enqueue.failed', {**attributes, 'error': exc.__class__.__name__})
                raise
            else:
                lifecycle('queue.enqueue.succeeded', attributes)

        logger.info(f'Bulk dispatched {len(jobs)} jobs to queue')

    async def size(
        self,
        queue: str = 'default',
        connection: Optional[str] = None,
    ) -> int:
        """
        Get the size of the queue.

        Args:
            queue: Queue name
            connection: Connection name (uses default if not specified)

        Returns:
            Number of jobs in the queue
        """
        driver = self.get_driver(connection)
        return await driver.size(queue)


# Global queue manager instance
queue = QueueManager()


# Helper function for dispatching jobs (Laravel-style)
async def dispatch(job: Job) -> None:
    """
    Dispatch a job to the queue.

    Args:
        job: Job instance to dispatch

    Example:
        await dispatch(SendEmailJob(to="user@example.com", subject="Hello"))
    """
    await queue.push(job)
