from __future__ import annotations

import asyncio

from routemq.router import Router

from ._harness import measure_ns, parse_args, print_result


class Handler:
    @staticmethod
    async def handle(device_id, payload, client):
        return None


async def _dispatch(router: Router) -> None:
    await router.dispatch('devices/abc/status', {'ok': True}, object())


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    router = Router()
    router.on('devices/{device_id}/status', Handler.handle)

    def bench() -> None:
        asyncio.run(_dispatch(router))

    print_result('route_dispatch', measure_ns(bench, iterations=args.iterations, rounds=args.rounds))


if __name__ == '__main__':
    main()
