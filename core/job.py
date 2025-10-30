import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger("RouteMQ.Job")


class Job(ABC):
    """
    Base Job class that all background jobs should extend.
    Similar to Laravel's Job class.
    """

    # Maximum number of times the job may be attempted
    max_tries: int = 3

    # Number of seconds the job can run before timing out
    timeout: int = 60

    # Number of seconds to wait before retrying the job after a failure
    retry_after: int = 0

    # The name of the queue the job should be sent to
    queue: str = "default"

    def __init__(self):
        """Initialize the job."""
        self.job_id: Optional[int] = None
        self.attempts: int = 0

    @abstractmethod
    async def handle(self) -> None:
        """
        Execute the job.
        This method must be implemented by all job classes.
        """
        pass

    async def failed(self, exception: Exception) -> None:
        """
        Handle a job failure.
        Override this method to perform cleanup when a job fails permanently.

        Args:
            exception: The exception that caused the job to fail
        """
        logger.error(
            f"Job {self.__class__.__name__} failed permanently: {str(exception)}"
        )

    def serialize(self) -> str:
        """
        Serialize the job to a JSON string for storage.

        Returns:
            JSON string representation of the job
        """
        job_data = {
            "class": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "data": self.get_data(),
            "max_tries": self.max_tries,
            "timeout": self.timeout,
            "retry_after": self.retry_after,
            "queue": self.queue,
        }
        return json.dumps(job_data)

    def get_data(self) -> Dict[str, Any]:
        """
        Get the serializable data for the job.
        Override this method to include custom data that needs to be serialized.

        Returns:
            Dictionary of data to be serialized
        """
        # Get all instance attributes except private ones and job metadata
        data = {}
        for key, value in self.__dict__.items():
            if not key.startswith("_") and key not in [
                "job_id",
                "attempts",
                "max_tries",
                "timeout",
                "retry_after",
                "queue",
            ]:
                data[key] = value
        return data

    @classmethod
    def unserialize(cls, payload: str) -> "Job":
        """
        Unserialize a job from a JSON string.

        Args:
            payload: JSON string representation of the job

        Returns:
            Job instance
        """
        job_data = json.loads(payload)

        # Import and instantiate the job class
        module_name, class_name = job_data["class"].rsplit(".", 1)
        module = __import__(module_name, fromlist=[class_name])
        job_class = getattr(module, class_name)

        # Create job instance
        job = job_class()

        # Restore job properties
        job.max_tries = job_data.get("max_tries", 3)
        job.timeout = job_data.get("timeout", 60)
        job.retry_after = job_data.get("retry_after", 0)
        job.queue = job_data.get("queue", "default")

        # Restore custom data
        data = job_data.get("data", {})
        for key, value in data.items():
            setattr(job, key, value)

        return job

    def __repr__(self):
        return f"<{self.__class__.__name__}(attempts={self.attempts}, max_tries={self.max_tries})>"
