import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from core.router import Router, Route
from core.middleware import Middleware


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router()
        self.test_client = MagicMock()

    def test_route_creation(self):
        """Test that routes are correctly created and added to the router."""
        # Create a test handler
        async def test_handler(device_id, payload, client):
            return {"status": "success", "device_id": device_id}

        # Register a route
        self.router.on("devices/{device_id}/status", test_handler, qos=1)

        # Check if the route was added
        self.assertEqual(len(self.router.routes), 1)
        self.assertEqual(self.router.routes[0].topic, "devices/{device_id}/status")
        self.assertEqual(self.router.routes[0].qos, 1)

    def test_route_pattern_matching(self):
        """Test that route patterns correctly match topics and extract parameters."""
        # Create a route with parameters
        route = Route("devices/{device_id}/sensors/{sensor_id}", AsyncMock())

        # Test successful match
        params = route.matches("devices/123/sensors/temp")
        self.assertIsNotNone(params)
        self.assertEqual(params["device_id"], "123")
        self.assertEqual(params["sensor_id"], "temp")

        # Test unsuccessful match
        params = route.matches("devices/123/sensors")
        self.assertIsNone(params)

    def test_router_group(self):
        """Test that router groups correctly add prefixes to routes."""
        # Create a test handler
        async def test_handler(device_id, payload, client):
            return {"status": "success", "device_id": device_id}

        # Create a group and add a route
        group = self.router.group(prefix="sensors")
        group.on("temperature/{device_id}", test_handler)

        # Check if the route was added with the prefix
        self.assertEqual(len(self.router.routes), 1)
        self.assertEqual(self.router.routes[0].topic, "sensors/temperature/{device_id}")

    def test_with_statement_for_group(self):
        """Test that the 'with' statement works correctly with router groups."""
        # Create a test handler
        async def test_handler(device_id, payload, client):
            return {"status": "success", "device_id": device_id}

        # Use the with statement
        with self.router.group(prefix="devices") as devices:
            devices.on("status/{device_id}", test_handler)

        # Check if the route was added with the prefix
        self.assertEqual(len(self.router.routes), 1)
        self.assertEqual(self.router.routes[0].topic, "devices/status/{device_id}")

    def test_route_dispatch(self):
        """Test that dispatching a message correctly calls the handler with parameters."""
        # Create a test handler
        handler_mock = AsyncMock(return_value={"status": "success"})

        # Register a route
        self.router.on("devices/{device_id}/status", handler_mock)

        # Dispatch a message
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.router.dispatch("devices/123/status", {"value": 25}, self.test_client)
        )

        # Check if the handler was called with the correct parameters
        handler_mock.assert_called_once()
        # The first positional argument should be 'device_id'
        args, kwargs = handler_mock.call_args
        self.assertEqual(kwargs["device_id"], "123")
        self.assertEqual(kwargs["payload"], {"value": 25})
        self.assertEqual(kwargs["client"], self.test_client)

    def test_shared_subscription(self):
        """Test that shared subscription topics are formatted correctly."""
        # Create a test handler
        async def test_handler(device_id, payload, client):
            return {"status": "success"}

        # Register a route with shared=True
        self.router.on("devices/{device_id}/status", test_handler, shared=True)

        # Check the subscription topic
        route = self.router.routes[0]
        self.assertEqual(route.get_subscription_topic("test_group"), "$share/test_group/devices/+/status")


if __name__ == "__main__":
    unittest.main()
