from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from core.model import Base


class QueueFailedJob(Base):
    """Model for queue_failed_jobs table - stores jobs that failed permanently."""

    __tablename__ = "queue_failed_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection = Column(String(255), nullable=False)
    queue = Column(String(255), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    exception = Column(Text, nullable=False)
    failed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<QueueFailedJob(id={self.id}, queue='{self.queue}', failed_at='{self.failed_at}')>"
