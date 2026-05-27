import unittest
from unittest.mock import MagicMock, AsyncMock

from core.router import Router, Route


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


if __name__ == '__main__':
    unittest.main()
