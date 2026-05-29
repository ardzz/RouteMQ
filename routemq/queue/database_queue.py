import logging
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Optional, Union, cast
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from routemq.queue.queue_driver import QueueDriver
from routemq.model import Model
from routemq.queue.models import QueueJob, QueueFailedJob

logger = logging.getLogger('RouteMQ.DatabaseQueue')


class DatabaseQueue(QueueDriver):
    """
    Database-backed queue driver using MySQL/SQLAlchemy.
    Provides persistent job storage with ACID guarantees.
    """

    def __init__(self):
        """Initialize the database queue driver."""
        self.connection_name = 'database'

    async def push(
        self,
        payload: str,
        queue: str = 'default',
        delay: int = 0,
    ) -> None:
        """Push a new job onto the queue."""
        if not Model._is_enabled:
            logger.error('Cannot push job to database queue - MySQL is disabled')
            raise RuntimeError('MySQL is disabled. Enable it to use DatabaseQueue.')

        session = cast(AsyncSession, await Model.get_session())
        try:
            available_at = datetime.now(UTC)
            if delay > 0:
                available_at += timedelta(seconds=delay)

            job = QueueJob(
                queue=queue,
                payload=payload,
                attempts=0,
                available_at=available_at,
                created_at=datetime.now(UTC),
            )

            session.add(job)
            await session.commit()
            logger.debug(f"Job pushed to queue '{queue}' with delay {delay}s")

        except Exception as e:
            await session.rollback()
            logger.error(f'Failed to push job to queue: {str(e)}')
            raise
        finally:
            await session.close()

    async def pop(self, queue: str = 'default') -> Optional[dict]:
        """Pop the next available job from the queue."""
        if not Model._is_enabled:
            logger.error('Cannot pop job from database queue - MySQL is disabled')
            return None

        session = cast(AsyncSession, await Model.get_session())
        try:
            # Use FOR UPDATE SKIP LOCKED for concurrency-safe job claiming
            # Find the next available job that's not reserved
            stmt = (
                select(QueueJob)
                .where(
                    QueueJob.queue == queue,
                    QueueJob.reserved_at.is_(None),
                    QueueJob.available_at <= datetime.now(UTC),
                )
                .order_by(QueueJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )

            result = await session.execute(stmt)
            job = result.scalars().first()

            if not job:
                return None

            # Mark job as reserved
            job_record = cast(Any, job)
            job_record.reserved_at = datetime.now(UTC)
            job_record.attempts += 1

            await session.commit()
            await session.refresh(job)

            logger.debug(f"Job {job.id} popped from queue '{queue}' (attempt {job.attempts})")

            return {
                'id': job.id,
                'payload': job.payload,
                'attempts': job.attempts,
            }

        except Exception as e:
            await session.rollback()
            logger.error(f'Failed to pop job from queue: {str(e)}')
            # Audit Accept: polling treats backend errors as no job after logging.
            return None
        finally:
            await session.close()

    async def release(
        self,
        job_id: Union[int, str],
        queue: str,
        delay: int = 0,
    ) -> None:
        """Release a job back to the queue for retry."""
        if not Model._is_enabled:
            logger.error('Cannot release job - MySQL is disabled')
            return

        session = cast(AsyncSession, await Model.get_session())
        try:
            available_at = datetime.now(UTC)
            if delay > 0:
                available_at += timedelta(seconds=delay)

            stmt = (
                update(QueueJob)
                .where(QueueJob.id == job_id, QueueJob.queue == queue)
                .values(reserved_at=None, available_at=available_at)
            )

            await session.execute(stmt)
            await session.commit()
            logger.debug(f"Job {job_id} released back to queue '{queue}' with delay {delay}s")

        except Exception as e:
            await session.rollback()
            logger.error(f'Failed to release job: {str(e)}')
            raise
        finally:
            await session.close()

    async def delete(self, job_id: Union[int, str], queue: str) -> None:
        """Delete a job from the queue."""
        if not Model._is_enabled:
            logger.error('Cannot delete job - MySQL is disabled')
            return

        session = cast(AsyncSession, await Model.get_session())
        try:
            stmt = delete(QueueJob).where(
                QueueJob.id == job_id,
                QueueJob.queue == queue,
            )

            await session.execute(stmt)
            await session.commit()
            logger.debug(f"Job {job_id} deleted from queue '{queue}'")

        except Exception as e:
            await session.rollback()
            logger.error(f'Failed to delete job: {str(e)}')
            raise
        finally:
            await session.close()

    async def heartbeat(self, job_id: Union[int, str], queue: str) -> bool:
        """Refresh the reserved_at timestamp for an active database job."""
        if not Model._is_enabled:
            return False

        session = cast(AsyncSession, await Model.get_session())
        try:
            stmt = (
                update(QueueJob)
                .where(QueueJob.id == job_id, QueueJob.queue == queue, QueueJob.reserved_at.is_not(None))
                .values(reserved_at=datetime.now(UTC))
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(getattr(result, 'rowcount', 0))
        except Exception as e:
            await session.rollback()
            logger.error(f'Failed to refresh job heartbeat: {str(e)}')
            raise
        finally:
            await session.close()

    async def failed(
        self,
        connection: str,
        queue: str,
        payload: str,
        exception: str,
    ) -> None:
        """Store a failed job."""
        if not Model._is_enabled:
            logger.error('Cannot store failed job - MySQL is disabled')
            return

        session = cast(AsyncSession, await Model.get_session())
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
            logger.info(f"Failed job stored for queue '{queue}'")

        except Exception as e:
            await session.rollback()
            logger.error(f'Failed to store failed job: {str(e)}')
            raise
        finally:
            await session.close()

    async def list_failed_jobs(self, queue: str | None = None) -> list[dict[str, Any]]:
        if not Model._is_enabled:
            return []
        session = cast(AsyncSession, await Model.get_session())
        try:
            stmt = select(QueueFailedJob).order_by(QueueFailedJob.id)
            if queue is not None:
                stmt = stmt.where(QueueFailedJob.queue == queue)
            result = await session.execute(stmt)
            return [_failed_job_to_dict(job) for job in result.scalars().all()]
        finally:
            await session.close()

    async def get_failed_job(self, job_id: Union[int, str]) -> dict[str, Any] | None:
        job = await self._get_failed_job_model(job_id)
        return _failed_job_to_dict(job) if job is not None else None

    async def retry_failed_job(self, job_id: Union[int, str]) -> bool:
        job = await self._get_failed_job_model(job_id)
        if job is None:
            return False
        failed_job = cast(Any, job)
        await self.push(str(failed_job.payload), str(failed_job.queue))
        return await self.forget_failed_job(job_id)

    async def forget_failed_job(self, job_id: Union[int, str]) -> bool:
        if not Model._is_enabled:
            return False
        session = cast(AsyncSession, await Model.get_session())
        try:
            result = await session.execute(select(QueueFailedJob).where(QueueFailedJob.id == int(job_id)))
            job = result.scalars().first()
            if job is None:
                return False
            await session.delete(job)
            await session.commit()
            return True
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def flush_failed_jobs(self, queue: str | None = None) -> int:
        if not Model._is_enabled:
            return 0
        session = cast(AsyncSession, await Model.get_session())
        try:
            stmt = delete(QueueFailedJob)
            if queue is not None:
                stmt = stmt.where(QueueFailedJob.queue == queue)
            result = await session.execute(stmt)
            await session.commit()
            rowcount = getattr(result, 'rowcount', 0)
            return int(rowcount or 0)
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def _get_failed_job_model(self, job_id: Union[int, str]):
        if not Model._is_enabled:
            return None
        session = cast(AsyncSession, await Model.get_session())
        try:
            result = await session.execute(select(QueueFailedJob).where(QueueFailedJob.id == int(job_id)))
            return result.scalars().first()
        finally:
            await session.close()

    async def reap_expired(self, queue: str = 'default', visibility_timeout: int = 300) -> int:
        """Return stale reserved jobs to the queue or move exhausted ones to failed jobs."""
        if not Model._is_enabled:
            logger.error('Cannot reap expired jobs - MySQL is disabled')
            return 0

        session = cast(AsyncSession, await Model.get_session())
        try:
            now = datetime.now(UTC)
            cutoff = now - timedelta(seconds=visibility_timeout)
            stmt = (
                select(QueueJob)
                .where(
                    QueueJob.queue == queue,
                    QueueJob.reserved_at.is_not(None),
                    QueueJob.reserved_at < cutoff,
                )
                .order_by(QueueJob.id)
            )
            result = await session.execute(stmt)
            jobs = result.scalars().all()
            for job in jobs:
                job_record = cast(Any, job)
                max_tries = _payload_max_tries(str(job_record.payload))
                attempts = int(getattr(job_record, 'attempts', 0) or 0)
                if attempts >= max_tries:
                    failed_job = QueueFailedJob(
                        connection=self.connection_name,
                        queue=queue,
                        payload=str(job_record.payload),
                        exception=f'Job reservation expired after {visibility_timeout}s visibility timeout',
                        failed_at=now,
                    )
                    session.add(failed_job)
                    await session.delete(job)
                else:
                    job_record.reserved_at = None
                    job_record.available_at = now

            await session.commit()
            return len(jobs)

        except Exception as e:
            await session.rollback()
            logger.error(f'Failed to reap expired database jobs: {str(e)}')
            raise
        finally:
            await session.close()

    async def size(self, queue: str = 'default') -> int:
        """Get the size of the queue."""
        if not Model._is_enabled:
            logger.error('Cannot get queue size - MySQL is disabled')
            return 0

        session = cast(AsyncSession, await Model.get_session())
        try:
            stmt = select(QueueJob).where(
                QueueJob.queue == queue,
                QueueJob.reserved_at.is_(None),
            )

            result = await session.execute(stmt)
            jobs = result.scalars().all()
            return len(jobs)

        except Exception as e:
            logger.error(f'Failed to get queue size: {str(e)}')
            # Audit Accept: queue depth is advisory and must not break callers.
            return 0
        finally:
            await session.close()

    async def stats(self, queue: str = 'default') -> dict[str, Any]:
        """Return ready/reserved/delayed/failed queue depth statistics."""
        empty_stats = _empty_queue_stats(queue)
        if not Model._is_enabled:
            logger.error('Cannot get queue stats - MySQL is disabled')
            return empty_stats

        session = cast(AsyncSession, await Model.get_session())
        try:
            now = datetime.now(UTC)
            jobs_result = await session.execute(select(QueueJob).where(QueueJob.queue == queue))
            jobs = cast(list[Any], list(jobs_result.scalars().all()))
            failed_result = await session.execute(select(QueueFailedJob).where(QueueFailedJob.queue == queue))
            failed_jobs = cast(list[Any], list(failed_result.scalars().all()))

            ready_jobs = [job for job in jobs if job.reserved_at is None and _as_utc(job.available_at) <= now]
            delayed_jobs = [job for job in jobs if job.reserved_at is None and _as_utc(job.available_at) > now]
            reserved_jobs = [job for job in jobs if job.reserved_at is not None]
            oldest_ready_age = _oldest_ready_age_seconds(ready_jobs, now)
            return {
                'queue': queue,
                'ready': len(ready_jobs),
                'reserved': len(reserved_jobs),
                'delayed': len(delayed_jobs),
                'failed': len(failed_jobs),
                'oldest_ready_age_seconds': oldest_ready_age,
            }
        except Exception as e:
            logger.error(f'Failed to get queue stats: {str(e)}')
            return empty_stats
        finally:
            await session.close()


def _payload_max_tries(payload: str, default: int = 3) -> int:
    try:
        value = json.loads(payload).get('max_tries', default)
        return max(1, int(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _failed_job_to_dict(job) -> dict[str, Any]:
    return {
        'id': job.id,
        'connection': job.connection,
        'queue': job.queue,
        'payload': job.payload,
        'exception': job.exception,
        'failed_at': job.failed_at.isoformat() if hasattr(job.failed_at, 'isoformat') else str(job.failed_at),
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _oldest_ready_age_seconds(jobs: list[Any], now: datetime) -> float:
    if not jobs:
        return 0.0
    oldest = min(_as_utc(getattr(job, 'created_at', None) or job.available_at) for job in jobs)
    return max(0.0, (now - oldest).total_seconds())


def _empty_queue_stats(queue: str) -> dict[str, Any]:
    return {
        'queue': queue,
        'ready': 0,
        'reserved': 0,
        'delayed': 0,
        'failed': 0,
        'oldest_ready_age_seconds': 0.0,
    }
