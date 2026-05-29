import json
import logging
import time
from typing import Any, Optional, Union, cast
from datetime import UTC, datetime

from routemq.queue.queue_driver import QueueDriver
from routemq.redis_manager import RedisManager
from routemq.model import Model
from routemq.queue.models import QueueFailedJob

logger = logging.getLogger('RouteMQ.RedisQueue')


class RedisQueue(QueueDriver):
    """
    Redis-backed queue driver using Redis lists and sorted sets.
    Provides fast, in-memory job storage with delayed job support.
    """

    def __init__(self):
        """Initialize the Redis queue driver."""
        self.redis = RedisManager()
        self.connection_name = 'redis'

    def _get_queue_key(self, queue: str) -> str:
        """Get the Redis key for a queue."""
        return f'routemq:queue:{queue}'

    def _get_delayed_key(self, queue: str) -> str:
        """Get the Redis key for delayed jobs in a queue."""
        return f'routemq:queue:{queue}:delayed'

    def _get_reserved_key(self, queue: str) -> str:
        """Get the Redis key for reserved jobs in a queue."""
        return f'routemq:queue:{queue}:reserved'

    def _get_worker_key(self, worker_id: str) -> str:
        """Get the Redis key for worker heartbeat metadata."""
        return f'routemq:queue:workers:{worker_id}'

    def _get_failed_key(self, queue: str) -> str:
        """Get the Redis key for failed jobs in a queue."""
        return f'routemq:queue:failed:{queue}'

    async def push(
        self,
        payload: str,
        queue: str = 'default',
        delay: int = 0,
    ) -> None:
        """Push a new job onto the queue."""
        if not self.redis.is_enabled():
            logger.error('Cannot push job to Redis queue - Redis is disabled')
            raise RuntimeError('Redis is disabled. Enable it to use RedisQueue.')

        client = cast(Any, self.redis.get_client())
        try:
            job_data = {
                'id': f'{queue}:{int(time.time() * 1000000)}',  # Unique ID with microseconds
                'payload': payload,
                'attempts': 0,
                'created_at': datetime.now(UTC).isoformat(),
            }
            job_json = json.dumps(job_data)

            if delay > 0:
                # Use sorted set for delayed jobs (score = available timestamp)
                available_at = time.time() + delay
                await client.zadd(self._get_delayed_key(queue), {job_json: available_at})
                logger.debug(f"Job pushed to delayed queue '{queue}' with {delay}s delay")
            else:
                # Use list for immediate jobs (FIFO)
                await client.rpush(self._get_queue_key(queue), job_json)
                logger.debug(f"Job pushed to queue '{queue}'")

        except Exception as e:
            logger.error(f'Failed to push job to Redis queue: {str(e)}')
            raise

    async def _migrate_delayed_jobs(self, queue: str) -> None:
        """Move delayed jobs that are now available to the main queue."""
        if not self.redis.is_enabled():
            return

        client = cast(Any, self.redis.get_client())
        try:
            delayed_key = self._get_delayed_key(queue)
            current_time = time.time()

            # Get all jobs that are now available (score <= current_time)
            available_jobs = await client.zrangebyscore(delayed_key, '-inf', current_time)

            if available_jobs:
                # Move jobs to main queue
                pipeline = client.pipeline()
                for job_json in available_jobs:
                    pipeline.rpush(self._get_queue_key(queue), job_json)
                    pipeline.zrem(delayed_key, job_json)
                await pipeline.execute()

                logger.debug(f"Migrated {len(available_jobs)} delayed jobs to queue '{queue}'")

        except Exception as e:
            logger.error(f'Failed to migrate delayed jobs: {str(e)}')
            # Audit Accept: best-effort delayed migration; the next poll retries migration.

    async def pop(self, queue: str = 'default') -> Optional[dict]:
        """Pop the next available job from the queue."""
        if not self.redis.is_enabled():
            logger.error('Cannot pop job from Redis queue - Redis is disabled')
            return None

        client = cast(Any, self.redis.get_client())
        try:
            # First, migrate any delayed jobs that are now available
            await self._migrate_delayed_jobs(queue)

            # Pop from main queue (FIFO) and move to reserved
            job_json = await client.rpoplpush(self._get_queue_key(queue), self._get_reserved_key(queue))

            if not job_json:
                return None

            job_data = json.loads(job_json)
            job_data['attempts'] += 1
            job_data['reserved_at'] = datetime.now(UTC).isoformat()

            # Update the reserved job with new attempt count
            updated_job_json = json.dumps(job_data)
            await client.lrem(self._get_reserved_key(queue), 1, job_json)
            await client.rpush(self._get_reserved_key(queue), updated_job_json)

            logger.debug(f"Job {job_data['id']} popped from queue '{queue}' (attempt {job_data['attempts']})")

            return {
                'id': job_data['id'],
                'payload': job_data['payload'],
                'attempts': job_data['attempts'],
            }

        except Exception as e:
            logger.error(f'Failed to pop job from Redis queue: {str(e)}')
            # Audit Accept: polling treats backend errors as no job after logging.
            return None

    async def release(
        self,
        job_id: Union[int, str],
        queue: str,
        delay: int = 0,
    ) -> None:
        """Release a job back to the queue for retry."""
        if not self.redis.is_enabled():
            logger.error('Cannot release job - Redis is disabled')
            return

        client = cast(Any, self.redis.get_client())
        try:
            reserved_key = self._get_reserved_key(queue)

            # Find the job in reserved list
            reserved_jobs = await client.lrange(reserved_key, 0, -1)
            job_json = None
            job_data: dict[str, Any] | None = None

            for reserved_job in reserved_jobs:
                candidate = json.loads(reserved_job)
                if candidate['id'] == job_id:
                    job_json = reserved_job
                    job_data = candidate
                    break

            if not job_json or job_data is None:
                logger.warning(f"Job {job_id} not found in reserved queue '{queue}'")
                return

            # Remove from reserved
            await client.lrem(reserved_key, 1, job_json)
            job_data.pop('reserved_at', None)
            job_json = json.dumps(job_data)

            # Add back to queue (with delay if specified)
            if delay > 0:
                available_at = time.time() + delay
                await client.zadd(self._get_delayed_key(queue), {job_json: available_at})
            else:
                await client.rpush(self._get_queue_key(queue), job_json)

            logger.debug(f"Job {job_id} released back to queue '{queue}' with delay {delay}s")

        except Exception as e:
            logger.error(f'Failed to release job: {str(e)}')
            raise

    async def reap_expired(self, queue: str = 'default', visibility_timeout: int = 300) -> int:
        """Return expired reserved jobs to the queue or fail exhausted ones."""
        if not self.redis.is_enabled():
            return 0

        client = cast(Any, self.redis.get_client())
        reserved_key = self._get_reserved_key(queue)
        now = datetime.now(UTC)
        reaped = 0
        try:
            reserved_jobs = await client.lrange(reserved_key, 0, -1)
            for job_json in reserved_jobs:
                job_data = json.loads(job_json)
                if not _reserved_job_expired(job_data, now, visibility_timeout):
                    continue

                await client.lrem(reserved_key, 1, job_json)
                payload = job_data.get('payload', '')
                max_tries = _payload_max_tries(payload)
                attempts = int(job_data.get('attempts', 0) or 0)
                if attempts >= max_tries:
                    await self.failed(
                        self.connection_name,
                        queue,
                        payload,
                        f'Job reservation expired after {visibility_timeout}s visibility timeout',
                    )
                else:
                    job_data.pop('reserved_at', None)
                    await client.rpush(self._get_queue_key(queue), json.dumps(job_data))
                reaped += 1
            return reaped
        except Exception as e:
            logger.error(f'Failed to reap expired Redis jobs: {str(e)}')
            raise

    async def delete(self, job_id: Union[int, str], queue: str) -> None:
        """Delete a job from the queue."""
        if not self.redis.is_enabled():
            logger.error('Cannot delete job - Redis is disabled')
            return

        client = cast(Any, self.redis.get_client())
        try:
            reserved_key = self._get_reserved_key(queue)

            # Find and remove the job from reserved list
            reserved_jobs = await client.lrange(reserved_key, 0, -1)

            for job_json in reserved_jobs:
                job_data = json.loads(job_json)
                if job_data['id'] == job_id:
                    await client.lrem(reserved_key, 1, job_json)
                    logger.debug(f"Job {job_id} deleted from queue '{queue}'")
                    return

            logger.warning(f"Job {job_id} not found in reserved queue '{queue}'")

        except Exception as e:
            logger.error(f'Failed to delete job: {str(e)}')
            raise

    async def heartbeat(self, job_id: Union[int, str], queue: str) -> bool:
        """Refresh the reservation timestamp for an active Redis job."""
        if not self.redis.is_enabled():
            return False

        client = cast(Any, self.redis.get_client())
        reserved_key = self._get_reserved_key(queue)
        reserved_jobs = await client.lrange(reserved_key, 0, -1)
        for job_json in reserved_jobs:
            job_data = json.loads(job_json)
            if job_data.get('id') != job_id:
                continue
            job_data['reserved_at'] = datetime.now(UTC).isoformat()
            await client.lrem(reserved_key, 1, job_json)
            await client.rpush(reserved_key, json.dumps(job_data))
            return True
        return False

    async def write_worker_heartbeat(self, heartbeat: dict[str, Any], ttl: int) -> None:
        """Persist worker heartbeat state in Redis with a TTL."""
        if not self.redis.is_enabled():
            return
        worker_id = str(heartbeat['worker_id'])
        key = self._get_worker_key(worker_id)
        client = cast(Any, self.redis.get_client())
        await client.hset(key, mapping={key: str(value) for key, value in heartbeat.items()})
        await client.expire(key, ttl)

    async def mark_worker_dead(self, worker_id: str) -> None:
        """Mark a worker heartbeat as dead."""
        if not self.redis.is_enabled():
            return
        client = cast(Any, self.redis.get_client())
        await client.hset(self._get_worker_key(worker_id), mapping={'state': 'dead'})

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
                session = cast(Any, await Model.get_session())
                try:
                    failed_job = QueueFailedJob(
                        connection=connection,
                        queue=queue,
                        payload=payload,
                        exception=exception,
                        failed_at=datetime.now(UTC),
                    )
                    session.add(failed_job)
                    await session.commit()
                    logger.info(f"Failed job stored in database for queue '{queue}'")
                finally:
                    await session.close()
            elif self.redis.is_enabled():
                # Fallback to Redis if database not available
                client = cast(Any, self.redis.get_client())
                failed_key = self._get_failed_key(queue)
                failed_data = {
                    'id': f'failed:{queue}:{int(time.time() * 1000000)}',
                    'connection': connection,
                    'queue': queue,
                    'payload': payload,
                    'exception': exception,
                    'failed_at': datetime.now(UTC).isoformat(),
                }
                await client.rpush(failed_key, json.dumps(failed_data))
                logger.info(f"Failed job stored in Redis for queue '{queue}'")
            else:
                logger.error('Cannot store failed job - both MySQL and Redis are disabled')

        except Exception as e:
            logger.error(f'Failed to store failed job: {str(e)}')
            # Audit Accept: failure persistence errors are logged; job retry/fail semantics stay unchanged.

    async def list_failed_jobs(self, queue: str | None = None) -> list[dict[str, Any]]:
        if not self.redis.is_enabled() or queue is None:
            return []
        client = cast(Any, self.redis.get_client())
        failed_jobs = await client.lrange(self._get_failed_key(queue), 0, -1)
        return [json.loads(job_json) for job_json in failed_jobs]

    async def get_failed_job(self, job_id: Union[int, str]) -> dict[str, Any] | None:
        queue = _failed_job_queue_from_id(str(job_id))
        if queue is None:
            return None
        for failed_job in await self.list_failed_jobs(queue):
            if str(failed_job.get('id')) == str(job_id):
                return failed_job
        return None

    async def retry_failed_job(self, job_id: Union[int, str]) -> bool:
        failed_job = await self.get_failed_job(job_id)
        if failed_job is None:
            return False
        await self.push(failed_job['payload'], failed_job.get('queue', 'default'))
        return await self.forget_failed_job(job_id)

    async def forget_failed_job(self, job_id: Union[int, str]) -> bool:
        queue = _failed_job_queue_from_id(str(job_id))
        if queue is None or not self.redis.is_enabled():
            return False
        client = cast(Any, self.redis.get_client())
        for failed_job_json in await client.lrange(self._get_failed_key(queue), 0, -1):
            failed_job = json.loads(failed_job_json)
            if str(failed_job.get('id')) == str(job_id):
                removed = await client.lrem(self._get_failed_key(queue), 1, failed_job_json)
                return bool(removed)
        return False

    async def flush_failed_jobs(self, queue: str | None = None) -> int:
        if queue is None or not self.redis.is_enabled():
            return 0
        client = cast(Any, self.redis.get_client())
        deleted = await client.delete(self._get_failed_key(queue))
        return int(deleted or 0)

    async def size(self, queue: str = 'default') -> int:
        """Get the size of the queue."""
        if not self.redis.is_enabled():
            logger.error('Cannot get queue size - Redis is disabled')
            return 0

        client = cast(Any, self.redis.get_client())
        try:
            # Count jobs in main queue
            main_count = await client.llen(self._get_queue_key(queue))

            # Count delayed jobs
            delayed_count = await client.zcard(self._get_delayed_key(queue))

            return main_count + delayed_count

        except Exception as e:
            logger.error(f'Failed to get queue size: {str(e)}')
            # Audit Accept: queue depth is advisory and must not break callers.
            return 0

    async def stats(self, queue: str = 'default') -> dict[str, Any]:
        """Return ready/reserved/delayed/failed queue depth statistics."""
        empty_stats = _empty_queue_stats(queue)
        if not self.redis.is_enabled():
            return empty_stats

        client = cast(Any, self.redis.get_client())
        try:
            ready_count = int(await client.llen(self._get_queue_key(queue)) or 0)
            reserved_count = int(await client.llen(self._get_reserved_key(queue)) or 0)
            delayed_count = int(await client.zcard(self._get_delayed_key(queue)) or 0)
            failed_count = int(await client.llen(self._get_failed_key(queue)) or 0)
            oldest_ready_age = await self._oldest_ready_age_seconds(client, queue)
            return {
                'queue': queue,
                'ready': ready_count,
                'reserved': reserved_count,
                'delayed': delayed_count,
                'failed': failed_count,
                'oldest_ready_age_seconds': oldest_ready_age,
            }
        except Exception as e:
            logger.error(f'Failed to get Redis queue stats: {str(e)}')
            return empty_stats

    async def _oldest_ready_age_seconds(self, client: Any, queue: str) -> float:
        job_json = await client.lindex(self._get_queue_key(queue), 0)
        if not job_json:
            return 0.0
        try:
            job_data = json.loads(job_json)
        except (TypeError, json.JSONDecodeError):
            return 0.0
        created_at = job_data.get('created_at') or _created_at_from_redis_job_id(str(job_data.get('id', '')))
        if not created_at:
            return 0.0
        try:
            created_at_dt = datetime.fromisoformat(str(created_at))
        except ValueError:
            return 0.0
        if created_at_dt.tzinfo is None:
            created_at_dt = created_at_dt.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - created_at_dt).total_seconds())


