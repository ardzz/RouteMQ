from __future__ import annotations

import asyncio
import os
from importlib import import_module
from typing import Any

import pytest

from routemq.model import Model

_DOCKER_GATE_REASON = 'Set RUN_INTEGRATION_TESTS=1 and ensure Docker is available to run database queue benchmarks.'


def _integration_enabled() -> bool:
    return os.environ.get('RUN_INTEGRATION_TESTS', '').lower() in {'1', 'true', 'yes', 'on'}


def _docker_available() -> bool:
    try:
        docker = import_module('docker')
        client = docker.from_env(timeout=3)
        client.ping()
        client.close()
        return True
    except Exception:
        # Audit Accept: any docker probe failure means benchmarks skip; not a test failure.
        return False


pytestmark = pytest.mark.skipif(
    not (_integration_enabled() and _docker_available()),
    reason=_DOCKER_GATE_REASON,
)


@pytest.fixture(scope='module')
def mysql_url() -> Any:
    mysql_container_cls = import_module('testcontainers.mysql').MySqlContainer
    container = mysql_container_cls('mysql:8.0', dialect='aiomysql')
    container.start()
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture
def db_queue(mysql_url: str) -> Any:
    previous_engine = Model._engine
    previous_factory = Model._session_factory
    previous_enabled = Model._is_enabled
    previous_env = os.environ.get('ENABLE_MYSQL')

    os.environ['ENABLE_MYSQL'] = 'true'
    Model._is_enabled = True
    Model.configure(mysql_url, pool_size=10, max_overflow=20)

    import_module('routemq.queue.models')
    database_queue_cls = import_module('routemq.queue.database_queue').DatabaseQueue

    async def _setup() -> Any:
        await Model.create_tables()
        return database_queue_cls()

    driver = asyncio.run(_setup())
    try:
        yield driver
    finally:
        asyncio.run(Model.cleanup())
        Model._engine = previous_engine
        Model._session_factory = previous_factory
        Model._is_enabled = previous_enabled
        if previous_env is None:
            os.environ.pop('ENABLE_MYSQL', None)
        else:
            os.environ['ENABLE_MYSQL'] = previous_env


_PAYLOAD = '{"class_path": "bench.Job", "instance_dict": {}, "attempts": 0}'


async def _push_one(driver: Any, queue: str) -> None:
    await driver.push(_PAYLOAD, queue=queue)


async def _push_burst(driver: Any, queue: str, count: int) -> None:
    await asyncio.gather(*(driver.push(_PAYLOAD, queue=queue) for _ in range(count)))


async def _round_trip(driver: Any, queue: str) -> None:
    await driver.push(_PAYLOAD, queue=queue, delay=0)
    job = await driver.pop(queue)
    if job is not None:
        await driver.delete(job['id'], queue)


@pytest.mark.benchmark(group='database-queue')
def bench_db_queue_push_one(async_benchmark: Any, db_queue: Any) -> None:
    async_benchmark(_push_one, db_queue, 'bench-push')


@pytest.mark.benchmark(group='database-queue')
def bench_db_queue_push_burst_100(async_benchmark: Any, db_queue: Any) -> None:
    async_benchmark(_push_burst, db_queue, 'bench-burst', 100)


@pytest.mark.benchmark(group='database-queue')
def bench_db_queue_round_trip(async_benchmark: Any, db_queue: Any) -> None:
    async_benchmark(_round_trip, db_queue, 'bench-rt')
