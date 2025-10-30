from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from core.model import Base


class QueueJob(Base):
    """Model for queue_jobs table - stores pending and reserved jobs."""

    __tablename__ = "queue_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    queue = Column(String(255), nullable=False, index=True, default="default")
    payload = Column(Text, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    reserved_at = Column(DateTime, nullable=True)
    available_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Composite index for efficient job fetching
    __table_args__ = (
        Index('queue_jobs_queue_reserved_at_index', 'queue', 'reserved_at'),
    )

    def __repr__(self):
        return f"<QueueJob(id={self.id}, queue='{self.queue}', attempts={self.attempts})>"
