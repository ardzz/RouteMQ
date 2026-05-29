import logging
import os
from collections.abc import Callable
from importlib import import_module
from importlib.metadata import entry_points
from typing import Optional

from routemq.job import Job
from routemq.queue.queue_driver import QueueDriver
from routemq.queue.redis_queue import RedisQueue
from routemq.queue.database_queue import DatabaseQueue
from routemq.redis_manager import RedisManager
from routemq.model import Model

logger = logging.getLogger('RouteMQ.QueueManager')

QueueDriverFactory = Callable[[], QueueDriver]
QUEUE_DRIVER_ENTRY_POINT_GROUP = 'routemq.queue_drivers'


def _lifecycle(event: str, attributes: dict) -> None:
    """Emit an observability lifecycle event."""
    import_module('routemq.observability').lifecycle(event, attributes)


def _start_span(name: str, attributes: dict, *, kind: str):
    """Start an observability span without importing at module load time."""

    return import_module('routemq.observability').start_span(name, attributes, kind=kind)


class QueueManager:
    """
    Queue Manager for dispatching jobs to queues.
    Similar to Laravel's Queue facade.
    """

    _instance: Optional['QueueManager'] = None
    _driver: Optional[QueueDriver] = None
    _default_connection: str = 'redis'
    _driver_factories: dict[str, QueueDriverFactory] = {}
    _entry_points_loaded: bool = False

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
        self._ensure_driver_registry_loaded()
        connection = self._resolve_connection(connection)
        factory = self._driver_factories[connection]
        driver = factory()

        if not isinstance(driver, QueueDriver):
            raise TypeError(f"Queue driver factory for '{connection}' did not return a QueueDriver instance")

        return driver

    @classmethod
    def register_driver(cls, name: str, factory: type[QueueDriver] | QueueDriverFactory) -> None:
        """
        Register a queue driver factory.

        Args:
            name: Connection name used by QUEUE_CONNECTION or get_driver().
            factory: QueueDriver subclass or zero-argument factory returning a QueueDriver.

        Raises:
            ValueError: If the driver name is empty.
            TypeError: If the factory is not callable or the class does not inherit QueueDriver.
        """
        normalized = name.strip()
        if not normalized:
            raise ValueError('Queue driver name cannot be empty')

        if isinstance(factory, type):
            if not issubclass(factory, QueueDriver):
                raise TypeError(f"Queue driver '{normalized}' must inherit QueueDriver")
            cls._driver_factories[normalized] = factory
            return

        if not callable(factory):
            raise TypeError(f"Queue driver factory for '{normalized}' must be callable")

        cls._driver_factories[normalized] = factory

    @classmethod
    def registered_drivers(cls) -> tuple[str, ...]:
        """Return the currently registered queue driver names."""
        cls._ensure_driver_registry_loaded()
        return tuple(sorted(cls._driver_factories))

    @classmethod
    def _ensure_driver_registry_loaded(cls) -> None:
        """Register built-in and entry-point queue drivers once."""
        cls._register_builtin_drivers()

        if cls._entry_points_loaded:
            return

        cls._entry_points_loaded = True
        for entry_point in entry_points(group=QUEUE_DRIVER_ENTRY_POINT_GROUP):
            if entry_point.name in cls._driver_factories:
                logger.debug(
                    "Skipping queue driver entry point '%s' because that name is already registered",
                    entry_point.name,
                )
                continue

            cls.register_driver(entry_point.name, entry_point.load())

    @classmethod
    def _register_builtin_drivers(cls) -> None:
        """Register built-in queue drivers without overriding explicit registrations."""
        cls._driver_factories.setdefault('redis', RedisQueue)
        cls._driver_factories.setdefault('database', DatabaseQueue)

    def _resolve_connection(self, connection: Optional[str] = None) -> str:
        """Resolve the requested queue connection, including Redis-to-database fallback."""
        self._ensure_driver_registry_loaded()
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

        if resolved in self._driver_factories:
            return resolved

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
        span_attributes = {
            'messaging.system': 'routemq.queue',
            'messaging.destination': queue,
            'routemq.job.name': job.__class__.__name__,
        }
        with _start_span('queue.enqueue', span_attributes, kind='producer'):
            job.capture_observability_context(attributes)
            payload = job.serialize()
            _lifecycle('queue.enqueue.started', attributes)
            try:
                await driver.push(payload, queue)
            except Exception as exc:
                _lifecycle('queue.enqueue.failed', {**attributes, 'error': exc.__class__.__name__})
                raise
            else:
                _lifecycle('queue.enqueue.succeeded', attributes)

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
        span_attributes = {
            'messaging.system': 'routemq.queue',
            'messaging.destination': queue,
            'routemq.job.name': job.__class__.__name__,
        }
        with _start_span('queue.enqueue', span_attributes, kind='producer'):
            job.capture_observability_context(attributes)
            payload = job.serialize()
            _lifecycle('queue.enqueue.started', attributes)
            try:
                await driver.push(payload, queue, delay)
            except Exception as exc:
                _lifecycle('queue.enqueue.failed', {**attributes, 'error': exc.__class__.__name__})
                raise
            else:
                _lifecycle('queue.enqueue.succeeded', attributes)

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
            span_attributes = {
                'messaging.system': 'routemq.queue',
                'messaging.destination': q,
                'routemq.job.name': job.__class__.__name__,
            }
            with _start_span('queue.enqueue', span_attributes, kind='producer'):
                job.capture_observability_context(attributes)
                payload = job.serialize()
                _lifecycle('queue.enqueue.started', attributes)
                try:
                    await driver.push(payload, q)
                except Exception as exc:
                    _lifecycle('queue.enqueue.failed', {**attributes, 'error': exc.__class__.__name__})
                    raise
                else:
                    _lifecycle('queue.enqueue.succeeded', attributes)

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

    async def stats(self, queue: str = 'default', connection: Optional[str] = None) -> dict:
        """Get queue-depth statistics and publish them to observability hooks."""
        driver = self.get_driver(connection)
        stats = await driver.stats(queue)
        _lifecycle('queue.stats', stats)
        return stats

    async def list_failed_jobs(self, queue: str | None = None, connection: Optional[str] = None) -> list[dict]:
        driver = self.get_driver(connection)
        return await driver.list_failed_jobs(queue)

    async def get_failed_job(self, job_id: int | str, connection: Optional[str] = None) -> dict | None:
        driver = self.get_driver(connection)
        return await driver.get_failed_job(job_id)

    async def retry_failed_job(self, job_id: int | str, connection: Optional[str] = None) -> bool:
        driver = self.get_driver(connection)
        return await driver.retry_failed_job(job_id)

    async def forget_failed_job(self, job_id: int | str, connection: Optional[str] = None) -> bool:
        driver = self.get_driver(connection)
        return await driver.forget_failed_job(job_id)

    async def flush_failed_jobs(self, queue: str | None = None, connection: Optional[str] = None) -> int:
        driver = self.get_driver(connection)
        return await driver.flush_failed_jobs(queue)


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
