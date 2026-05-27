import unittest
from unittest.mock import MagicMock

from core.controller import Controller


class TestController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_controller_logger(self):
        self.assertIsNotNone(Controller.logger)

    async def test_controller_extension(self):
        class _TestController(Controller):
            @staticmethod
            async def handle_message(device_id, payload, client):
                return {'status': 'processed', 'device_id': device_id}

            @classmethod
            async def process_data(cls, payload):
                cls.logger.info('Processing data')
                return {'processed': True}

        result = await _TestController.handle_message('123', {'value': 25}, self.client)
        self.assertEqual(result['status'], 'processed')
        self.assertEqual(result['device_id'], '123')

        result = await _TestController.process_data({'value': 25})
        self.assertTrue(result['processed'])

    async def test_controller_integration_with_router(self):
        from core.router import Router

        class _TestController(Controller):
            @staticmethod
            async def handle_message(device_id, payload, client):
                return {'status': 'processed', 'device_id': device_id}

        router = Router()
        router.on('devices/{device_id}/status', _TestController.handle_message)

        result = await router.dispatch('devices/123/status', {'value': 25}, self.client)
        self.assertEqual(result['status'], 'processed')
        self.assertEqual(result['device_id'], '123')


if __name__ == '__main__':
    unittest.main()
