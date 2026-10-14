from sqlalchemy import Column, String

from routemq.model import Model


class SmokeResult(Model):
    """Row written by the smoke job, keyed by the MQTT message ID."""

    __tablename__ = 'smoke_results'

    message_id = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)
    worker_hostname = Column(String(255), nullable=False)
