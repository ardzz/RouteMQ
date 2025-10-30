import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.queue.queue_driver import QueueDriver
from core.model import Model
from app.models.queue_job import QueueJob
from app.models.queue_failed_job import QueueFailedJob

logger = logging.getLogger("RouteMQ.DatabaseQueue")


class DatabaseQueue(QueueDriver):
    """
    Database-backed queue driver using MySQL/SQLAlchemy.
    Provides persistent job storage with ACID guarantees.
    """

    def __init__(self):
        """Initialize the database queue driver."""
        self.connection_name = "database"

    async def push(
        self,
        payload: str,
        queue: str = "default",
        delay: int = 0,
    ) -> None:
        """Push a new job onto the queue."""
        if not Model._is_enabled:
            logger.error("Cannot push job to database queue - MySQL is disabled")
            raise RuntimeError("MySQL is disabled. Enable it to use DatabaseQueue.")

        session: AsyncSession = await Model.get_session()
        try:
            available_at = datetime.utcnow()
            if delay > 0:
                available_at += timedelta(seconds=delay)

            job = QueueJob(
                queue=queue,
                payload=payload,
                attempts=0,
                available_at=available_at,
                created_at=datetime.utcnow(),
            )

            session.add(job)
            await session.commit()
            logger.debug(f"Job pushed to queue '{queue}' with delay {delay}s")

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to push job to queue: {str(e)}")
            raise
        finally:
            await session.close()

    async def pop(self, queue: str = "default") -> Optional[dict]:
        """Pop the next available job from the queue."""
        if not Model._is_enabled:
            logger.error("Cannot pop job from database queue - MySQL is disabled")
            return None

        session: AsyncSession = await Model.get_session()
        try:
            # Use FOR UPDATE SKIP LOCKED for concurrency-safe job claiming
            # Find the next available job that's not reserved
            stmt = (
                select(QueueJob)
                .where(
                    QueueJob.queue == queue,
                    QueueJob.reserved_at.is_(None),
                    QueueJob.available_at <= datetime.utcnow(),
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
            job.reserved_at = datetime.utcnow()
            job.attempts += 1

            await session.commit()
            await session.refresh(job)

            logger.debug(
                f"Job {job.id} popped from queue '{queue}' (attempt {job.attempts})"
            )

            return {
                "id": job.id,
                "payload": job.payload,
                "attempts": job.attempts,
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to pop job from queue: {str(e)}")
            return None
        finally:
            await session.close()

    async def release(
        self,
        job_id: int,
        queue: str,
        delay: int = 0,
    ) -> None:
        """Release a job back to the queue for retry."""
        if not Model._is_enabled:
            logger.error("Cannot release job - MySQL is disabled")
            return

        session: AsyncSession = await Model.get_session()
        try:
            available_at = datetime.utcnow()
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
            logger.error(f"Failed to release job: {str(e)}")
            raise
        finally:
            await session.close()

    async def delete(self, job_id: int, queue: str) -> None:
        """Delete a job from the queue."""
        if not Model._is_enabled:
            logger.error("Cannot delete job - MySQL is disabled")
            return

        session: AsyncSession = await Model.get_session()
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
            logger.error(f"Failed to delete job: {str(e)}")
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
            logger.error("Cannot store failed job - MySQL is disabled")
            return

        session: AsyncSession = await Model.get_session()
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
            logger.info(f"Failed job stored for queue '{queue}'")

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to store failed job: {str(e)}")
            raise
        finally:
            await session.close()

    async def size(self, queue: str = "default") -> int:
        """Get the size of the queue."""
        if not Model._is_enabled:
            logger.error("Cannot get queue size - MySQL is disabled")
            return 0

        session: AsyncSession = await Model.get_session()
        try:
            stmt = select(QueueJob).where(
                QueueJob.queue == queue,
                QueueJob.reserved_at.is_(None),
            )

            result = await session.execute(stmt)
            jobs = result.scalars().all()
            return len(jobs)

        except Exception as e:
            logger.error(f"Failed to get queue size: {str(e)}")
            return 0
        finally:
            await session.close()
