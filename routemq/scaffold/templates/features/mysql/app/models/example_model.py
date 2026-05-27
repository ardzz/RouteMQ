from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from routemq.model import Model


class ExampleDevice(Model):
    """Example SQLAlchemy model for a device."""

    __tablename__ = 'example_devices'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default='online')
