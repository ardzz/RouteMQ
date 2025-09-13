# Rate Limiting Strategies

RouteMQ supports multiple rate limiting algorithms, each with different characteristics and use cases. Choose the right strategy based on your application's needs.

## Available Strategies

### 1. Sliding Window (Default)

**Most accurate and recommended for most use cases**

```python
sliding_window = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window"
)
```

#### How It Works

The sliding window algorithm maintains a continuous window that moves with time:

```
Time:     0    15    30    45    60    75    90
Window:   |-------- 60s --------|
          |           |-------- 60s --------|
          |                      |-------- 60s --------|
```

- Tracks exact timestamps of each request
- Continuously slides the time window
- Provides the most accurate rate limiting
- Prevents burst traffic at window boundaries

#### Implementation Details

Uses Redis sorted sets to store request timestamps:

```python
# Redis operations for sliding window
async def _sliding_window_redis(self, redis_key: str, current_time: int):
    # Remove old requests outside the window
    window_start = current_time - self.window_seconds
    await redis_manager.zremrangebyscore(redis_key, 0, window_start)
    
    # Count current requests in window
    current_count = await redis_manager.zcard(redis_key)
    
    if current_count >= self.max_requests:
        return False, 0, self.window_seconds
    
    # Add current request
    await redis_manager.zadd(redis_key, {str(current_time): current_time})
    await redis_manager.expire(redis_key, self.window_seconds + 1)
    
    remaining = self.max_requests - current_count - 1
    return True, remaining, self.window_seconds
```

#### Pros and Cons

**Pros:**
- Most accurate rate limiting
- Smooth traffic distribution
- No burst at window boundaries
- Fair for all users

**Cons:**
- Higher memory usage (stores all timestamps)
- More Redis operations
- Slightly more complex

#### Use Cases

```python
# API endpoints requiring precise control
api_rate_limit = RateLimitMiddleware(
    max_requests=1000,
    window_seconds=3600,  # 1000 requests per hour
    strategy="sliding_window"
)

# Critical system endpoints
critical_rate_limit = RateLimitMiddleware(
    max_requests=10,
    window_seconds=60,    # 10 requests per minute
    strategy="sliding_window"
)
```

### 2. Fixed Window

**Simple and memory-efficient**

```python
fixed_window = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="fixed_window"
)
```

#### How It Works

Fixed window algorithm resets counters at fixed intervals:

```
Time:     0         60        120       180
Window:   |-- 60s --|-- 60s --|-- 60s --|
Resets:   ^         ^         ^         ^
```

- Divides time into fixed windows
- Resets counter at window boundaries
- Simple counter increment/decrement
- Memory efficient

#### Implementation Details

Uses Redis strings with expiration:

```python
# Redis operations for fixed window
async def _fixed_window_redis(self, redis_key: str, current_time: int):
    # Calculate window start
    window_start = (current_time // self.window_seconds) * self.window_seconds
    window_key = f"{redis_key}:{window_start}"
    
    # Get current count
    current_count = await redis_manager.get(window_key) or 0
    current_count = int(current_count)
    
    if current_count >= self.max_requests:
        reset_time = window_start + self.window_seconds - current_time
        return False, 0, max(1, reset_time)
    
    # Increment counter
    pipe = redis_manager.pipeline()
    pipe.incr(window_key)
    pipe.expire(window_key, self.window_seconds + 1)
    await pipe.execute()
    
    remaining = self.max_requests - current_count - 1
    reset_time = window_start + self.window_seconds - current_time
    return True, remaining, max(1, reset_time)
```

#### Pros and Cons

**Pros:**
- Very memory efficient
- Simple implementation
- Fast operations
- Predictable reset times

**Cons:**
- Allows burst traffic at window boundaries
- Less accurate than sliding window
- Can allow 2x limit in worst case

#### Burst Traffic Issue

```
Window 1 (0-60s):   [50 requests at 59s] ✓
Window 2 (60-120s): [50 requests at 61s] ✓
Total in 2 seconds: 100 requests (2x the limit!)
```

#### Use Cases

```python
# High-volume endpoints where bursts are acceptable
bulk_data_rate_limit = RateLimitMiddleware(
    max_requests=10000,
    window_seconds=3600,  # 10k requests per hour
    strategy="fixed_window"
)

# Simple rate limiting for internal services
internal_rate_limit = RateLimitMiddleware(
    max_requests=500,
    window_seconds=60,
    strategy="fixed_window"
)
```

### 3. Token Bucket

**Allows burst traffic with sustained rate limiting**

```python
token_bucket = RateLimitMiddleware(
    max_requests=100,        # Bucket capacity
    window_seconds=60,       # Refill rate (100 tokens per 60s)
    strategy="token_bucket",
    burst_allowance=50       # Extra tokens for bursts
)
```

