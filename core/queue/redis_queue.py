import json
import logging
import time
from typing import Optional
from datetime import datetime

from core.queue.queue_driver import QueueDriver
from core.redis_manager import RedisManager
from core.model import Model
from app.models.queue_failed_job import QueueFailedJob

logger = logging.getLogger("RouteMQ.RedisQueue")


class RedisQueue(QueueDriver):
    """
    Redis-backed queue driver using Redis lists and sorted sets.
    Provides fast, in-memory job storage with delayed job support.
    """

    def __init__(self):
        """Initialize the Redis queue driver."""
        self.redis = RedisManager()
        self.connection_name = "redis"

    def _get_queue_key(self, queue: str) -> str:
        """Get the Redis key for a queue."""
        return f"routemq:queue:{queue}"

    def _get_delayed_key(self, queue: str) -> str:
        """Get the Redis key for delayed jobs in a queue."""
        return f"routemq:queue:{queue}:delayed"

    def _get_reserved_key(self, queue: str) -> str:
        """Get the Redis key for reserved jobs in a queue."""
        return f"routemq:queue:{queue}:reserved"

    async def push(
        self,
        payload: str,
        queue: str = "default",
        delay: int = 0,
    ) -> None:
        """Push a new job onto the queue."""
        if not self.redis.is_enabled():
            logger.error("Cannot push job to Redis queue - Redis is disabled")
            raise RuntimeError("Redis is disabled. Enable it to use RedisQueue.")

        client = self.redis.get_client()
        try:
            job_data = {
                "id": f"{queue}:{int(time.time() * 1000000)}",  # Unique ID with microseconds
                "payload": payload,
                "attempts": 0,
            }
            job_json = json.dumps(job_data)

            if delay > 0:
                # Use sorted set for delayed jobs (score = available timestamp)
                available_at = time.time() + delay
                await client.zadd(
                    self._get_delayed_key(queue),
                    {job_json: available_at}
                )
                logger.debug(f"Job pushed to delayed queue '{queue}' with {delay}s delay")
            else:
                # Use list for immediate jobs (FIFO)
                await client.rpush(self._get_queue_key(queue), job_json)
                logger.debug(f"Job pushed to queue '{queue}'")

        except Exception as e:
            logger.error(f"Failed to push job to Redis queue: {str(e)}")
            raise

    async def _migrate_delayed_jobs(self, queue: str) -> None:
        """Move delayed jobs that are now available to the main queue."""
        if not self.redis.is_enabled():
            return

        client = self.redis.get_client()
        try:
            delayed_key = self._get_delayed_key(queue)
            current_time = time.time()

            # Get all jobs that are now available (score <= current_time)
            available_jobs = await client.zrangebyscore(
                delayed_key,
                "-inf",
                current_time
            )

            if available_jobs:
                # Move jobs to main queue
                pipeline = client.pipeline()
                for job_json in available_jobs:
                    pipeline.rpush(self._get_queue_key(queue), job_json)
                    pipeline.zrem(delayed_key, job_json)
                await pipeline.execute()

                logger.debug(f"Migrated {len(available_jobs)} delayed jobs to queue '{queue}'")

        except Exception as e:
            logger.error(f"Failed to migrate delayed jobs: {str(e)}")

    async def pop(self, queue: str = "default") -> Optional[dict]:
        """Pop the next available job from the queue."""
        if not self.redis.is_enabled():
            logger.error("Cannot pop job from Redis queue - Redis is disabled")
            return None

        client = self.redis.get_client()
        try:
            # First, migrate any delayed jobs that are now available
            await self._migrate_delayed_jobs(queue)

            # Pop from main queue (FIFO) and move to reserved
            job_json = await client.rpoplpush(
                self._get_queue_key(queue),
                self._get_reserved_key(queue)
            )

            if not job_json:
                return None

            job_data = json.loads(job_json)
            job_data["attempts"] += 1

            # Update the reserved job with new attempt count
            updated_job_json = json.dumps(job_data)
            await client.lrem(self._get_reserved_key(queue), 1, job_json)
            await client.rpush(self._get_reserved_key(queue), updated_job_json)

            logger.debug(
                f"Job {job_data['id']} popped from queue '{queue}' (attempt {job_data['attempts']})"
            )

            return job_data

        except Exception as e:
            logger.error(f"Failed to pop job from Redis queue: {str(e)}")
            return None

    async def release(
        self,
        job_id: str,
        queue: str,
        delay: int = 0,
    ) -> None:
        """Release a job back to the queue for retry."""
        if not self.redis.is_enabled():
            logger.error("Cannot release job - Redis is disabled")
            return

        client = self.redis.get_client()
        try:
            reserved_key = self._get_reserved_key(queue)

            # Find the job in reserved list
            reserved_jobs = await client.lrange(reserved_key, 0, -1)
            job_json = None

            for reserved_job in reserved_jobs:
                job_data = json.loads(reserved_job)
                if job_data["id"] == job_id:
                    job_json = reserved_job
                    break

            if not job_json:
                logger.warning(f"Job {job_id} not found in reserved queue '{queue}'")
                return

            # Remove from reserved
            await client.lrem(reserved_key, 1, job_json)

            # Add back to queue (with delay if specified)
            if delay > 0:
                available_at = time.time() + delay
                await client.zadd(
                    self._get_delayed_key(queue),
                    {job_json: available_at}
                )
            else:
                await client.rpush(self._get_queue_key(queue), job_json)

            logger.debug(f"Job {job_id} released back to queue '{queue}' with delay {delay}s")

        except Exception as e:
            logger.error(f"Failed to release job: {str(e)}")
            raise

    async def delete(self, job_id: str, queue: str) -> None:
        """Delete a job from the queue."""
        if not self.redis.is_enabled():
            logger.error("Cannot delete job - Redis is disabled")
            return

        client = self.redis.get_client()
        try:
            reserved_key = self._get_reserved_key(queue)

            # Find and remove the job from reserved list
            reserved_jobs = await client.lrange(reserved_key, 0, -1)

            for job_json in reserved_jobs:
                job_data = json.loads(job_json)
                if job_data["id"] == job_id:
                    await client.lrem(reserved_key, 1, job_json)
                    logger.debug(f"Job {job_id} deleted from queue '{queue}'")
                    return

            logger.warning(f"Job {job_id} not found in reserved queue '{queue}'")

        except Exception as e:
            logger.error(f"Failed to delete job: {str(e)}")
            raise

    async def failed(
        self,
        connection: str,
        queue: str,
        payload: str,
        exception: str,
    ) -> None:
        """
        Store a failed job.
        If MySQL is enabled, store in database. Otherwise, store in Redis.
        """
        try:
            if Model._is_enabled:
                # Store in database
                session = await Model.get_session()
                try:
                    failed_job = QueueFailedJob(
                        connection=connection,
                        queue=queue,
                        payload=payload,
                        exception=exception,
                        failed_at=datetime.utcnow(),
                    )
                    session.add(failed_job)
                    await session.commit()
                    logger.info(f"Failed job stored in database for queue '{queue}'")
                finally:
                    await session.close()
            elif self.redis.is_enabled():
                # Fallback to Redis if database not available
                client = self.redis.get_client()
                failed_key = f"routemq:queue:failed:{queue}"
                failed_data = {
                    "connection": connection,
                    "queue": queue,
                    "payload": payload,
                    "exception": exception,
                    "failed_at": datetime.utcnow().isoformat(),
                }
                await client.rpush(failed_key, json.dumps(failed_data))
                logger.info(f"Failed job stored in Redis for queue '{queue}'")
            else:
                logger.error("Cannot store failed job - both MySQL and Redis are disabled")

        except Exception as e:
            logger.error(f"Failed to store failed job: {str(e)}")

    async def size(self, queue: str = "default") -> int:
        """Get the size of the queue."""
        if not self.redis.is_enabled():
            logger.error("Cannot get queue size - Redis is disabled")
            return 0

        client = self.redis.get_client()
        try:
            # Count jobs in main queue
            main_count = await client.llen(self._get_queue_key(queue))

            # Count delayed jobs
            delayed_count = await client.zcard(self._get_delayed_key(queue))

            return main_count + delayed_count

        except Exception as e:
            logger.error(f"Failed to get queue size: {str(e)}")
            return 0
