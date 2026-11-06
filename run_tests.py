#!/usr/bin/env python3
"""
Test runner for RouteMQ framework
"""

import os
import sys
import unittest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def run_tests():
    """Run all tests in the tests directory"""
    # Discover and run tests
    test_suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py')
    result = unittest.TextTestRunner().run(test_suite)

    if os.environ.get('RUN_INTEGRATION_TESTS', '').strip().lower() == 'required' and result.skipped:
        print('Required integration mode does not allow skipped tests:', file=sys.stderr)
        for test, reason in result.skipped:
            print(f'{test.id()}: {reason}', file=sys.stderr)
        return 1

    # Return proper exit code (0 if all tests pass, 1 otherwise)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
