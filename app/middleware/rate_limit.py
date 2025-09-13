import time
from typing import Dict, Optional, List

from core.middleware import Middleware
from core.redis_manager import redis_manager


class RateLimitMiddleware(Middleware):
    """
    Rate limiting middleware that uses Redis for distributed rate limiting.
    Supports multiple rate limiting strategies including sliding window and token bucket.
    """

    def __init__(self,
                 max_requests: int = 100,
                 window_seconds: int = 60,
                 strategy: str = "sliding_window",
                 key_generator: Optional[callable] = None,
                 burst_allowance: Optional[int] = None,
                 redis_key_prefix: str = "rate_limit",
                 fallback_enabled: bool = True,
                 block_duration: Optional[int] = None,
                 whitelist: Optional[List[str]] = None,
                 custom_error_message: Optional[str] = None):
        """
        Initialize rate limiting middleware.

        Args:
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds
            strategy: Rate limiting strategy ('sliding_window', 'fixed_window', 'token_bucket')
            key_generator: Custom function to generate rate limit keys
            burst_allowance: Additional requests allowed for burst traffic (token bucket only)
            redis_key_prefix: Prefix for Redis keys
            fallback_enabled: Enable in-memory fallback when Redis is unavailable
            block_duration: Duration to block after limit exceeded (None = window_seconds)
            whitelist: List of patterns/keys to whitelist (bypass rate limiting)
            custom_error_message: Custom error message for rate limit exceeded
        """
        super().__init__()

        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.strategy = strategy.lower()
        self.key_generator = key_generator or self._default_key_generator
        self.burst_allowance = burst_allowance or 0
        self.redis_key_prefix = redis_key_prefix
        self.fallback_enabled = fallback_enabled
        self.block_duration = block_duration or window_seconds
        self.whitelist = set(whitelist or [])
        self.custom_error_message = custom_error_message

        # In-memory fallback storage
        self._memory_cache: Dict[str, Dict] = {}
        self._cache_cleanup_interval = 60  # seconds
        self._last_cleanup = time.time()

        # Validate strategy
        if self.strategy not in ['sliding_window', 'fixed_window', 'token_bucket']:
            raise ValueError(f"Invalid strategy: {self.strategy}")

        self.logger.info(f"Rate limit middleware initialized: {max_requests} req/{window_seconds}s, strategy: {strategy}")

    def _default_key_generator(self, context: Dict) -> str:
        """
        Default key generator based on topic.

        Args:
            context: Message context

        Returns:
            Rate limit key
        """
        topic = context.get('topic', 'unknown')
        # Use topic as the key - you can customize this for client-based limiting
        return f"topic:{topic}"

    def _is_whitelisted(self, key: str) -> bool:
        """
        Check if key is whitelisted.

        Args:
            key: Rate limit key

        Returns:
            True if whitelisted
        """
        for pattern in self.whitelist:
            if pattern in key or key.startswith(pattern):
                return True
        return False

    async def handle(self, context: Dict, next_handler):
        """
        Handle rate limiting logic.

        Args:
            context: Message context
            next_handler: Next handler in the chain

        Returns:
            Handler result or rate limit error
        """
        # Generate rate limit key
        rate_limit_key = self.key_generator(context)

        # Check whitelist
        if self._is_whitelisted(rate_limit_key):
            self.logger.debug(f"Whitelisted key: {rate_limit_key}")
            return await next_handler(context)

        # Apply rate limiting
        allowed, remaining, reset_time = await self._check_rate_limit(rate_limit_key)

        if not allowed:
            error_message = self.custom_error_message or f"Rate limit exceeded. Try again in {reset_time} seconds."
            self.logger.warning(f"Rate limit exceeded for key: {rate_limit_key}")

            # Add rate limit info to context for potential custom handling
            context['rate_limit'] = {
                'exceeded': True,
                'key': rate_limit_key,
                'remaining': remaining,
                'reset_time': reset_time,
                'max_requests': self.max_requests,
                'window_seconds': self.window_seconds
            }

            return {
                "error": "rate_limit_exceeded",
                "message": error_message,
                "rate_limit": {
                    "max_requests": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "remaining": remaining,
                    "reset_time": reset_time
                }
            }

        # Add rate limit info to context
        context['rate_limit'] = {
            'exceeded': False,
            'key': rate_limit_key,
            'remaining': remaining,
            'reset_time': reset_time,
            'max_requests': self.max_requests,
            'window_seconds': self.window_seconds
        }

        self.logger.debug(f"Rate limit check passed for key: {rate_limit_key}, remaining: {remaining}")

        # Continue to next handler
        return await next_handler(context)

    async def _check_rate_limit(self, key: str) -> tuple[bool, int, int]:
        """
        Check rate limit for the given key.

        Args:
            key: Rate limit key

        Returns:
            Tuple of (allowed, remaining_requests, reset_time_seconds)
        """
        redis_key = f"{self.redis_key_prefix}:{key}"

        # Try Redis first
        if redis_manager.is_enabled():
            try:
                return await self._check_rate_limit_redis(redis_key)
            except Exception as e:
                self.logger.error(f"Redis rate limit check failed: {e}")
                if not self.fallback_enabled:
                    # If fallback is disabled, allow the request
                    return True, self.max_requests - 1, self.window_seconds

        # Fallback to in-memory rate limiting
        if self.fallback_enabled:
            return await self._check_rate_limit_memory(key)

        # If no fallback, allow the request
        return True, self.max_requests - 1, self.window_seconds

    async def _check_rate_limit_redis(self, redis_key: str) -> tuple[bool, int, int]:
        """
        Redis-based rate limiting.

        Args:
            redis_key: Redis key for rate limiting

        Returns:
            Tuple of (allowed, remaining_requests, reset_time_seconds)
        """
        current_time = int(time.time())

        if self.strategy == "sliding_window":
            return await self._sliding_window_redis(redis_key, current_time)
        elif self.strategy == "fixed_window":
            return await self._fixed_window_redis(redis_key, current_time)
        elif self.strategy == "token_bucket":
            return await self._token_bucket_redis(redis_key, current_time)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    async def _sliding_window_redis(self, redis_key: str, current_time: int) -> tuple[bool, int, int]:
        """
        Sliding window rate limiting using Redis sorted sets.
        """
        window_start = current_time - self.window_seconds
        pipe = redis_manager.get_client().pipeline()

        # Remove old entries
        pipe.zremrangebyscore(redis_key, 0, window_start)

        # Count current requests in window
        pipe.zcard(redis_key)

        # Add current request
        pipe.zadd(redis_key, {str(current_time): current_time})

        # Set expiration
        pipe.expire(redis_key, self.window_seconds + 1)

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= self.max_requests:
            # Get the oldest entry to calculate reset time
            oldest_entries = await redis_manager.get_client().zrange(redis_key, 0, 0, withscores=True)
            if oldest_entries:
                oldest_time = int(oldest_entries[0][1])
                reset_time = oldest_time + self.window_seconds - current_time
            else:
                reset_time = self.window_seconds

            # Remove the request we just added since it's not allowed
            await redis_manager.get_client().zrem(redis_key, str(current_time))

            return False, 0, max(reset_time, 1)

        remaining = self.max_requests - current_count - 1
        return True, remaining, self.window_seconds

    async def _fixed_window_redis(self, redis_key: str, current_time: int) -> tuple[bool, int, int]:
        """
        Fixed window rate limiting using Redis.
        """
        window_key = f"{redis_key}:{current_time // self.window_seconds}"

        # Increment counter
        current_count = await redis_manager.get_client().incr(window_key)

        if current_count == 1:
            # Set expiration on first request
            await redis_manager.get_client().expire(window_key, self.window_seconds)

        if current_count > self.max_requests:
            # Calculate reset time
            window_start = (current_time // self.window_seconds) * self.window_seconds
            reset_time = window_start + self.window_seconds - current_time
            return False, 0, max(reset_time, 1)

        remaining = self.max_requests - current_count
        window_start = (current_time // self.window_seconds) * self.window_seconds
        reset_time = window_start + self.window_seconds - current_time

        return True, remaining, reset_time

    async def _token_bucket_redis(self, redis_key: str, current_time: int) -> tuple[bool, int, int]:
        """
        Token bucket rate limiting using Redis.
        """
        bucket_key = f"{redis_key}:bucket"
        last_refill_key = f"{redis_key}:last_refill"

        # Get current bucket state
        pipe = redis_manager.get_client().pipeline()
        pipe.get(bucket_key)
        pipe.get(last_refill_key)
        results = await pipe.execute()

        current_tokens = int(results[0] or self.max_requests)
        last_refill = int(results[1] or current_time)

        # Calculate tokens to add based on time elapsed
        time_elapsed = current_time - last_refill
        tokens_to_add = int(time_elapsed * (self.max_requests / self.window_seconds))

        # Refill tokens (max capacity = max_requests + burst_allowance)
        max_capacity = self.max_requests + self.burst_allowance
        current_tokens = min(max_capacity, current_tokens + tokens_to_add)

        if current_tokens < 1:
            # No tokens available
            reset_time = int(self.window_seconds / self.max_requests)  # Time to get 1 token
            return False, 0, reset_time

        # Consume one token
        current_tokens -= 1

        # Update bucket state
        pipe = redis_manager.get_client().pipeline()
        pipe.set(bucket_key, current_tokens, ex=self.window_seconds * 2)
        pipe.set(last_refill_key, current_time, ex=self.window_seconds * 2)
        await pipe.execute()

        reset_time = int((max_capacity - current_tokens) * (self.window_seconds / self.max_requests))
        return True, current_tokens, reset_time

    async def _check_rate_limit_memory(self, key: str) -> tuple[bool, int, int]:
        """
        In-memory fallback rate limiting.
        """
        current_time = time.time()

        # Cleanup old entries periodically
        if current_time - self._last_cleanup > self._cache_cleanup_interval:
            await self._cleanup_memory_cache(current_time)

        if key not in self._memory_cache:
            self._memory_cache[key] = {
                'requests': [],
                'created': current_time
            }

        cache_entry = self._memory_cache[key]

        if self.strategy == "sliding_window":
            return self._sliding_window_memory(cache_entry, current_time)
        elif self.strategy == "fixed_window":
            return self._fixed_window_memory(cache_entry, current_time)
        elif self.strategy == "token_bucket":
            return self._token_bucket_memory(cache_entry, current_time)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}, pick from sliding_window, fixed_window, token_bucket!")

    def _sliding_window_memory(self, cache_entry: Dict, current_time: float) -> tuple[bool, int, int]:
        """Sliding window rate limiting in memory."""
        window_start = current_time - self.window_seconds

        # Remove old requests
        cache_entry['requests'] = [req_time for req_time in cache_entry['requests'] if req_time > window_start]

        if len(cache_entry['requests']) >= self.max_requests:
            oldest_request = min(cache_entry['requests'])
            reset_time = int(oldest_request + self.window_seconds - current_time)
            return False, 0, max(reset_time, 1)

        # Add current request
        cache_entry['requests'].append(current_time)
        remaining = self.max_requests - len(cache_entry['requests'])

        return True, remaining, self.window_seconds

    def _fixed_window_memory(self, cache_entry: Dict, current_time: float) -> tuple[bool, int, int]:
        """Fixed window rate limiting in memory."""
        window_start = int(current_time // self.window_seconds) * self.window_seconds

        # Reset counter if we're in a new window
        if cache_entry.get('window_start', 0) != window_start:
            cache_entry['requests'] = []
            cache_entry['window_start'] = window_start

        if len(cache_entry['requests']) >= self.max_requests:
            reset_time = int(window_start + self.window_seconds - current_time)
            return False, 0, max(reset_time, 1)

        # Add current request
        cache_entry['requests'].append(current_time)
        remaining = self.max_requests - len(cache_entry['requests'])
        reset_time = int(window_start + self.window_seconds - current_time)

        return True, remaining, reset_time

    def _token_bucket_memory(self, cache_entry: Dict, current_time: float) -> tuple[bool, int, int]:
        """Token bucket rate limiting in memory."""
        if 'tokens' not in cache_entry:
            cache_entry['tokens'] = self.max_requests
            cache_entry['last_refill'] = current_time

        # Calculate tokens to add
        time_elapsed = current_time - cache_entry['last_refill']
        tokens_to_add = time_elapsed * (self.max_requests / self.window_seconds)

        max_capacity = self.max_requests + self.burst_allowance
        cache_entry['tokens'] = min(max_capacity, cache_entry['tokens'] + tokens_to_add)
        cache_entry['last_refill'] = current_time

        if cache_entry['tokens'] < 1:
            reset_time = int(self.window_seconds / self.max_requests)
            return False, 0, reset_time

        # Consume token
        cache_entry['tokens'] -= 1
        reset_time = int((max_capacity - cache_entry['tokens']) * (self.window_seconds / self.max_requests))

        return True, int(cache_entry['tokens']), reset_time

    async def _cleanup_memory_cache(self, current_time: float):
        """Clean up old entries from memory cache."""
        keys_to_remove = []

        for key, cache_entry in self._memory_cache.items():
            # Remove entries older than 2 * window_seconds
            if current_time - cache_entry.get('created', 0) > (self.window_seconds * 2):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._memory_cache[key]

        self._last_cleanup = current_time

        if keys_to_remove:
            self.logger.debug(f"Cleaned up {len(keys_to_remove)} old rate limit entries from memory")


class TopicRateLimitMiddleware(RateLimitMiddleware):
    """
    Rate limiting middleware that limits by MQTT topic.
    """

    def __init__(self, topic_limits: Dict[str, Dict] = None, default_limit: Dict = None, **kwargs):
        """
        Initialize topic-based rate limiting.

        Args:
            topic_limits: Dictionary mapping topic patterns to rate limit configs
            default_limit: Default rate limit config for unmatched topics
            **kwargs: Additional arguments passed to RateLimitMiddleware
        """
        # Use default limit or fallback values
        default_config = default_limit or {"max_requests": 100, "window_seconds": 60}
        super().__init__(**{**default_config, **kwargs})

        self.topic_limits = topic_limits or {}
        self.default_limit = default_config

        self.logger.info(f"Topic rate limit middleware initialized with {len(self.topic_limits)} topic-specific limits")

    async def handle(self, context: Dict, next_handler):
        """Handle topic-specific rate limiting."""
        topic = context.get('topic', '')

        # Find matching topic limit
        topic_config = None
        for pattern, config in self.topic_limits.items():
            if self._topic_matches_pattern(topic, pattern):
                topic_config = config
                break

        if topic_config:
            # Create temporary middleware with topic-specific config
            temp_middleware = RateLimitMiddleware(
                max_requests=topic_config.get('max_requests', self.default_limit['max_requests']),
                window_seconds=topic_config.get('window_seconds', self.default_limit['window_seconds']),
                strategy=topic_config.get('strategy', self.strategy),
                burst_allowance=topic_config.get('burst_allowance', self.burst_allowance),
                redis_key_prefix=self.redis_key_prefix,
                fallback_enabled=self.fallback_enabled,
                block_duration=topic_config.get('block_duration', self.block_duration),
                whitelist=topic_config.get('whitelist', []),
                custom_error_message=topic_config.get('custom_error_message', self.custom_error_message)
            )

            return await temp_middleware.handle(context, next_handler)

        # Use default rate limiting
        return await super().handle(context, next_handler)

    def _topic_matches_pattern(self, topic: str, pattern: str) -> bool:
        """Check if topic matches pattern (supports wildcards)."""
        import fnmatch
        return fnmatch.fnmatch(topic, pattern)


class ClientRateLimitMiddleware(RateLimitMiddleware):
    """
    Rate limiting middleware that limits by client identifier.
    Requires client information in the message payload or context.
    """

    def __init__(self, client_id_field: str = "client_id", **kwargs):
        """
        Initialize client-based rate limiting.

        Args:
            client_id_field: Field name to extract client ID from payload/context
            **kwargs: Additional arguments passed to RateLimitMiddleware
        """
        super().__init__(**kwargs)
        self.client_id_field = client_id_field

    def _default_key_generator(self, context: Dict) -> str:
        """Generate key based on client ID."""
        # Try to get client ID from payload first, then context
        payload = context.get('payload', {})
        client_id = None

        if isinstance(payload, dict):
            client_id = payload.get(self.client_id_field)

        if not client_id:
            client_id = context.get(self.client_id_field)

        if not client_id:
            # Fallback to topic-based limiting
            topic = context.get('topic', 'unknown')
            return f"topic:{topic}"

        return f"client:{client_id}"
