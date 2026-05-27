import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from routemq.scaffold import run_scaffolder


class TestScaffolder(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.target = Path(self.tmpdir.name) / 'demo'

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run(self, **kwargs):
        defaults = {
            'yes': True,
            'with_mysql': False,
            'with_redis': False,
            'with_queue': False,
            'with_docker': False,
            'package_manager': 'uv',
            'no_input': True,
        }
        defaults.update(kwargs)
        old_cwd = os.getcwd()
        os.chdir(self.tmpdir.name)
        try:
            return run_scaffolder('demo', **defaults)
        finally:
            os.chdir(old_cwd)

    def test_base_tree_no_features(self):
        rc = self._run()

        self.assertEqual(rc, 0)
        expected = [
            'app/__init__.py',
            'app/controllers/__init__.py',
            'app/controllers/example_controller.py',
            'app/middleware/__init__.py',
            'app/middleware/example_middleware.py',
            'app/models/__init__.py',
            'app/routers/__init__.py',
            'app/routers/example_device.py',
            '.env',
            '.gitignore',
            'pyproject.toml',
            'README.md',
        ]
        for filename in expected:
            self.assertTrue((self.target / filename).exists(), f'missing {filename}')

    def test_mysql_feature_adds_model_and_env(self):
        self._run(with_mysql=True)

        self.assertTrue((self.target / 'app/models/example_model.py').exists())
        env = (self.target / '.env').read_text(encoding='utf-8')
        self.assertIn('ENABLE_MYSQL=true', env)
        self.assertIn('DB_NAME=demo', env)

    def test_redis_feature_sets_env_and_extra(self):
        self._run(with_redis=True)

        env = (self.target / '.env').read_text(encoding='utf-8')
        pyproject = (self.target / 'pyproject.toml').read_text(encoding='utf-8')
        self.assertIn('ENABLE_REDIS=true', env)
        self.assertIn('REDIS_HOST=localhost', env)
        self.assertIn('routemq[redis]>=', pyproject)

    def test_queue_feature_adds_jobs(self):
        self._run(with_queue=True, with_redis=True)

        self.assertTrue((self.target / 'app/jobs/__init__.py').exists())
        self.assertTrue((self.target / 'app/jobs/example_job.py').exists())
        env = (self.target / '.env').read_text(encoding='utf-8')
        self.assertIn('QUEUE_CONNECTION=redis', env)

    def test_queue_uses_database_when_mysql_is_selected_without_redis(self):
        self._run(with_queue=True, with_mysql=True)

        env = (self.target / '.env').read_text(encoding='utf-8')
        self.assertIn('QUEUE_CONNECTION=database', env)
        self.assertNotIn('ENABLE_REDIS=true', env)

    def test_queue_auto_enables_backend_when_none(self):
        self._run(with_queue=True)

        env = (self.target / '.env').read_text(encoding='utf-8')
        self.assertIn('ENABLE_REDIS=true', env)
        self.assertIn('QUEUE_CONNECTION=redis', env)

    def test_docker_feature_adds_compose(self):
        self._run(with_docker=True, with_redis=True)

        self.assertTrue((self.target / 'docker-compose.yml').exists())
        self.assertTrue((self.target / 'Dockerfile').exists())
        self.assertTrue((self.target / 'Makefile').exists())
        compose = (self.target / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('redis:', compose)

    def test_yes_skips_prompts(self):
        with patch('routemq.scaffold.prompts.gather_choices') as mock_prompts:
            self._run(yes=True, no_input=False)

        mock_prompts.assert_not_called()

    def test_interactive_prompts_are_lazy_and_used_on_tty(self):
        choices = {
            'with_mysql': False,
            'with_redis': True,
            'with_queue': False,
            'with_docker': False,
            'package_manager': 'pip',
        }
        with (
            patch.object(sys.stdout, 'isatty', return_value=True),
            patch('routemq.scaffold.prompts.gather_choices', return_value=choices) as mock_prompts,
        ):
            self._run(yes=False, no_input=False)

        mock_prompts.assert_called_once()
        readme = (self.target / 'README.md').read_text(encoding='utf-8')
        self.assertIn('pip install -e .', readme)

    def test_refuses_non_empty_target(self):
        self.target.mkdir(parents=True)
        (self.target / 'stuff.txt').write_text('hi', encoding='utf-8')

        rc = self._run()

        self.assertEqual(rc, 2)

    def test_jinja_substitution_renders_project_name_and_features(self):
        self._run(with_mysql=True, with_redis=True, with_queue=True)

        pyproject = (self.target / 'pyproject.toml').read_text(encoding='utf-8')
        readme = (self.target / 'README.md').read_text(encoding='utf-8')
        self.assertIn('name = "demo"', pyproject)
        self.assertIn('RouteMQ starter project', readme)
        self.assertIn('Selected features: mysql, redis, queue', readme)


if __name__ == '__main__':
    unittest.main()
