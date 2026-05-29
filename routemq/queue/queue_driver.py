from abc import ABC, abstractmethod
from typing import Any, Optional, Union
from datetime import datetime


class QueueDriver(ABC):
    """
    Abstract base class for queue drivers.
    Implementations can use Redis, Database, or any other backend.
    """

    @abstractmethod
    async def push(
        self,
        payload: str,
        queue: str = 'default',
        delay: int = 0,
    ) -> None:
        """
        Push a new job onto the queue.

        Args:
            payload: Serialized job data
            queue: Queue name
            delay: Delay in seconds before the job becomes available
        """
        pass

    @abstractmethod
    async def pop(self, queue: str = 'default') -> Optional[dict]:
        """
        Pop the next available job from the queue.

        Args:
            queue: Queue name

        Returns:
            Dictionary with job data: {id, payload, attempts} or None if no jobs available
        """
        pass

    @abstractmethod
    async def release(
        self,
        job_id: Union[int, str],
        queue: str,
        delay: int = 0,
    ) -> None:
        """
        Release a job back to the queue (for retry).

        Args:
            job_id: Job identifier (int for database driver, str for redis driver)
            queue: Queue name
            delay: Delay in seconds before the job becomes available again
        """
        pass

    @abstractmethod
    async def delete(self, job_id: Union[int, str], queue: str) -> None:
        """
        Delete a job from the queue.

        Args:
            job_id: Job identifier (int for database driver, str for redis driver)
            queue: Queue name
        """
        pass

    @abstractmethod
    async def failed(
        self,
        connection: str,
        queue: str,
        payload: str,
        exception: str,
    ) -> None:
        """
        Store a failed job.

        Args:
            connection: Connection name (e.g., 'redis', 'database')
            queue: Queue name
            payload: Serialized job data
            exception: Exception message
        """
        pass

    @abstractmethod
    async def size(self, queue: str = 'default') -> int:
        """
        Get the size of the queue.

        Args:
            queue: Queue name

        Returns:
            Number of jobs in the queue
        """
        pass

    async def stats(self, queue: str = 'default') -> dict[str, Any]:
        """Return queue-depth statistics when supported by the driver."""
        ready = await self.size(queue)
        return {
            'queue': queue,
            'ready': ready,
            'reserved': 0,
            'delayed': 0,
            'failed': 0,
            'oldest_ready_age_seconds': 0.0,
        }

    async def reap_expired(self, queue: str = 'default', visibility_timeout: int = 300) -> int:
        """Reclaim expired reserved jobs when supported by the driver."""
        return 0

    async def heartbeat(self, job_id: Union[int, str], queue: str) -> bool:
        """Refresh an active job reservation when supported by the driver."""
        return False

    async def write_worker_heartbeat(self, heartbeat: dict[str, Any], ttl: int) -> None:
        """Publish queue-worker liveness metadata when supported by the driver."""
        return None

    async def mark_worker_dead(self, worker_id: str) -> None:
        """Mark a queue worker as dead when supported by the driver."""
        return None

    async def list_failed_jobs(self, queue: str | None = None) -> list[dict[str, Any]]:
        """List failed jobs when supported by the driver."""
        return []

    async def get_failed_job(self, job_id: Union[int, str]) -> dict[str, Any] | None:
        """Return a failed job by id when supported by the driver."""
        return None

    async def retry_failed_job(self, job_id: Union[int, str]) -> bool:
        """Retry a failed job by id when supported by the driver."""
        return False

    async def forget_failed_job(self, job_id: Union[int, str]) -> bool:
        """Forget a failed job by id when supported by the driver."""
        return False

    async def flush_failed_jobs(self, queue: str | None = None) -> int:
        """Flush failed jobs when supported by the driver."""
        return 0
