from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index

from core.model import Model


class QueueJob(Model):
    """Model for queue_jobs table - stores pending and reserved jobs."""

    __tablename__ = 'queue_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    queue = Column(String(255), nullable=False, index=True, default='default')
    payload = Column(Text, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    reserved_at = Column(DateTime, nullable=True)
    available_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index('queue_jobs_queue_reserved_at_index', 'queue', 'reserved_at'),)

    def __repr__(self):
        return f"<QueueJob(id={self.id}, queue='{self.queue}', attempts={self.attempts})>"


class QueueFailedJob(Model):
    """Model for queue_failed_jobs table - stores jobs that failed permanently."""

    __tablename__ = 'queue_failed_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection = Column(String(255), nullable=False)
    queue = Column(String(255), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    exception = Column(Text, nullable=False)
    failed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<QueueFailedJob(id={self.id}, queue='{self.queue}', failed_at='{self.failed_at}')>"
