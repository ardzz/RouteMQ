import unittest
from datetime import datetime

from routemq.queue.models import QueueFailedJob, QueueJob


class TestQueueJobRepr(unittest.TestCase):
    def test_queue_job_repr(self) -> None:
        available_at = datetime(2026, 5, 27, 12, 0, 0)
        job = QueueJob(queue='default', payload='payload', attempts=2, available_at=available_at)

        r = repr(job)

        self.assertIn('QueueJob', r)
        self.assertIn("queue='default'", r)
        self.assertIn('attempts=2', r)


class TestQueueFailedJobRepr(unittest.TestCase):
    def test_queue_failed_job_repr(self) -> None:
        failed_at = datetime(2026, 5, 27, 12, 0, 0)
        job = QueueFailedJob(
            connection='redis',
            queue='critical',
            payload='payload',
            exception='RuntimeError: boom',
            failed_at=failed_at,
        )

        r = repr(job)

        self.assertIn('QueueFailedJob', r)
        self.assertIn("queue='critical'", r)
        self.assertIn('failed_at=', r)


if __name__ == '__main__':
    unittest.main()
