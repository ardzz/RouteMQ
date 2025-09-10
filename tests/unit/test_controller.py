import unittest
import asyncio
from unittest.mock import MagicMock

from core.controller import Controller


class TestController(unittest.TestCase):
    def setUp(self):
        # Create a test client mock
        self.client = MagicMock()

    def test_controller_logger(self):
        """Test that controllers have access to a logger."""
        # Check that the controller class has a logger
        self.assertIsNotNone(Controller.logger)

    def test_controller_extension(self):
        """Test that controllers can be extended."""
        # Create a controller subclass
        class TestController(Controller):
            @staticmethod
            async def handle_message(device_id, payload, client):
                return {"status": "processed", "device_id": device_id}

            @classmethod
            async def process_data(cls, payload):
                cls.logger.info("Processing data")
                return {"processed": True}

        # Test the static handler method
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            TestController.handle_message("123", {"value": 25}, self.client)
        )

        # Check the result
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["device_id"], "123")

        # Test the class method
        result = loop.run_until_complete(
            TestController.process_data({"value": 25})
        )

        # Check the result
        self.assertTrue(result["processed"])

    def test_controller_integration_with_router(self):
        """Test that controllers work with the router."""
        from core.router import Router

        # Create a controller
        class TestController(Controller):
            @staticmethod
            async def handle_message(device_id, payload, client):
                return {"status": "processed", "device_id": device_id}

        # Create a router and register the controller method
        router = Router()
        router.on("devices/{device_id}/status", TestController.handle_message)

        # Test dispatching a message
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            router.dispatch("devices/123/status", {"value": 25}, self.client)
        )

        # Check the result
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["device_id"], "123")


if __name__ == "__main__":
    unittest.main()
