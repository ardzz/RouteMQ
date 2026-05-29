import importlib
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from routemq.job import Job
from routemq.job_registry import JobRegistry, discover_and_register_jobs


class TestJobRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self._allowed_classes = set(Job._allowed_classes)
        Job._allowed_classes.clear()
        self._tmpdir = TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        sys.path.insert(0, str(self.root))
        importlib.invalidate_caches()

    def tearDown(self) -> None:
        sys.path.remove(str(self.root))
        self._tmpdir.cleanup()
        Job._allowed_classes.clear()
        Job._allowed_classes.update(self._allowed_classes)
        for module_name in list(sys.modules):
            if module_name == 'sample_jobs' or module_name.startswith('sample_jobs.'):
                sys.modules.pop(module_name, None)

    def _write_package(self) -> None:
        package = self.root / 'sample_jobs'
        package.mkdir()
        (package / '__init__.py').write_text('', encoding='utf-8')
        (package / 'email_job.py').write_text(
            textwrap.dedent(
                """
                from routemq.job import Job


                @Job.register
                class EmailJob(Job):
                    async def handle(self):
                        return None
                """
            ),
            encoding='utf-8',
        )
        (package / '_private_job.py').write_text(
            textwrap.dedent(
                """
                from routemq.job import Job


                @Job.register
                class PrivateJob(Job):
                    async def handle(self):
                        return None
                """
            ),
            encoding='utf-8',
        )

    def test_discover_and_register_jobs_imports_public_job_modules(self) -> None:
        self._write_package()

        loaded = discover_and_register_jobs('sample_jobs')

        self.assertEqual(['sample_jobs.email_job'], loaded)
        self.assertIn('sample_jobs.email_job.EmailJob', Job._allowed_classes)
        self.assertNotIn('sample_jobs._private_job.PrivateJob', Job._allowed_classes)

    def test_registry_returns_empty_list_when_package_is_missing(self) -> None:
        loaded = JobRegistry('missing_jobs').discover_and_register_jobs()

        self.assertEqual([], loaded)

    def test_registry_returns_empty_list_when_target_is_not_package(self) -> None:
        (self.root / 'sample_jobs.py').write_text('', encoding='utf-8')
        importlib.invalidate_caches()

        loaded = JobRegistry('sample_jobs').discover_and_register_jobs()

        self.assertEqual([], loaded)

    def test_registry_skips_job_modules_that_fail_to_import(self) -> None:
        self._write_package()
        package = self.root / 'sample_jobs'
        (package / 'bad_import.py').write_text('import missing_dependency_for_test\n', encoding='utf-8')
        (package / 'bad_runtime.py').write_text('raise RuntimeError("boom")\n', encoding='utf-8')
        importlib.invalidate_caches()

        loaded = JobRegistry('sample_jobs').discover_and_register_jobs()

        self.assertEqual(['sample_jobs.email_job'], loaded)


class TestExampleJobRegistration(unittest.TestCase):
    def setUp(self) -> None:
        self._allowed_classes = set(Job._allowed_classes)
        Job._allowed_classes.clear()

    def tearDown(self) -> None:
        Job._allowed_classes.clear()
        Job._allowed_classes.update(self._allowed_classes)

    def test_example_jobs_register_when_imported(self) -> None:
        for module_name in [
            'app.jobs.example_email_job',
            'app.jobs.example_data_processing_job',
            'app.jobs.example_report_job',
        ]:
            module = importlib.import_module(module_name)
            importlib.reload(module)

        self.assertIn('app.jobs.example_email_job.SendEmailJob', Job._allowed_classes)
        self.assertIn('app.jobs.example_data_processing_job.ProcessDataJob', Job._allowed_classes)
        self.assertIn('app.jobs.example_report_job.GenerateReportJob', Job._allowed_classes)


if __name__ == '__main__':
    unittest.main()
