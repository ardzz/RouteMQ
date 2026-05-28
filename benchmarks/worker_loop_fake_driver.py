from __future__ import annotations

import asyncio
from typing import Union

from routemq.queue.queue_driver import QueueDriver
from routemq.queue.queue_worker import QueueWorker

from ._harness import measure_ns, parse_args, print_result


class FakeDriver(QueueDriver):
    async def push(self, payload: str, queue: str = 'default', delay: int = 0) -> None:
        return None

    async def pop(self, queue: str = 'default') -> dict | None:
        return None

    async def release(self, job_id: Union[int, str], queue: str, delay: int = 0) -> None:
        return None

    async def delete(self, job_id: Union[int, str], queue: str) -> None:
        return None

    async def failed(self, connection: str, queue: str, payload: str, exception: str) -> None:
        return None

    async def size(self, queue: str = 'default') -> int:
        return 0


async def _poll_once() -> None:
    worker = QueueWorker(sleep=0, max_jobs=1)
    driver = FakeDriver()
    worker.queue_manager.get_driver = lambda connection=None: driver
    worker.should_quit = True
    await worker.work()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    def bench() -> None:
        asyncio.run(_poll_once())

    print_result('worker_loop_fake_driver', measure_ns(bench, iterations=args.iterations, rounds=args.rounds))


if __name__ == '__main__':
    main()
