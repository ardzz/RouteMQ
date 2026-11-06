import os
import sys
import unittest
from importlib import import_module


_OPTIONAL_INTEGRATION_VALUES = {'1', 'true', 'yes', 'on'}


def _integration_mode() -> str:
    value = os.environ.get('RUN_INTEGRATION_TESTS', '').strip().lower()
    if value == 'required':
        return 'required'
    if value in _OPTIONAL_INTEGRATION_VALUES:
        return 'optional'
    return 'off'


def integration_tests_enabled() -> bool:
    """Return whether Docker-backed integration tests were explicitly enabled."""
    return _integration_mode() != 'off'


def _require_dependency(name: str, dependency: str, integration: str):
    mode = _integration_mode()
    if mode == 'off':
        raise unittest.SkipTest(
            f'{integration} integration "{name}" is disabled. Set RUN_INTEGRATION_TESTS=1 to run it.'
        )
    try:
        return import_module(dependency)
    except ImportError as exc:
        message = (
            f'{integration} integration "{name}" requires Python dependency "{dependency}". '
            'Install the selected integration dependencies and rerun the tests.'
        )
        if mode == 'required':
            raise RuntimeError(message) from exc
        raise unittest.SkipTest(message) from exc


def require_integration_dependency(name: str, dependency: str):
    return _require_dependency(name, dependency, 'Selected')


def require_docker_integration(name: str) -> None:
    mode = _integration_mode()
    if mode == 'off':
        raise unittest.SkipTest(f'Docker integration "{name}" is disabled. Set RUN_INTEGRATION_TESTS=1 to run it.')

    docker = _require_dependency(name, 'docker', 'Docker')
    requests_exceptions = _require_dependency(name, 'requests.exceptions', 'Docker')
    docker_client = None
    unavailable: Exception | None = None
    try:
        docker_client = docker.from_env(timeout=3)
        if not docker_client.ping():
            unavailable = docker.errors.DockerException('Docker daemon ping returned false')
    except (docker.errors.DockerException, requests_exceptions.RequestException) as exc:
        unavailable = exc
    finally:
        if docker_client is not None:
            try:
                docker_client.close()
            except Exception as exc:
                if unavailable is None:
                    unavailable = exc

    if unavailable is None:
        return

    message = (
        f'Docker integration "{name}" is unavailable: {unavailable}. '
        'Start Docker and verify the daemon is reachable before rerunning the tests.'
    )
    if mode == 'required':
        raise RuntimeError(message) from unavailable
    raise unittest.SkipTest(message) from unavailable


def _cleanup_testcontainers_reaper() -> None:
    container_module = sys.modules.get('testcontainers.core.container')
    if container_module is not None:
        container_module.Reaper.delete_instance()


class DockerIntegrationTestCase(unittest.TestCase):
    """Base class for Docker-backed integration tests."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        require_docker_integration(cls.__name__)
        cls.addClassCleanup(_cleanup_testcontainers_reaper)
