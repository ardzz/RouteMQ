#!/usr/bin/env python3
"""
Test runner for RouteMQ framework
"""
import unittest
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def run_tests():
    """Run all tests in the tests directory"""
    # Discover and run tests
    test_suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py')
    result = unittest.TextTestRunner().run(test_suite)

    # Return proper exit code (0 if all tests pass, 1 otherwise)
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(run_tests())
