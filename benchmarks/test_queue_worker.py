from __future__ import annotations

from collections.abc import Callable

import pytest

from routemq.queue.queue_worker import QueueWorker

from .conftest import FakeQueueDriver


async def _run_worker(driver: FakeQueueDriver, *, max_jobs: int = 1, sleep: int = 0) -> QueueWorker:
    worker = QueueWorker(sleep=sleep, max_jobs=max_jobs)
    worker.queue_manager.get_driver = lambda connection=None: driver
    await worker.work()
    return worker


async def _run_one_job(driver_factory: Callable[..., FakeQueueDriver], *, fail: bool = False) -> QueueWorker:
    driver = driver_factory(1, fail=fail, attempts=1)
    return await _run_worker(driver, max_jobs=1)


async def _run_empty_pop(driver: FakeQueueDriver) -> QueueWorker:
    worker = QueueWorker(sleep=0, max_jobs=1)
    worker.queue_manager.get_driver = lambda connection=None: driver
    original_pop = driver.pop

    async def pop_once(queue: str = 'default'):
        worker.should_quit = True
        return await original_pop(queue)

    driver.pop = pop_once
    await worker.work()
    return worker


async def _run_one_empty_pop(driver_factory: Callable[..., FakeQueueDriver]) -> QueueWorker:
    return await _run_empty_pop(driver_factory(0))


@pytest.mark.benchmark(group='queue-worker')
def bench_process_one_job_no_retry(async_benchmark, fake_driver: Callable[..., FakeQueueDriver]) -> None:
    async_benchmark(_run_one_job, fake_driver)


@pytest.mark.benchmark(group='queue-worker')
def bench_process_one_job_with_failure(async_benchmark, fake_driver: Callable[..., FakeQueueDriver]) -> None:
    async_benchmark(_run_one_job, fake_driver, fail=True)


@pytest.mark.benchmark(group='queue-worker')
def bench_pop_empty_queue_sleep(async_benchmark, fake_driver: Callable[..., FakeQueueDriver]) -> None:
    async_benchmark(_run_one_empty_pop, fake_driver)
