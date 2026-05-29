from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Union

import pytest

from routemq.job import Job
from routemq.middleware import Middleware
from routemq.queue.queue_driver import QueueDriver
from routemq.router import Router


class BenchmarkMiddleware(Middleware):
    async def handle(self, context: dict[str, Any], next_handler: Callable[[dict[str, Any]], Awaitable[Any]]) -> Any:
        return await next_handler(context)


class BenchmarkHandler:
    @staticmethod
    async def handle(device_id: str, payload: Any, client: object) -> None:
        return None


class BenchmarkJob(Job):
    def __init__(self, payload_size: int = 10, *, fail: bool = False) -> None:
        super().__init__()
        self.value: dict[str, object] = {f'field_{index}': index for index in range(payload_size)}
        self.fail = fail

    async def handle(self) -> None:
        if self.fail:
            raise RuntimeError('benchmark failure')


Job.register(BenchmarkJob)


class FakeQueueDriver(QueueDriver):
    def __init__(self, jobs: list[dict[str, object]]) -> None:
        self.jobs = list(jobs)
        self.deleted: list[Union[int, str]] = []
        self.released: list[tuple[Union[int, str], str, int]] = []
        self.failed_jobs: list[tuple[str, str, str, str]] = []

    async def push(self, payload: str, queue: str = 'default', delay: int = 0) -> None:
        self.jobs.append({'id': len(self.jobs) + 1, 'payload': payload, 'attempts': 1})

    async def pop(self, queue: str = 'default') -> dict[str, object] | None:
        if not self.jobs:
            return None
        return self.jobs.pop(0)

    async def release(self, job_id: Union[int, str], queue: str, delay: int = 0) -> None:
        self.released.append((job_id, queue, delay))

    async def delete(self, job_id: Union[int, str], queue: str) -> None:
        self.deleted.append(job_id)

    async def failed(self, connection: str, queue: str, payload: str, exception: str) -> None:
        self.failed_jobs.append((connection, queue, payload, exception))

    async def size(self, queue: str = 'default') -> int:
        return len(self.jobs)


@pytest.fixture
def async_benchmark(benchmark):
    def run(coro_factory: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> Any:
        return benchmark(lambda: asyncio.run(coro_factory(*args, **kwargs)))

    return run


@pytest.fixture
def make_router() -> Callable[[int, int], Router]:
    def factory(n_routes: int, middleware_depth: int = 0) -> Router:
        router = Router()
        middleware: list[Middleware] = [BenchmarkMiddleware() for _ in range(middleware_depth)]
        for route_id in range(n_routes):
            router.on(f'devices/{{device_id}}/status/{route_id}', BenchmarkHandler.handle, middleware=middleware)
        return router

    return factory


@pytest.fixture
def make_job() -> Callable[..., BenchmarkJob]:
    def factory(payload_size: int = 10, *, fail: bool = False) -> BenchmarkJob:
        return BenchmarkJob(payload_size, fail=fail)

    return factory


@pytest.fixture
def fake_driver(make_job: Callable[..., BenchmarkJob]) -> Callable[..., FakeQueueDriver]:
    def factory(n_jobs: int, *, payload_size: int = 10, fail: bool = False, attempts: int = 1) -> FakeQueueDriver:
        jobs = [
            {'id': index + 1, 'payload': make_job(payload_size, fail=fail).serialize(), 'attempts': attempts}
            for index in range(n_jobs)
        ]
        return FakeQueueDriver(jobs)

    return factory
