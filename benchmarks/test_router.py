from __future__ import annotations

from collections.abc import Callable

import pytest

from routemq.router import Router


def _dispatch(router: Router, topic: str):
    return router.dispatch(topic, {'ok': True}, object())


async def _dispatch_no_match(router: Router, topic: str) -> None:
    with pytest.raises(ValueError):
        await _dispatch(router, topic)


@pytest.mark.benchmark(group='router-compile')
def bench_route_compile_small(benchmark, make_router: Callable[[int, int], Router]) -> None:
    benchmark(lambda: make_router(10, 0))


@pytest.mark.benchmark(group='router-compile')
def bench_route_compile_large(benchmark, make_router: Callable[[int, int], Router]) -> None:
    benchmark(lambda: make_router(500, 0))


@pytest.mark.benchmark(group='router-dispatch')
def bench_dispatch_first_route_hit(async_benchmark, make_router: Callable[[int, int], Router]) -> None:
    router = make_router(1, 0)

    async_benchmark(_dispatch, router, 'devices/abc/status/0')


@pytest.mark.benchmark(group='router-dispatch')
def bench_dispatch_last_route_hit(async_benchmark, make_router: Callable[[int, int], Router]) -> None:
    router = make_router(100, 0)

    async_benchmark(_dispatch, router, 'devices/abc/status/99')


@pytest.mark.benchmark(group='router-dispatch')
def bench_dispatch_no_match(async_benchmark, make_router: Callable[[int, int], Router]) -> None:
    router = make_router(100, 0)

    async_benchmark(_dispatch_no_match, router, 'devices/abc/status/missing')


@pytest.mark.benchmark(group='router-middleware')
def bench_middleware_chain_depth_0(async_benchmark, make_router: Callable[[int, int], Router]) -> None:
    router = make_router(1, 0)

    async_benchmark(_dispatch, router, 'devices/abc/status/0')


@pytest.mark.benchmark(group='router-middleware')
def bench_middleware_chain_depth_5(async_benchmark, make_router: Callable[[int, int], Router]) -> None:
    router = make_router(1, 5)

    async_benchmark(_dispatch, router, 'devices/abc/status/0')


@pytest.mark.benchmark(group='router-middleware')
def bench_middleware_chain_depth_20(async_benchmark, make_router: Callable[[int, int], Router]) -> None:
    router = make_router(1, 20)

    async_benchmark(_dispatch, router, 'devices/abc/status/0')