#### How It Works

Token bucket algorithm allows controlled bursts:

```
Bucket Capacity: 150 tokens (100 + 50 burst)
Refill Rate: 100 tokens per 60 seconds
```

- Bucket starts full of tokens
- Each request consumes one token
- Tokens refill at a steady rate
- Allows bursts when bucket is full

#### Implementation Details

Uses Redis hash to store bucket state:

```python
# Redis operations for token bucket
async def _token_bucket_redis(self, redis_key: str, current_time: int):
    bucket_key = f"{redis_key}:bucket"
    
    # Get current bucket state
    bucket_data = await redis_manager.hmget(bucket_key, 'tokens', 'last_refill')
    
    current_tokens = float(bucket_data[0] or self.max_requests + self.burst_allowance)
    last_refill = float(bucket_data[1] or current_time)
    
    # Calculate tokens to add based on time elapsed
    time_elapsed = current_time - last_refill
    tokens_to_add = (time_elapsed / self.window_seconds) * self.max_requests
    
    # Update token count (don't exceed capacity)
    max_tokens = self.max_requests + self.burst_allowance
    current_tokens = min(max_tokens, current_tokens + tokens_to_add)
    
    if current_tokens < 1:
        # Not enough tokens
        refill_time = (1 - current_tokens) * self.window_seconds / self.max_requests
        return False, 0, int(refill_time) + 1
    
    # Consume one token
    current_tokens -= 1
    
    # Update bucket state
    await redis_manager.hmset(bucket_key, {
        'tokens': current_tokens,
        'last_refill': current_time
    })
    await redis_manager.expire(bucket_key, self.window_seconds * 2)
    
    remaining = int(current_tokens)
    return True, remaining, 0
```

#### Pros and Cons

**Pros:**
- Allows controlled burst traffic
- Smooth average rate limiting
- Good user experience
- Handles irregular traffic well

**Cons:**
- More complex implementation
- Can allow temporary rate spikes
- Requires careful tuning

#### Configuration Examples

```python
# Web API with burst support
web_api_rate_limit = RateLimitMiddleware(
    max_requests=60,         # 1 request per second sustained
    window_seconds=60,
    strategy="token_bucket",
    burst_allowance=30       # Allow 30 extra requests for bursts
)

# File upload endpoint
upload_rate_limit = RateLimitMiddleware(
    max_requests=10,         # 10 uploads per hour
    window_seconds=3600,
    strategy="token_bucket", 
    burst_allowance=5        # Allow 5 extra for burst uploads
)

# Real-time notifications
notification_rate_limit = RateLimitMiddleware(
    max_requests=100,        # 100 notifications per minute
    window_seconds=60,
    strategy="token_bucket",
    burst_allowance=50       # Allow 50 extra for urgent notifications
)
```

## Strategy Comparison

### Performance Comparison

| Strategy | Memory Usage | CPU Usage | Redis Ops | Accuracy |
|----------|--------------|-----------|-----------|----------|
| Sliding Window | High | Medium | High | Highest |
| Fixed Window | Low | Low | Low | Medium |
| Token Bucket | Medium | Medium | Medium | High |

### Traffic Pattern Suitability

#### Steady Traffic
```python
# For consistent, predictable traffic
steady_traffic_limit = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="sliding_window"  # Best for steady traffic
)
```

#### Bursty Traffic
```python
# For applications with burst patterns
bursty_traffic_limit = RateLimitMiddleware(
    max_requests=60,
    window_seconds=60,
    strategy="token_bucket",
    burst_allowance=40  # Handle bursts gracefully
)
```

#### High Volume Traffic
```python
# For high-volume, less sensitive endpoints
high_volume_limit = RateLimitMiddleware(
    max_requests=10000,
    window_seconds=3600,
    strategy="fixed_window"  # Most efficient for high volume
)
```

## Choosing the Right Strategy

### Decision Matrix

**Use Sliding Window when:**
- Accuracy is critical
- Traffic should be evenly distributed
- Burst prevention is important
- Memory usage is not a concern

**Use Fixed Window when:**
- High performance is required
- Memory efficiency is important
- Occasional bursts are acceptable
- Simple implementation is preferred

**Use Token Bucket when:**
- Burst traffic is expected
- User experience is important
- Traffic patterns are irregular
- Some flexibility is needed

### Application-Specific Recommendations

#### REST APIs
```python
# Sliding window for precise control
api_rate_limit = RateLimitMiddleware(
    max_requests=1000,
    window_seconds=3600,
    strategy="sliding_window"
)
```

