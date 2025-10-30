from abc import ABC, abstractmethod
from typing import Optional
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
        queue: str = "default",
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
    async def pop(self, queue: str = "default") -> Optional[dict]:
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
        job_id: int,
        queue: str,
        delay: int = 0,
    ) -> None:
        """
        Release a job back to the queue (for retry).

        Args:
            job_id: Job identifier
            queue: Queue name
            delay: Delay in seconds before the job becomes available again
        """
        pass

    @abstractmethod
    async def delete(self, job_id: int, queue: str) -> None:
        """
        Delete a job from the queue.

        Args:
            job_id: Job identifier
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
    async def size(self, queue: str = "default") -> int:
        """
        Get the size of the queue.

        Args:
            queue: Queue name

        Returns:
            Number of jobs in the queue
        """
        pass
