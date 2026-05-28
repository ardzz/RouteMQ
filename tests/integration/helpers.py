import os
import unittest

import docker
from docker.errors import DockerException


def integration_tests_enabled() -> bool:
    """Return whether Docker-backed integration tests were explicitly enabled."""
    return os.environ.get('RUN_INTEGRATION_TESTS', '').lower() in {'1', 'true', 'yes', 'on'}


class DockerIntegrationTestCase(unittest.TestCase):
    """Base class for Docker-backed integration tests."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        if not integration_tests_enabled():
            raise unittest.SkipTest('Set RUN_INTEGRATION_TESTS=1 to run integration tests (requires Docker).')

        docker_client = None
        try:
            docker_client = docker.from_env(timeout=3)
            docker_client.ping()
        except DockerException as exc:
            raise unittest.SkipTest(f'Docker daemon is not available: {exc}') from exc
        finally:
            if docker_client is not None:
                docker_client.close()
