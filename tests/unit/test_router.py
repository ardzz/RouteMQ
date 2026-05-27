import unittest
from unittest.mock import MagicMock, AsyncMock

from routemq.router import Router, Route


class TestRouter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.router = Router()
        self.test_client = MagicMock()

    def test_route_creation(self):
        async def test_handler(device_id, payload, client):
            return {'status': 'success', 'device_id': device_id}

        self.router.on('devices/{device_id}/status', test_handler, qos=1)

        self.assertEqual(len(self.router.routes), 1)
        self.assertEqual(self.router.routes[0].topic, 'devices/{device_id}/status')
        self.assertEqual(self.router.routes[0].qos, 1)

    def test_route_pattern_matching(self):
        route = Route('devices/{device_id}/sensors/{sensor_id}', AsyncMock())

        params = route.matches('devices/123/sensors/temp')
        self.assertIsNotNone(params)
        self.assertEqual(params['device_id'], '123')
        self.assertEqual(params['sensor_id'], 'temp')

        params = route.matches('devices/123/sensors')
        self.assertIsNone(params)

    def test_router_group(self):
        async def test_handler(device_id, payload, client):
            return {'status': 'success', 'device_id': device_id}

        group = self.router.group(prefix='sensors')
        group.on('temperature/{device_id}', test_handler)

        self.assertEqual(len(self.router.routes), 1)
        self.assertEqual(self.router.routes[0].topic, 'sensors/temperature/{device_id}')

    def test_with_statement_for_group(self):
        async def test_handler(device_id, payload, client):
            return {'status': 'success', 'device_id': device_id}

        with self.router.group(prefix='devices') as devices:
            devices.on('status/{device_id}', test_handler)

        self.assertEqual(len(self.router.routes), 1)
        self.assertEqual(self.router.routes[0].topic, 'devices/status/{device_id}')

    async def test_route_dispatch(self):
        handler_mock = AsyncMock(return_value={'status': 'success'})
        self.router.on('devices/{device_id}/status', handler_mock)

        await self.router.dispatch('devices/123/status', {'value': 25}, self.test_client)

        handler_mock.assert_called_once()
        args, kwargs = handler_mock.call_args
        self.assertEqual(kwargs['device_id'], '123')
        self.assertEqual(kwargs['payload'], {'value': 25})
        self.assertEqual(kwargs['client'], self.test_client)

    def test_shared_subscription(self):
        async def test_handler(device_id, payload, client):
            return {'status': 'success'}

        self.router.on('devices/{device_id}/status', test_handler, shared=True)

        route = self.router.routes[0]
        self.assertEqual(route.get_subscription_topic('test_group'), '$share/test_group/devices/+/status')

    def test_subscription_topic_without_shared_group_returns_plain_topic(self):
        async def test_handler(payload, client):
            return {'status': 'success'}

        self.router.on('devices/status', test_handler, shared=False)
        route = self.router.routes[0]
        result = route.get_subscription_topic()
        self.assertEqual(result, 'devices/status')

    def test_group_combines_group_and_route_middleware(self):
        from routemq.middleware import Middleware

        class _GroupMW(Middleware):
            async def handle(self, context, next_handler):
                return await next_handler(context)

        class _RouteMW(Middleware):
            async def handle(self, context, next_handler):
                return await next_handler(context)

        g = self.router.group(prefix='api', middleware=[_GroupMW()])
        g.on('test', AsyncMock(), middleware=[_RouteMW()])
        route = self.router.routes[0]
        self.assertEqual(len(route.middleware), 2)
        self.assertIsInstance(route.middleware[0], _GroupMW)
        self.assertIsInstance(route.middleware[1], _RouteMW)

    async def test_dispatch_skips_non_matching_route_then_matches_later(self):
        handler_first = AsyncMock(return_value={'status': 'ok'})
        handler_second = AsyncMock(return_value={'status': 'ok'})
        self.router.on('devices/create', handler_first)
        self.router.on('devices/{device_id}/status', handler_second)

        await self.router.dispatch('devices/42/status', {'value': 99}, self.test_client)

        handler_first.assert_not_called()
        handler_second.assert_called_once()
        args, kwargs = handler_second.call_args
        self.assertEqual(kwargs['device_id'], '42')

    async def test_dispatch_runs_route_middleware_chain(self):
        from routemq.middleware import Middleware

        call_order = []

        class _OrderMW(Middleware):
            def __init__(self, tag):
                self.tag = tag

            async def handle(self, context, next_handler):
                call_order.append(f'{self.tag}_enter')
                result = await next_handler(context)
                call_order.append(f'{self.tag}_exit')
                return result

        handler_mock = AsyncMock(return_value={'status': 'ok'})
        self.router.on('test/chain', handler_mock, middleware=[_OrderMW('first'), _OrderMW('second')])

        await self.router.dispatch('test/chain', {}, self.test_client)

        self.assertEqual(call_order, ['first_enter', 'second_enter', 'second_exit', 'first_exit'])

    async def test_dispatch_raises_when_no_route_matches(self):
        self.router.on('devices/{id}/status', AsyncMock())

        with self.assertRaisesRegex(ValueError, 'No route found for topic'):
            await self.router.dispatch('unknown/topic', {}, self.test_client)


if __name__ == '__main__':
    unittest.main()
