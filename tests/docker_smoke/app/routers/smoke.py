from app.jobs.record_smoke_result import RecordSmokeResultJob
from routemq.queue.queue_manager import dispatch
from routemq.router import Router

router = Router()


async def record_message(message_id: str, payload, client) -> None:
    job = RecordSmokeResultJob()
    job.message_id = message_id
    job.value = payload['value']
    await dispatch(job)


router.on('routemq-smoke/messages/{message_id}', record_message, qos=1)
