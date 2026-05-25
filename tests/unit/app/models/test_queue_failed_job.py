import unittest

from sqlalchemy import DateTime, Integer, String, Text

from app.models.queue_failed_job import QueueFailedJob
from core.model import Model
from core.queue.models import QueueFailedJob as CoreQueueFailedJob


class TestAppQueueFailedJobModel(unittest.TestCase):
    def test_app_wrapper_reexports_core_failed_job(self) -> None:
        """Legacy app import remains the same mapped QueueFailedJob class."""
        self.assertIs(QueueFailedJob, CoreQueueFailedJob)

    def test_failed_job_inherits_model_base(self) -> None:
        """QueueFailedJob remains wired into the shared SQLAlchemy Model base."""
        self.assertTrue(issubclass(QueueFailedJob, Model))

    def test_failed_job_table_name_is_stable(self) -> None:
        """Database driver depends on the queue_failed_jobs table name."""
        self.assertEqual(QueueFailedJob.__tablename__, 'queue_failed_jobs')

    def test_failed_job_declares_expected_columns(self) -> None:
        """Failed-job schema keeps every failure persistence column."""
        self.assertEqual(set(QueueFailedJob.__table__.columns.keys()), EXPECTED_FAILED_JOB_COLUMNS)

    def test_failed_job_required_columns_are_not_nullable(self) -> None:
        """Failed-job persistence requires connection, queue, payload and exception."""
        required = {'connection', 'queue', 'payload', 'exception', 'failed_at'}

        self.assertEqual({name for name in required if not QueueFailedJob.__table__.columns[name].nullable}, required)

    def test_failed_job_id_is_primary_key(self) -> None:
        """Failed jobs keep an autoincrementing primary key."""
        self.assertTrue(QueueFailedJob.__table__.columns['id'].primary_key)

    def test_failed_job_column_types_match_contract(self) -> None:
        """Column SQL types remain compatible with failed payload storage."""
        columns = QueueFailedJob.__table__.columns

        self.assertIsInstance(columns['id'].type, Integer)
        self.assertIsInstance(columns['connection'].type, String)
        self.assertIsInstance(columns['payload'].type, Text)
        self.assertIsInstance(columns['failed_at'].type, DateTime)


EXPECTED_FAILED_JOB_COLUMNS = {'id', 'connection', 'queue', 'payload', 'exception', 'failed_at'}


if __name__ == '__main__':
    unittest.main()
