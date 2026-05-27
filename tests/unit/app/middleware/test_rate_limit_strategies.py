import time
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.middleware.rate_limit import (
    ClientRateLimitMiddleware,
    RateLimitMiddleware,
    TopicRateLimitMiddleware,
)


class RateLimitConstructionTests(unittest.TestCase):
    def test_invalid_strategy_raises(self) -> None:
        with self.assertRaises(ValueError):
            RateLimitMiddleware(max_requests=10, strategy='not_a_strategy')

    def test_strategy_normalised_to_lowercase(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, strategy='Sliding_Window')
        self.assertEqual(mw.strategy, 'sliding_window')

    def test_burst_allowance_defaults_zero(self) -> None:
        mw = RateLimitMiddleware(max_requests=10)
        self.assertEqual(mw.burst_allowance, 0)

    def test_block_duration_defaults_to_window(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, window_seconds=30)
        self.assertEqual(mw.block_duration, 30)

    def test_block_duration_override_respected(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, window_seconds=30, block_duration=120)
        self.assertEqual(mw.block_duration, 120)

    def test_whitelist_is_set_not_list(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, whitelist=['a', 'b', 'a'])
        self.assertEqual(mw.whitelist, {'a', 'b'})

    def test_default_key_generator_uses_topic(self) -> None:
        mw = RateLimitMiddleware(max_requests=10)
        self.assertEqual(mw._default_key_generator({'topic': 'devices/1'}), 'topic:devices/1')

    def test_default_key_generator_handles_missing_topic(self) -> None:
        mw = RateLimitMiddleware(max_requests=10)
        self.assertEqual(mw._default_key_generator({}), 'topic:unknown')


class WhitelistTests(unittest.TestCase):
    def test_substring_match(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, whitelist=['admin'])
        self.assertTrue(mw._is_whitelisted('topic:admin/status'))

    def test_startswith_match(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, whitelist=['internal:'])
        self.assertTrue(mw._is_whitelisted('internal:foo'))

    def test_no_match(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, whitelist=['admin'])
        self.assertFalse(mw._is_whitelisted('topic:user/status'))

    def test_empty_whitelist_never_matches(self) -> None:
        mw = RateLimitMiddleware(max_requests=10)
        self.assertFalse(mw._is_whitelisted('anything'))


class HandleBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_whitelisted_request_skips_rate_check(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, whitelist=['admin'])
        next_handler = AsyncMock(return_value='handled')
        result = await mw.handle({'topic': 'admin/test'}, next_handler)
        self.assertEqual(result, 'handled')
        next_handler.assert_awaited_once()

    async def test_allowed_request_calls_next_and_annotates_context(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, strategy='sliding_window')
        next_handler = AsyncMock(return_value='ok')
        ctx: dict[str, Any] = {'topic': 'devices/1/status'}

        with patch.object(mw, '_check_rate_limit', AsyncMock(return_value=(True, 5, 60))):
            result = await mw.handle(ctx, next_handler)

        self.assertEqual(result, 'ok')
        self.assertFalse(ctx['rate_limit']['exceeded'])
        self.assertEqual(ctx['rate_limit']['remaining'], 5)
        next_handler.assert_awaited_once_with(ctx)

    async def test_blocked_request_returns_error_payload(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, custom_error_message='Slow down!')
        next_handler = AsyncMock()
        ctx: dict[str, Any] = {'topic': 'devices/1/status'}

        with patch.object(mw, '_check_rate_limit', AsyncMock(return_value=(False, 0, 30))):
            result = await mw.handle(ctx, next_handler)

        self.assertEqual(result['error'], 'rate_limit_exceeded')
        self.assertEqual(result['message'], 'Slow down!')
        self.assertEqual(result['rate_limit']['remaining'], 0)
        self.assertEqual(result['rate_limit']['reset_time'], 30)
        next_handler.assert_not_awaited()
        self.assertTrue(ctx['rate_limit']['exceeded'])


class CheckRateLimitDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_redis_path_used_when_enabled(self) -> None:
        mw = RateLimitMiddleware(max_requests=10)
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            mock_redis.is_enabled.return_value = True
            with patch.object(
                mw,
                '_check_rate_limit_redis',
                AsyncMock(return_value=(True, 9, 60)),
            ) as mock_redis_check:
                allowed, remaining, reset = await mw._check_rate_limit('foo')

        mock_redis_check.assert_awaited_once()
        self.assertEqual((allowed, remaining, reset), (True, 9, 60))

    async def test_redis_failure_falls_back_to_memory_when_enabled(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, fallback_enabled=True)
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            mock_redis.is_enabled.return_value = True
            with (
                patch.object(
                    mw,
                    '_check_rate_limit_redis',
                    AsyncMock(side_effect=RuntimeError('redis down')),
                ),
                patch.object(
                    mw,
                    '_check_rate_limit_memory',
                    AsyncMock(return_value=(True, 9, 60)),
                ) as mock_memory_check,
            ):
                allowed, remaining, reset = await mw._check_rate_limit('foo')

        mock_memory_check.assert_awaited_once()
        self.assertEqual((allowed, remaining, reset), (True, 9, 60))

    async def test_redis_failure_with_no_fallback_allows_request(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, fallback_enabled=False)
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            mock_redis.is_enabled.return_value = True
            with patch.object(
                mw,
                '_check_rate_limit_redis',
                AsyncMock(side_effect=RuntimeError('redis down')),
            ):
                allowed, remaining, reset = await mw._check_rate_limit('foo')

        self.assertTrue(allowed)
        self.assertEqual(remaining, 9)

    async def test_redis_disabled_uses_memory_when_fallback_enabled(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, fallback_enabled=True)
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            mock_redis.is_enabled.return_value = False
            with patch.object(
                mw,
                '_check_rate_limit_memory',
                AsyncMock(return_value=(True, 9, 60)),
            ) as mock_memory_check:
                await mw._check_rate_limit('foo')

        mock_memory_check.assert_awaited_once()

    async def test_redis_disabled_no_fallback_allows_request(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, fallback_enabled=False)
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            mock_redis.is_enabled.return_value = False
            allowed, remaining, reset = await mw._check_rate_limit('foo')

        self.assertTrue(allowed)
        self.assertEqual(remaining, 9)

    async def test_redis_dispatch_unknown_strategy_raises(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, strategy='sliding_window')
        mw.strategy = 'mystery'
        with self.assertRaises(ValueError):
            await mw._check_rate_limit_redis('k')

    async def test_redis_dispatch_routes_to_sliding_window(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, strategy='sliding_window')
        with patch.object(mw, '_sliding_window_redis', AsyncMock(return_value=(True, 5, 60))) as mock_method:
            await mw._check_rate_limit_redis('k')
        mock_method.assert_awaited_once()

    async def test_redis_dispatch_routes_to_fixed_window(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, strategy='fixed_window')
        with patch.object(mw, '_fixed_window_redis', AsyncMock(return_value=(True, 5, 60))) as mock_method:
            await mw._check_rate_limit_redis('k')
        mock_method.assert_awaited_once()

    async def test_redis_dispatch_routes_to_token_bucket(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, strategy='token_bucket')
        with patch.object(mw, '_token_bucket_redis', AsyncMock(return_value=(True, 5, 60))) as mock_method:
            await mw._check_rate_limit_redis('k')
        mock_method.assert_awaited_once()


class MemoryStrategiesTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_dispatch_unknown_strategy_raises(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, strategy='sliding_window')
        mw.strategy = 'mystery'
        with self.assertRaises(ValueError):
            await mw._check_rate_limit_memory('k')

    async def test_memory_sliding_window_under_limit_allows(self) -> None:
        mw = RateLimitMiddleware(max_requests=3, window_seconds=60, strategy='sliding_window')
        for _ in range(3):
            allowed, remaining, reset = await mw._check_rate_limit_memory('k')
            self.assertTrue(allowed)
        self.assertEqual(remaining, 0)

    async def test_memory_sliding_window_over_limit_blocks(self) -> None:
        mw = RateLimitMiddleware(max_requests=2, window_seconds=60, strategy='sliding_window')
        for _ in range(2):
            await mw._check_rate_limit_memory('k')
        allowed, remaining, reset = await mw._check_rate_limit_memory('k')
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreaterEqual(reset, 1)

    async def test_memory_fixed_window_under_limit_allows(self) -> None:
        mw = RateLimitMiddleware(max_requests=3, window_seconds=60, strategy='fixed_window')
        allowed, remaining, reset = await mw._check_rate_limit_memory('k')
        self.assertTrue(allowed)
        self.assertEqual(remaining, 2)

    async def test_memory_fixed_window_over_limit_blocks(self) -> None:
        mw = RateLimitMiddleware(max_requests=1, window_seconds=60, strategy='fixed_window')
        await mw._check_rate_limit_memory('k')
        allowed, remaining, reset = await mw._check_rate_limit_memory('k')
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)

    async def test_memory_fixed_window_resets_in_new_window(self) -> None:
        mw = RateLimitMiddleware(max_requests=1, window_seconds=60, strategy='fixed_window')
        await mw._check_rate_limit_memory('k')
        cache_entry = mw._memory_cache['k']
        cache_entry['window_start'] = 0
        allowed, remaining, _ = await mw._check_rate_limit_memory('k')
        self.assertTrue(allowed)

    async def test_memory_token_bucket_initializes_full(self) -> None:
        mw = RateLimitMiddleware(max_requests=5, window_seconds=60, strategy='token_bucket')
        allowed, remaining, _ = await mw._check_rate_limit_memory('k')
        self.assertTrue(allowed)
        self.assertGreaterEqual(remaining, 3)

    async def test_memory_token_bucket_exhausts_then_blocks(self) -> None:
        mw = RateLimitMiddleware(max_requests=2, window_seconds=60, strategy='token_bucket')
        await mw._check_rate_limit_memory('k')
        await mw._check_rate_limit_memory('k')
        cache_entry = mw._memory_cache['k']
        cache_entry['tokens'] = 0.0
        allowed, remaining, reset = await mw._check_rate_limit_memory('k')
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreaterEqual(reset, 1)


class CleanupMemoryCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_removes_entries_older_than_two_windows(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, window_seconds=60)
        now = time.time()
        mw._memory_cache['stale'] = {'requests': [], 'created': now - 200}
        mw._memory_cache['fresh'] = {'requests': [], 'created': now}

        await mw._cleanup_memory_cache(now)

        self.assertNotIn('stale', mw._memory_cache)
        self.assertIn('fresh', mw._memory_cache)
        self.assertEqual(mw._last_cleanup, now)

    async def test_cleanup_is_triggered_on_interval_in_check(self) -> None:
        mw = RateLimitMiddleware(max_requests=5, window_seconds=60, strategy='sliding_window')
        mw._last_cleanup = 0.0
        with patch.object(mw, '_cleanup_memory_cache', AsyncMock()) as mock_cleanup:
            await mw._check_rate_limit_memory('k')
        mock_cleanup.assert_awaited_once()


class RedisSlidingWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_under_limit_allows_and_returns_remaining(self) -> None:
        mw = RateLimitMiddleware(max_requests=5, window_seconds=60, strategy='sliding_window')
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            client = MagicMock()
            pipe = MagicMock()
            pipe.execute = AsyncMock(return_value=[0, 2, 1, True])
            client.pipeline.return_value = pipe
            mock_redis.get_client.return_value = client

            allowed, remaining, reset = await mw._sliding_window_redis('rk', 1000)

        self.assertTrue(allowed)
        self.assertEqual(remaining, 5 - 2 - 1)
        self.assertEqual(reset, 60)

    async def test_at_limit_blocks_and_reports_reset(self) -> None:
        mw = RateLimitMiddleware(max_requests=5, window_seconds=60, strategy='sliding_window')
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            client = MagicMock()
            pipe = MagicMock()
            pipe.execute = AsyncMock(return_value=[0, 5, 1, True])
            client.pipeline.return_value = pipe
            client.zrange = AsyncMock(return_value=[(b'998', 998.0)])
            client.zrem = AsyncMock(return_value=1)
            mock_redis.get_client.return_value = client

            allowed, remaining, reset = await mw._sliding_window_redis('rk', 1000)

        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreaterEqual(reset, 1)
        client.zrem.assert_awaited_once()


class RedisFixedWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_request_sets_expiration(self) -> None:
        mw = RateLimitMiddleware(max_requests=5, window_seconds=60, strategy='fixed_window')
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            client = MagicMock()
            client.incr = AsyncMock(return_value=1)
            client.expire = AsyncMock()
            mock_redis.get_client.return_value = client

            allowed, remaining, _ = await mw._fixed_window_redis('rk', 1000)

        client.expire.assert_awaited_once()
        self.assertTrue(allowed)
        self.assertEqual(remaining, 4)

    async def test_over_limit_blocks(self) -> None:
        mw = RateLimitMiddleware(max_requests=3, window_seconds=60, strategy='fixed_window')
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            client = MagicMock()
            client.incr = AsyncMock(return_value=5)
            client.expire = AsyncMock()
            mock_redis.get_client.return_value = client

            allowed, remaining, reset = await mw._fixed_window_redis('rk', 1000)

        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreaterEqual(reset, 1)


class RedisTokenBucketTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_bucket_allows_request(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, window_seconds=60, strategy='token_bucket')
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            client = MagicMock()
            pipe = MagicMock()
            pipe.execute = AsyncMock(return_value=[None, None])
            client.pipeline.return_value = pipe
            mock_redis.get_client.return_value = client

            allowed, remaining, _ = await mw._token_bucket_redis('rk', 1000)

        self.assertTrue(allowed)
        self.assertGreaterEqual(remaining, 8)

    async def test_empty_bucket_denies(self) -> None:
        mw = RateLimitMiddleware(max_requests=10, window_seconds=60, strategy='token_bucket')
        with patch('app.middleware.rate_limit.redis_manager') as mock_redis:
            client = MagicMock()
            pipe = MagicMock()
            pipe.execute = AsyncMock(return_value=[b'0', b'1000'])
            client.pipeline.return_value = pipe
            mock_redis.get_client.return_value = client

            allowed, remaining, reset = await mw._token_bucket_redis('rk', 1000)

        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreaterEqual(reset, 1)


class TopicRateLimitMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def test_init_with_topic_limits(self) -> None:
        mw = TopicRateLimitMiddleware(
            topic_limits={'devices/+/status': {'max_requests': 50, 'window_seconds': 30}},
            default_limit={'max_requests': 100, 'window_seconds': 60},
        )
        self.assertEqual(mw.topic_limits, {'devices/+/status': {'max_requests': 50, 'window_seconds': 30}})

    def test_pattern_matches_uses_fnmatch_wildcards(self) -> None:
        mw = TopicRateLimitMiddleware()
        self.assertTrue(mw._topic_matches_pattern('devices/abc/status', 'devices/*/status'))
        self.assertFalse(mw._topic_matches_pattern('users/abc/status', 'devices/*/status'))

    async def test_handle_falls_through_to_default_when_no_match(self) -> None:
        mw = TopicRateLimitMiddleware(default_limit={'max_requests': 10, 'window_seconds': 60})
        next_handler = AsyncMock(return_value='ok')

        with patch.object(mw, '_check_rate_limit', AsyncMock(return_value=(True, 9, 60))):
            result = await mw.handle({'topic': 'unknown/topic'}, next_handler)

        self.assertEqual(result, 'ok')

    async def test_handle_uses_topic_specific_limit_when_matched(self) -> None:
        mw = TopicRateLimitMiddleware(
            topic_limits={'devices/*': {'max_requests': 5, 'window_seconds': 10}},
            default_limit={'max_requests': 100, 'window_seconds': 60},
        )
        next_handler = AsyncMock(return_value='ok')

        with patch(
            'app.middleware.rate_limit.RateLimitMiddleware.handle',
            new=AsyncMock(return_value='topic-specific'),
        ):
            result = await mw.handle({'topic': 'devices/abc'}, next_handler)

        self.assertEqual(result, 'topic-specific')


class ClientRateLimitMiddlewareTests(unittest.TestCase):
    def test_uses_client_id_field(self) -> None:
        mw = ClientRateLimitMiddleware(max_requests=10, client_id_field='device_id')
        self.assertEqual(mw.client_id_field, 'device_id')

    def test_key_generator_from_payload(self) -> None:
        mw = ClientRateLimitMiddleware(max_requests=10, client_id_field='device_id')
        ctx = {'payload': {'device_id': 'sensor-42'}, 'topic': 'devices/sensor-42/status'}
        self.assertEqual(mw._default_key_generator(ctx), 'client:sensor-42')

    def test_key_generator_from_context_when_payload_missing(self) -> None:
        mw = ClientRateLimitMiddleware(max_requests=10, client_id_field='device_id')
        ctx = {'payload': None, 'device_id': 'ctx-id', 'topic': 'x'}
        self.assertEqual(mw._default_key_generator(ctx), 'client:ctx-id')

    def test_key_generator_falls_back_to_topic(self) -> None:
        mw = ClientRateLimitMiddleware(max_requests=10, client_id_field='device_id')
        ctx = {'payload': {}, 'topic': 'fallback/topic'}
        self.assertEqual(mw._default_key_generator(ctx), 'topic:fallback/topic')

    def test_key_generator_handles_non_dict_payload(self) -> None:
        mw = ClientRateLimitMiddleware(max_requests=10, client_id_field='device_id')
        ctx = {'payload': b'binary-blob', 'topic': 'binary/topic'}
        self.assertEqual(mw._default_key_generator(ctx), 'topic:binary/topic')


if __name__ == '__main__':
    unittest.main()
