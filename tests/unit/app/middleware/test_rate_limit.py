import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from app.middleware.rate_limit import RateLimitMiddleware
from routemq import observability


class TestRateLimitMiddleware(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.redis_enabled = patch('app.middleware.rate_limit.redis_manager.is_enabled', return_value=False)
        self.redis_enabled.start()
        self.addCleanup(self.redis_enabled.stop)
        self.addCleanup(observability.clear_hooks)

    async def test_allows_request_when_under_limit(self) -> None:
        """First request under the configured limit reaches the next handler."""
        middleware = RateLimitMiddleware(max_requests=2, window_seconds=10)
        next_handler = AsyncMock(return_value={'ok': True})

        result = await middleware.handle({'topic': 'devices/1'}, next_handler)

        self.assertEqual(result, {'ok': True})
        next_handler.assert_awaited_once()

    async def test_handle_emits_rate_limit_span_attributes(self) -> None:
        middleware = RateLimitMiddleware(max_requests=5, window_seconds=30, strategy='fixed_window')
        next_handler = AsyncMock(return_value={'ok': True})
        spans: list[Any] = []
        observability.register_span_hook(spans.append)

        with patch.object(middleware, '_check_rate_limit', AsyncMock(return_value=(True, 4, 29))):
            result = await middleware.handle({'topic': 'devices/1'}, next_handler)

        self.assertEqual(result, {'ok': True})
        span = spans[-1]
        self.assertEqual(span.name, 'middleware.rate_limit')
        self.assertEqual(span.kind, 'internal')
        self.assertEqual(span.attributes['routemq.rate_limit.strategy'], 'fixed_window')
        self.assertTrue(span.attributes['routemq.rate_limit.allowed'])
        self.assertEqual(span.attributes['routemq.rate_limit.remaining'], 4)
        self.assertEqual(span.attributes['routemq.rate_limit.reset_time'], 29)
        self.assertEqual(span.attributes['routemq.rate_limit.max_requests'], 5)
        self.assertEqual(span.attributes['routemq.rate_limit.window_seconds'], 30)

    async def test_blocks_request_when_over_limit(self) -> None:
        """Requests beyond max_requests return the rate-limit sentinel."""
        middleware = RateLimitMiddleware(max_requests=1, window_seconds=10)

        await middleware.handle({'topic': 'devices/1'}, AsyncMock(return_value='first'))
        result = await middleware.handle({'topic': 'devices/1'}, AsyncMock(return_value='second'))

        self.assertEqual(result['error'], 'rate_limit_exceeded')

    async def test_blocked_request_marks_context(self) -> None:
        """Blocked contexts expose rate-limit metadata for callers."""
        middleware = RateLimitMiddleware(max_requests=1, window_seconds=10)
        context: dict[str, Any] = {'topic': 'devices/1'}

        await middleware.handle(context, AsyncMock(return_value='first'))
        await middleware.handle(context, AsyncMock(return_value='second'))

        self.assertTrue(context['rate_limit']['exceeded'])

    async def test_window_expiry_resets_counter(self) -> None:
        """Expired sliding-window entries stop counting against new requests."""
        middleware = RateLimitMiddleware(max_requests=1, window_seconds=10)

        with patch('app.middleware.rate_limit.time.time', side_effect=[100.0, 111.0]):
            await middleware.handle({'topic': 'devices/1'}, AsyncMock(return_value='first'))
            result = await middleware.handle({'topic': 'devices/1'}, AsyncMock(return_value='second'))

        self.assertEqual(result, 'second')

    async def test_multiple_clients_are_tracked_independently(self) -> None:
        """Custom client keys isolate counters per client."""
        middleware = RateLimitMiddleware(max_requests=1, key_generator=lambda context: f'client:{context["client_id"]}')

        await middleware.handle({'client_id': 'a'}, AsyncMock(return_value='a1'))
        result = await middleware.handle({'client_id': 'b'}, AsyncMock(return_value='b1'))

        self.assertEqual(result, 'b1')

    async def test_zero_limit_raises_value_error_on_first_request(self) -> None:
        """Zero max_requests currently fails on an empty limiter window."""
        middleware = RateLimitMiddleware(max_requests=0, window_seconds=10)

        with self.assertRaises(ValueError):
            await middleware.handle({'topic': 'devices/1'}, AsyncMock(return_value='ok'))

    async def test_none_limit_raises_value_error_at_construction(self) -> None:
        """None max_requests is rejected before request-time rate-limit checks."""
        with self.assertRaises(ValueError):
            RateLimitMiddleware(max_requests=cast(Any, None))

    async def test_negative_limit_raises_value_error_on_first_request(self) -> None:
        """Negative max_requests currently fails on an empty limiter window."""
        middleware = RateLimitMiddleware(max_requests=-1, window_seconds=10)

        with self.assertRaises(ValueError):
            await middleware.handle({'topic': 'devices/1'}, AsyncMock(return_value='ok'))


if __name__ == '__main__':
    unittest.main()
