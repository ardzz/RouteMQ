from __future__ import annotations

from routemq.job import Job

from ._harness import measure_ns, parse_args, print_result


@Job.register
class BenchmarkJob(Job):
    def __init__(self) -> None:
        super().__init__()
        self.value: dict[str, object] = {'device': 'abc', 'readings': [1, 2, 3]}

    async def handle(self) -> None:
        return None


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    job = BenchmarkJob()

    def bench() -> None:
        Job.unserialize(job.serialize())

    print_result('queue_serialization', measure_ns(bench, iterations=args.iterations, rounds=args.rounds))


if __name__ == '__main__':
    main()
