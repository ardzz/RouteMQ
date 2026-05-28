# Mocking

Use mocks for external services in unit tests. RouteMQ integration tests cover real Redis, MySQL, and
Mosquitto behavior separately.

## Common patterns

```python
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

class MyTest(IsolatedAsyncioTestCase):
    async def test_handler(self):
        client = Mock()
        client.publish = Mock()
        next_handler = AsyncMock(return_value={"ok": True})
```

Patch at the import location used by the code under test. Reset singletons between tests when they hold
process-wide state.