#### IoT Data Ingestion
```python
# Token bucket for handling device bursts
iot_rate_limit = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    strategy="token_bucket",
    burst_allowance=50
)
```

#### Public Endpoints
```python
# Fixed window for simplicity and performance
public_rate_limit = RateLimitMiddleware(
    max_requests=100,
    window_seconds=3600,
    strategy="fixed_window"
)
```

#### Critical Systems
```python
# Sliding window for maximum protection
critical_rate_limit = RateLimitMiddleware(
    max_requests=10,
    window_seconds=60,
    strategy="sliding_window"
)
```

## Advanced Strategy Configuration

### Hybrid Approach

Combine multiple strategies for different endpoints:

```python
class StrategySelector:
    @staticmethod
    def get_rate_limiter(endpoint_type: str):
        strategies = {
            "critical": RateLimitMiddleware(
                max_requests=10,
                window_seconds=60,
                strategy="sliding_window"
            ),
            "standard": RateLimitMiddleware(
                max_requests=100,
                window_seconds=60,
                strategy="token_bucket",
                burst_allowance=20
            ),
            "bulk": RateLimitMiddleware(
                max_requests=1000,
                window_seconds=60,
                strategy="fixed_window"
            )
        }
        return strategies.get(endpoint_type, strategies["standard"])

# Apply different strategies to different routes
router.on("critical/{action}", 
          CriticalController.handle,
          middleware=[StrategySelector.get_rate_limiter("critical")])

router.on("api/{endpoint}",
          ApiController.handle, 
          middleware=[StrategySelector.get_rate_limiter("standard")])

router.on("bulk/{operation}",
          BulkController.handle,
          middleware=[StrategySelector.get_rate_limiter("bulk")])
```

### Dynamic Strategy Selection

Select strategy based on runtime conditions:

```python
class AdaptiveRateLimitMiddleware(RateLimitMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_threshold = 0.8
        
    async def handle(self, context, next_handler):
        # Check system load
        current_load = await self._get_system_load()
        
        # Switch to more efficient strategy under high load
        if current_load > self.load_threshold:
            original_strategy = self.strategy
            self.strategy = "fixed_window"
            
            try:
                return await super().handle(context, next_handler)
            finally:
                self.strategy = original_strategy
        else:
            return await super().handle(context, next_handler)
    
    async def _get_system_load(self):
        # Implement system load detection
        # Return value between 0.0 and 1.0
        pass
```

## Testing Different Strategies

### Performance Testing

```python
import asyncio
import time
from app.middleware.rate_limit import RateLimitMiddleware

async def test_strategy_performance():
    """Compare performance of different strategies"""
    
    strategies = ["sliding_window", "fixed_window", "token_bucket"]
    results = {}
    
    for strategy in strategies:
        rate_limiter = RateLimitMiddleware(
            max_requests=100,
            window_seconds=60,
            strategy=strategy,
            fallback_enabled=True  # Use memory for testing
        )
        
        # Measure time for 1000 requests
        start_time = time.time()
        
        for i in range(1000):
            context = {'topic': f'test/{i % 10}'}  # 10 different topics
            await rate_limiter._check_rate_limit(f"test:{i % 10}")
        
        end_time = time.time()
        results[strategy] = end_time - start_time
    
    # Print results
    for strategy, duration in results.items():
        print(f"{strategy}: {duration:.3f} seconds")

# Run the test
asyncio.run(test_strategy_performance())
```

### Accuracy Testing

```python
async def test_strategy_accuracy():
    """Test accuracy of different strategies"""
    
    async def simulate_burst_traffic(rate_limiter, burst_size=50):
        """Simulate burst traffic and count allowed requests"""
        allowed_count = 0
        
        for i in range(burst_size):
            context = {'topic': 'test/burst'}
            allowed, _, _ = await rate_limiter._check_rate_limit('test:burst')
            if allowed:
                allowed_count += 1
        
        return allowed_count
    
    # Test each strategy
    for strategy in ["sliding_window", "fixed_window", "token_bucket"]:
        rate_limiter = RateLimitMiddleware(
            max_requests=10,
            window_seconds=60,
            strategy=strategy,
            burst_allowance=5 if strategy == "token_bucket" else 0
        )
        
        allowed = await simulate_burst_traffic(rate_limiter)
        expected = 15 if strategy == "token_bucket" else 10
        
        print(f"{strategy}: {allowed}/{expected} requests allowed")
```

## Next Steps

- [Topic-Specific Limits](topic-specific.md) - Configure different limits per topic
- [Client-Based Limiting](client-based.md) - Rate limit by client ID
- [Advanced Features](advanced-features.md) - Whitelisting and custom configurations
- [Basic Rate Limiting](basic-rate-limiting.md) - Return to basics if needed
