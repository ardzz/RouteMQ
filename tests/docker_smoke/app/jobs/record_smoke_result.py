import socket

from app.models.smoke_result import SmokeResult
from routemq.job import Job
from routemq.model import Model


@Job.register
class RecordSmokeResultJob(Job):
    """Store a smoke message together with the hostname of the queue worker that handled it."""

    def __init__(self):
        super().__init__()
        self.message_id = None
        self.value = None

    async def handle(self) -> None:
        stored = await Model.create(
            SmokeResult,
            message_id=self.message_id,
            value=self.value,
            worker_hostname=socket.gethostname(),
        )
        if stored is None:
            raise RuntimeError('Database integration is disabled; the smoke result was not stored')
