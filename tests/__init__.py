import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ['ENABLE_MYSQL'] = 'false'


def load_tests(loader, tests, pattern):
    """Discovery function for unittest to find all tests."""
    suite = unittest.TestSuite()
    for all_test_suite in unittest.defaultTestLoader.discover('.', pattern='test_*.py'):
        for test_suite in all_test_suite:
            suite.addTests(test_suite)
    return suite
