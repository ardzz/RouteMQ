import builtins
import importlib
import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from routemq.scaffold import prompts


DEFAULTS = {
    'with_mysql': False,
    'with_redis': True,
    'with_queue': False,
    'with_docker': False,
    'package_manager': 'uv',
}


class GatherChoicesTests(unittest.TestCase):
    def test_returns_defaults_copy_when_user_cancels_prompt(self) -> None:
        fake_questionary = SimpleNamespace(prompt=lambda _questions: None)
        with patch.object(prompts, 'import_module', return_value=fake_questionary):
            result = prompts.gather_choices(DEFAULTS)

        self.assertEqual(result, DEFAULTS)
        self.assertIsNot(result, DEFAULTS)

    def test_enables_redis_when_queue_selected_without_backend(self) -> None:
        answers = {
            'with_mysql': False,
            'with_redis': False,
            'with_queue': True,
            'with_docker': False,
            'package_manager': 'pip',
        }
        fake_questionary = SimpleNamespace(prompt=lambda _questions: dict(answers))
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with patch.object(prompts, 'import_module', return_value=fake_questionary):
                result = prompts.gather_choices(DEFAULTS)

        self.assertTrue(result['with_redis'])
        self.assertTrue(result['with_queue'])
        self.assertIn('Queue requires Redis or MySQL backend', buffer.getvalue())

    def test_returns_answers_unchanged_when_backend_already_present(self) -> None:
        answers = {
            'with_mysql': True,
            'with_redis': False,
            'with_queue': True,
            'with_docker': True,
            'package_manager': 'uv',
        }
        fake_questionary = SimpleNamespace(prompt=lambda _questions: dict(answers))
        with patch.object(prompts, 'import_module', return_value=fake_questionary):
            result = prompts.gather_choices(DEFAULTS)

        self.assertEqual(result, answers)

    def test_raises_helpful_error_when_questionary_missing(self) -> None:
        real_import = builtins.__import__
        sys.modules.pop('questionary', None)

        def import_blocker(name, *args, **kwargs):
            if name == 'questionary':
                raise ImportError("No module named 'questionary'")
            return real_import(name, *args, **kwargs)

        importlib.invalidate_caches()
        with patch.object(builtins, '__import__', side_effect=import_blocker):
            with self.assertRaisesRegex(ImportError, 'routemq\\[cli\\]'):
                prompts.gather_choices(DEFAULTS)


if __name__ == '__main__':
    unittest.main()