def _payload_max_tries(payload: str, default: int = 3) -> int:
    try:
        value = json.loads(payload).get('max_tries', default)
        return max(1, int(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _reserved_job_expired(job_data: dict[str, Any], now: datetime, visibility_timeout: int) -> bool:
    reserved_at = job_data.get('reserved_at')
    if not reserved_at:
        return True
    try:
        reserved_at_dt = datetime.fromisoformat(str(reserved_at))
    except ValueError:
        return True
    if reserved_at_dt.tzinfo is None:
        reserved_at_dt = reserved_at_dt.replace(tzinfo=UTC)
    return (now - reserved_at_dt).total_seconds() >= visibility_timeout


def _failed_job_queue_from_id(job_id: str) -> str | None:
    parts = job_id.split(':', 2)
    if len(parts) == 3 and parts[0] == 'failed' and parts[1]:
        return parts[1]
    return None


def _created_at_from_redis_job_id(job_id: str) -> str | None:
    try:
        _queue, timestamp = job_id.rsplit(':', 1)
        seconds = int(timestamp) / 1_000_000
    except (ValueError, TypeError):
        return None
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat()


def _empty_queue_stats(queue: str) -> dict[str, Any]:
    return {
        'queue': queue,
        'ready': 0,
        'reserved': 0,
        'delayed': 0,
        'failed': 0,
        'oldest_ready_age_seconds': 0.0,
    }
