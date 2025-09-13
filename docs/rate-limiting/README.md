# Rate Limiting

RouteMQ includes advanced rate limiting middleware with multiple strategies and Redis backend support.

## Topics

- [Basic Rate Limiting](basic-rate-limiting.md) - Simple rate limiting setup
- [Rate Limiting Strategies](strategies.md) - Different algorithms and approaches
- [Topic-Specific Limits](topic-specific.md) - Custom limits per topic pattern
- [Client-Based Limiting](client-based.md) - Rate limiting per client
- [Advanced Features](advanced-features.md) - Whitelisting, custom messages, fallbacks

## Quick Overview

```python
from app.middleware.rate_limit import RateLimitMiddleware

# Basic rate limiting - 100 requests per minute
rate_limit = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window"
)

# Apply to routes
router.on("api/{endpoint}", Controller.handle, middleware=[rate_limit])
```

## Rate Limiting Strategies

### 1. Sliding Window (Most Accurate)
Uses Redis sorted sets for precision:
```python
sliding_window = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window"
)
```

### 2. Fixed Window (Simple)
Resets at window boundaries:
```python
fixed_window = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="fixed_window"
)
```

### 3. Token Bucket (Allows Bursts)
Allows burst traffic:
```python
token_bucket = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="token_bucket",
    burst_allowance=50  # Allow up to 150 requests in bursts
)
```

## Advanced Rate Limiting

### Topic-Specific Limits
```python
from app.middleware.rate_limit import TopicRateLimitMiddleware

topic_rate_limit = TopicRateLimitMiddleware(
    topic_limits={
        "sensors/batch/*": {"max_requests": 1000, "window_seconds": 60},
        "sensors/temperature/*": {"max_requests": 100, "window_seconds": 60},
        "devices/control/*": {"max_requests": 10, "window_seconds": 60},
    },
    default_limit={"max_requests": 50, "window_seconds": 60}
)
```

### Client-Based Limits
```python
from app.middleware.rate_limit import ClientRateLimitMiddleware

client_rate_limit = ClientRateLimitMiddleware(
    max_requests=50,
    window_seconds=60,
    client_id_field="client_id",
    strategy="sliding_window"
)
```

### Advanced Features
```python
advanced_rate_limit = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window",
    whitelist=["admin/*", "emergency/*"],  # Bypass rate limiting
    custom_error_message="Too many requests. Please slow down.",
    fallback_enabled=True  # Use memory if Redis is down
)
```

## Next Steps

- [Basic Rate Limiting](basic-rate-limiting.md) - Get started with rate limiting
- [Strategies](strategies.md) - Choose the right algorithm
- [Redis Integration](../redis/README.md) - Redis-powered rate limiting
