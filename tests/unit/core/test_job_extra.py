import logging
import unittest

from core.job import Job


class _LoggingJob(Job):
    async def handle(self) -> None:
        return None


class TestJobFailed(unittest.IsolatedAsyncioTestCase):
    async def test_default_failed_logs_error(self) -> None:
        job = _LoggingJob()

        with self.assertLogs('RouteMQ.Job', level='ERROR') as logs:
            await job.failed(RuntimeError('test error'))

        self.assertTrue(any('failed permanently' in msg for msg in logs.output))
        self.assertTrue(any('test error' in msg for msg in logs.output))


class TestJobRepr(unittest.TestCase):
    def test_job_repr_includes_attempts_and_max_tries(self) -> None:
        job = _LoggingJob()
        job.attempts = 2
        job.max_tries = 5

        r = repr(job)

        self.assertIn('_LoggingJob', r)
        self.assertIn('attempts=2', r)
        self.assertIn('max_tries=5', r)


if __name__ == '__main__':
    unittest.main()
