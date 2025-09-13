# Testing

Learn how to write and run tests for your RouteMQ application.

## Topics

- [Running Tests](running-tests.md) - Execute the test suite
- [Writing Unit Tests](unit-tests.md) - Test controllers and middleware
- [Integration Tests](integration-tests.md) - Test complete workflows
- [Mocking](mocking.md) - Mock external dependencies
- [Test Coverage](coverage.md) - Measure test coverage

## Quick Overview

Run the test suite:

```bash
python run_tests.py

# Or using uv
uv run pytest
```

## Writing Tests

Create your tests in the `tests/` directory:

```python
import unittest
from unittest.mock import Mock, AsyncMock, patch
from app.controllers.sensor_controller import SensorController
from app.middleware.rate_limit import RateLimitMiddleware

class TestSensorController(unittest.TestCase):
    async def test_handle_temperature(self):
        # Mock client and Redis
        client = Mock()
        client.publish = Mock()
        
        # Test data
        sensor_id = "temp_001"
        payload = {"value": 25.5, "unit": "celsius"}
        
        # Call controller
        result = await SensorController.handle_temperature(sensor_id, payload, client)
        
        # Assertions
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["sensor_id"], sensor_id)

class TestRateLimitMiddleware(unittest.TestCase):
    async def test_rate_limiting(self):
        # Create rate limiter
        rate_limiter = RateLimitMiddleware(max_requests=2, window_seconds=60)
        
        # Mock context and handler
        context = {"topic": "test/topic", "payload": {}}
        next_handler = AsyncMock(return_value={"success": True})
        
        # First two requests should pass
        result1 = await rate_limiter.handle(context, next_handler)
        self.assertEqual(result1["success"], True)
        
        result2 = await rate_limiter.handle(context, next_handler)
        self.assertEqual(result2["success"], True)
        
        # Third request should be rate limited
        result3 = await rate_limiter.handle(context, next_handler)
        self.assertIn("rate_limit_exceeded", result3.get("error", ""))
```

## Test Organization

```
tests/
├── __init__.py
├── unit/
│   ├── test_controller.py
│   ├── test_middleware.py
│   └── test_router.py
├── integration/
│   ├── test_full_workflow.py
│   └── test_redis_integration.py
└── fixtures/
    └── test_data.json
```

## Best Practices

- **Test Each Component**: Controllers, middleware, models separately
- **Mock External Dependencies**: Redis, database, MQTT client
- **Use Descriptive Names**: Clear test method names
- **Test Edge Cases**: Error conditions and boundary values
- **Keep Tests Fast**: Use mocks to avoid slow operations

## Next Steps

- [Running Tests](running-tests.md) - Execute tests
- [Unit Tests](unit-tests.md) - Test individual components
- [Integration Tests](integration-tests.md) - Test complete flows
