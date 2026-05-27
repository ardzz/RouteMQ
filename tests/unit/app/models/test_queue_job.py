import unittest

from sqlalchemy import DateTime, Integer, String, Text

from app.models.queue_job import QueueJob
from routemq.model import Model
from routemq.queue.models import QueueJob as CoreQueueJob


class TestAppQueueJobModel(unittest.TestCase):
    def test_app_wrapper_reexports_core_queue_job(self) -> None:
        """Legacy app import remains the same mapped QueueJob class."""
        self.assertIs(QueueJob, CoreQueueJob)

    def test_queue_job_inherits_model_base(self) -> None:
        """QueueJob remains wired into the shared SQLAlchemy Model base."""
        self.assertTrue(issubclass(QueueJob, Model))

    def test_queue_job_table_name_is_stable(self) -> None:
        """Database driver depends on the queue_jobs table name."""
        self.assertEqual(QueueJob.__tablename__, 'queue_jobs')

    def test_queue_job_declares_expected_columns(self) -> None:
        """Pending-job schema keeps every worker-facing column."""
        self.assertEqual(set(QueueJob.__table__.columns.keys()), EXPECTED_QUEUE_JOB_COLUMNS)

    def test_queue_job_required_columns_are_not_nullable(self) -> None:
        """Required queue fields stay non-null for database workers."""
        required = {'queue', 'payload', 'attempts', 'available_at', 'created_at'}

        self.assertEqual({name for name in required if not QueueJob.__table__.columns[name].nullable}, required)

    def test_queue_job_reserved_at_is_optional(self) -> None:
        """Unreserved jobs keep reserved_at nullable."""
        self.assertTrue(QueueJob.__table__.columns['reserved_at'].nullable)

    def test_queue_job_column_types_match_contract(self) -> None:
        """Column SQL types remain compatible with serialized jobs."""
        columns = QueueJob.__table__.columns

        self.assertIsInstance(columns['payload'].type, Text)
        self.assertIsInstance(columns['attempts'].type, Integer)
        self.assertIsInstance(columns['queue'].type, String)
        self.assertIsInstance(columns['available_at'].type, DateTime)


EXPECTED_QUEUE_JOB_COLUMNS = {'id', 'queue', 'payload', 'attempts', 'reserved_at', 'available_at', 'created_at'}


if __name__ == '__main__':
    unittest.main()
