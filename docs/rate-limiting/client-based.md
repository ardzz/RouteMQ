# Client-Based Rate Limiting

Implement rate limiting based on client identity rather than topic patterns, providing per-client quotas and preventing individual clients from overwhelming your system.

## Overview

Client-based rate limiting tracks and limits requests per individual client, identified by:

- Client ID from MQTT connection
- User ID from authentication
- API key or token
- Device ID from IoT devices
- IP address (with caution)
- Custom client identifiers

## Basic Client-Based Rate Limiting

### Custom Key Generator for Client-Based Limiting

```python
from app.middleware.rate_limit import RateLimitMiddleware

def client_based_key_generator(context):
    """Generate rate limit keys based on client identity"""
    
    # Try different client identification methods in order of preference
    
    # 1. Authenticated user ID (most reliable)
    user_id = context.get('user_id')
    if user_id:
        return f"user:{user_id}"
    
    # 2. Device ID from authenticated device
    device_id = context.get('device_id')
    if device_id:
        return f"device:{device_id}"
    
    # 3. API key identifier
    auth_data = context.get('auth_data', {})
    api_key_id = auth_data.get('key_id')
    if api_key_id:
        return f"api_key:{api_key_id}"
    
    # 4. MQTT client ID
    client = context.get('client')
    if client and hasattr(client, '_client_id'):
        return f"mqtt_client:{client._client_id}"
    
    # 5. Fallback to topic-based (if no client info available)
    topic = context.get('topic', 'unknown')
    return f"topic:{topic}"

# Create client-based rate limiter
client_rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=3600,  # 100 requests per hour per client
    key_generator=client_based_key_generator,
    strategy="sliding_window"
)

# Apply to routes
router.on("api/{endpoint}", 
          ApiController.handle,
          middleware=[client_rate_limiter])
```

### Dedicated Client Rate Limiting Middleware

```python
from typing import Dict, Any, Optional, Callable
from app.middleware.rate_limit import RateLimitMiddleware

class ClientRateLimitMiddleware(RateLimitMiddleware):
    """Specialized rate limiting middleware for client-based limiting"""
    
    def __init__(self,
                 max_requests: int = 100,
                 window_seconds: int = 3600,
                 client_id_extractors: List[Callable] = None,
                 anonymous_limit: Dict[str, Any] = None,
                 per_client_limits: Dict[str, Dict[str, Any]] = None,
                 *args, **kwargs):
        """
        Initialize client-based rate limiting.
        
        Args:
            max_requests: Default max requests per client
            window_seconds: Time window in seconds
            client_id_extractors: List of functions to extract client ID
            anonymous_limit: Rate limit for anonymous/unidentified clients
            per_client_limits: Custom limits for specific clients
        """
        super().__init__(max_requests, window_seconds, *args, **kwargs)
        
        self.client_id_extractors = client_id_extractors or [
            self._extract_user_id,
            self._extract_device_id,
            self._extract_api_key_id,
            self._extract_mqtt_client_id
        ]
        
        self.anonymous_limit = anonymous_limit or {
            "max_requests": max_requests // 10,  # 10x stricter for anonymous
            "window_seconds": window_seconds
        }
        
        self.per_client_limits = per_client_limits or {}
        
        # Override key generator
        self.key_generator = self._client_key_generator
    
    def _extract_user_id(self, context: Dict[str, Any]) -> Optional[str]:
        """Extract user ID from authentication context"""
        user_id = context.get('user_id')
        if user_id:
            return f"user:{user_id}"
        return None
    
    def _extract_device_id(self, context: Dict[str, Any]) -> Optional[str]:
        """Extract device ID from context"""
        device_id = context.get('device_id')
        if device_id:
            return f"device:{device_id}"
        return None
    
    def _extract_api_key_id(self, context: Dict[str, Any]) -> Optional[str]:
        """Extract API key ID from authentication data"""
        auth_data = context.get('auth_data', {})
        key_id = auth_data.get('key_id')
        if key_id:
            return f"api_key:{key_id}"
        return None
    
    def _extract_mqtt_client_id(self, context: Dict[str, Any]) -> Optional[str]:
        """Extract MQTT client ID"""
        client = context.get('client')
        if client and hasattr(client, '_client_id'):
            return f"mqtt_client:{client._client_id}"
        return None
    
    def _client_key_generator(self, context: Dict[str, Any]) -> str:
        """Generate client-based rate limit key"""
        
        # Try each extractor in order
        for extractor in self.client_id_extractors:
            client_id = extractor(context)
            if client_id:
                return client_id
        
        # No client ID found - use anonymous key
        return "anonymous"
    
    def _get_client_limits(self, client_id: str) -> Dict[str, Any]:
        """Get rate limits for specific client"""
        
        # Check for client-specific limits
        if client_id in self.per_client_limits:
            return self.per_client_limits[client_id]
        
        # Check for anonymous clients
        if client_id == "anonymous":
            return self.anonymous_limit
        
        # Return default limits
        return {
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "strategy": self.strategy
        }
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Handle client-based rate limiting"""
        
        # Get client ID
        client_id = self._client_key_generator(context)
        
        # Get client-specific limits
        client_limits = self._get_client_limits(client_id)
        
        # Temporarily override limits
        original_max_requests = self.max_requests
        original_window_seconds = self.window_seconds
        original_strategy = self.strategy
        
        self.max_requests = client_limits.get("max_requests", self.max_requests)
        self.window_seconds = client_limits.get("window_seconds", self.window_seconds)
        self.strategy = client_limits.get("strategy", self.strategy)
        
        try:
            # Add client ID to context for logging/monitoring
            context['rate_limit_client_id'] = client_id
            
            return await super().handle(context, next_handler)
        finally:
            # Restore original limits
            self.max_requests = original_max_requests
            self.window_seconds = original_window_seconds
            self.strategy = original_strategy

# Usage example
client_limiter = ClientRateLimitMiddleware(
    max_requests=1000,        # Default: 1000 requests per hour
    window_seconds=3600,
    anonymous_limit={
        "max_requests": 50,   # Anonymous users: 50 requests per hour
        "window_seconds": 3600
    },
    per_client_limits={
        "user:premium_user_123": {
            "max_requests": 10000,  # Premium users get higher limits
            "window_seconds": 3600
        },
        "device:critical_sensor_456": {
            "max_requests": 5000,   # Critical devices get higher limits
            "window_seconds": 3600
        }
    }
)
```

## Advanced Client-Based Patterns

### Tiered Client Rate Limiting

```python
class TieredClientRateLimitMiddleware(ClientRateLimitMiddleware):
    """Rate limiting with client tiers/subscription levels"""
    
    def __init__(self, tier_configs: Dict[str, Dict], 
                 tier_resolver: Callable = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tier_configs = tier_configs
        self.tier_resolver = tier_resolver or self._default_tier_resolver
    
    def _default_tier_resolver(self, context: Dict[str, Any]) -> str:
        """Resolve client tier from context"""
        
        # Check user tier
        user_data = context.get('user_data', {})
        if user_data:
            return user_data.get('tier', 'free')
        
        # Check device tier
        device_data = context.get('device_data', {})
        if device_data:
            return device_data.get('tier', 'standard')
        
        # Check API key tier
        auth_data = context.get('auth_data', {})
        if auth_data:
            return auth_data.get('tier', 'basic')
        
        return 'free'  # Default tier
    
    def _get_client_limits(self, client_id: str) -> Dict[str, Any]:
        """Get limits based on client tier"""
        
        # For tier-based limiting, we need the context
        # This is a simplified version - in practice, you'd pass context
        return self.tier_configs.get('standard', {
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds
        })
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Handle tier-based rate limiting"""
        
        # Resolve client tier
        client_tier = self.tier_resolver(context)
        tier_config = self.tier_configs.get(client_tier, self.tier_configs.get('free'))
        
        # Override configuration with tier-specific limits
        original_max_requests = self.max_requests
        original_window_seconds = self.window_seconds
        original_strategy = self.strategy
        
        self.max_requests = tier_config.get("max_requests", self.max_requests)
        self.window_seconds = tier_config.get("window_seconds", self.window_seconds)
        self.strategy = tier_config.get("strategy", self.strategy)
        
        try:
            context['client_tier'] = client_tier
            return await super().handle(context, next_handler)
        finally:
            self.max_requests = original_max_requests
            self.window_seconds = original_window_seconds
            self.strategy = original_strategy

# Tier-based configuration
tier_limiter = TieredClientRateLimitMiddleware(
    tier_configs={
        'free': {
            "max_requests": 100,
            "window_seconds": 3600,
            "strategy": "fixed_window"
        },
        'basic': {
            "max_requests": 1000,
            "window_seconds": 3600,
            "strategy": "sliding_window"
        },
        'premium': {
            "max_requests": 10000,
            "window_seconds": 3600,
            "strategy": "token_bucket",
            "burst_allowance": 2000
        },
        'enterprise': {
            "max_requests": 100000,
            "window_seconds": 3600,
            "strategy": "token_bucket",
            "burst_allowance": 20000
        }
    }
)
```

### Multi-Dimensional Client Rate Limiting

```python
class MultiDimensionalClientRateLimitMiddleware(ClientRateLimitMiddleware):
    """Rate limiting across multiple dimensions per client"""
    
    def __init__(self, dimensions: Dict[str, Dict], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dimensions = dimensions
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Check rate limits across multiple dimensions"""
        
        client_id = self._client_key_generator(context)
        
        # Check each dimension
        for dimension_name, dimension_config in self.dimensions.items():
            dimension_key = self._generate_dimension_key(client_id, dimension_name, context)
            
            # Create temporary rate limiter for this dimension
            dimension_limiter = RateLimitMiddleware(
                max_requests=dimension_config["max_requests"],
                window_seconds=dimension_config["window_seconds"],
                strategy=dimension_config.get("strategy", "sliding_window"),
                key_generator=lambda ctx: dimension_key
            )
            
            # Check this dimension's rate limit
            allowed, remaining, reset_time = await dimension_limiter._check_rate_limit(dimension_key)
            
            if not allowed:
                return {
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {dimension_name}",
                    "dimension": dimension_name,
                    "rate_limit": {
                        "max_requests": dimension_config["max_requests"],
                        "window_seconds": dimension_config["window_seconds"],
                        "remaining": remaining,
                        "reset_time": reset_time
                    }
                }
        
        # All dimensions passed, continue
        return await next_handler(context)
    
    def _generate_dimension_key(self, client_id: str, dimension: str, context: Dict) -> str:
        """Generate rate limit key for specific dimension"""
        
        if dimension == "global":
            return f"{client_id}:global"
        elif dimension == "per_topic":
            topic = context.get('topic', 'unknown')
            return f"{client_id}:topic:{topic}"
        elif dimension == "per_endpoint":
            endpoint = context.get('params', {}).get('endpoint', 'unknown')
            return f"{client_id}:endpoint:{endpoint}"
        else:
            return f"{client_id}:{dimension}"

# Multi-dimensional rate limiting
multi_dim_limiter = MultiDimensionalClientRateLimitMiddleware(
    dimensions={
        "global": {
            "max_requests": 10000,    # 10k requests per hour globally
            "window_seconds": 3600
        },
        "per_topic": {
            "max_requests": 1000,     # 1k requests per topic per hour
            "window_seconds": 3600
        },
        "per_minute": {
            "max_requests": 100,      # 100 requests per minute
            "window_seconds": 60
        }
    }
)
```

## Client Identification Strategies

### Enhanced Client ID Extraction

```python
class EnhancedClientIdentifier:
    """Advanced client identification with fallback strategies"""
    
    def __init__(self, identification_priority: List[str] = None):
        self.identification_priority = identification_priority or [
            "authenticated_user",
            "authenticated_device", 
            "api_key",
            "mqtt_client_id",
            "session_id",
            "ip_address"  # Use with caution
        ]
    
    def extract_client_id(self, context: Dict[str, Any]) -> str:
        """Extract client ID using priority-based strategy"""
        
        for method in self.identification_priority:
            client_id = self._extract_by_method(method, context)
            if client_id:
                return client_id
        
        return "anonymous"
    
    def _extract_by_method(self, method: str, context: Dict[str, Any]) -> Optional[str]:
        """Extract client ID using specific method"""
        
        if method == "authenticated_user":
            user_id = context.get('user_id')
            if user_id:
                return f"user:{user_id}"
        
        elif method == "authenticated_device":
            device_id = context.get('device_id')
            if device_id:
                return f"device:{device_id}"
        
        elif method == "api_key":
            auth_data = context.get('auth_data', {})
            key_id = auth_data.get('key_id')
            if key_id:
                return f"api_key:{key_id}"
        
        elif method == "mqtt_client_id":
            client = context.get('client')
            if client and hasattr(client, '_client_id'):
                client_id = client._client_id
                # Validate client ID format
                if len(client_id) > 0 and len(client_id) < 100:
                    return f"mqtt_client:{client_id}"
        
        elif method == "session_id":
            session_id = context.get('session_id')
            if session_id:
                return f"session:{session_id}"
        
        elif method == "ip_address":
            # Use IP address as last resort (with caution)
            ip_address = context.get('client_ip')
            if ip_address and not self._is_internal_ip(ip_address):
                return f"ip:{ip_address}"
        
        return None
    
    def _is_internal_ip(self, ip_address: str) -> bool:
        """Check if IP address is internal/private"""
        # Simple check for private IP ranges
        return (ip_address.startswith('192.168.') or 
                ip_address.startswith('10.') or
                ip_address.startswith('172.16.') or
                ip_address == '127.0.0.1')

# Usage with enhanced identification
enhanced_identifier = EnhancedClientIdentifier()

def enhanced_client_key_generator(context):
    return enhanced_identifier.extract_client_id(context)

enhanced_client_limiter = RateLimitMiddleware(
    max_requests=1000,
    window_seconds=3600,
    key_generator=enhanced_client_key_generator
)
```

### Client Fingerprinting

```python
import hashlib
import json

class ClientFingerprintIdentifier:
    """Identify clients using fingerprinting techniques"""
    
    def generate_fingerprint(self, context: Dict[str, Any]) -> str:
        """Generate client fingerprint from available data"""
        
        fingerprint_data = {}
        
        # MQTT client information
        client = context.get('client')
        if client:
            fingerprint_data['client_id'] = getattr(client, '_client_id', '')
            fingerprint_data['keep_alive'] = getattr(client, '_keepalive', 0)
        
        # Message patterns
        topic = context.get('topic', '')
        fingerprint_data['topic_pattern'] = self._normalize_topic(topic)
        
        # Payload characteristics
        payload = context.get('payload', {})
        fingerprint_data['payload_structure'] = self._analyze_payload_structure(payload)
        
        # Timing patterns (if available)
        timestamp = context.get('timestamp', time.time())
        fingerprint_data['hour_of_day'] = int(timestamp) % 86400 // 3600
        
        # Generate hash
        fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
        fingerprint_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()[:16]
        
        return f"fingerprint:{fingerprint_hash}"
    
    def _normalize_topic(self, topic: str) -> str:
        """Normalize topic to pattern"""
        parts = topic.split('/')
        # Replace variable parts with placeholders
        normalized_parts = []
        for part in parts:
            if part.isdigit():
                normalized_parts.append('<number>')
            elif len(part) > 10 and part.isalnum():
                normalized_parts.append('<id>')
            else:
                normalized_parts.append(part)
        return '/'.join(normalized_parts)
    
    def _analyze_payload_structure(self, payload: Any) -> str:
        """Analyze payload structure for fingerprinting"""
        if isinstance(payload, dict):
            keys = sorted(payload.keys())
            return f"dict:{','.join(keys[:5])}"  # First 5 keys
        elif isinstance(payload, list):
            return f"list:{len(payload)}"
        elif isinstance(payload, str):
            return f"string:{len(payload)}"
        else:
            return f"type:{type(payload).__name__}"

# Usage with fingerprinting
fingerprint_identifier = ClientFingerprintIdentifier()

def fingerprint_key_generator(context):
    # Try authenticated methods first
    authenticated_id = enhanced_identifier.extract_client_id(context)
    if authenticated_id != "anonymous":
        return authenticated_id
    
    # Fall back to fingerprinting
    return fingerprint_identifier.generate_fingerprint(context)

fingerprint_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=3600,
    key_generator=fingerprint_key_generator
)
```

## Use Cases and Examples

### API Rate Limiting by User

```python
# Per-user API rate limiting
user_api_limiter = ClientRateLimitMiddleware(
    max_requests=1000,      # 1000 API calls per hour per user
    window_seconds=3600,
    anonymous_limit={
        "max_requests": 50, # Anonymous users limited to 50 calls
        "window_seconds": 3600
    },
    per_client_limits={
        "user:admin": {
            "max_requests": 10000,  # Admins get higher limits
            "window_seconds": 3600
        }
    }
)

# Apply to API routes with authentication middleware
api_middleware = [
    AuthenticationMiddleware(),  # Provides user_id in context
    user_api_limiter
]

router.on("api/{endpoint}", 
          ApiController.handle,
          middleware=api_middleware)
```

### IoT Device Rate Limiting

```python
# Per-device rate limiting for IoT
device_limiter = ClientRateLimitMiddleware(
    max_requests=1000,      # 1000 messages per hour per device
    window_seconds=3600,
    client_id_extractors=[
        lambda ctx: f"device:{ctx.get('device_id')}" if ctx.get('device_id') else None,
        lambda ctx: f"mqtt_client:{ctx.get('client')._client_id}" if ctx.get('client') else None
    ],
    per_client_limits={
        "device:critical_sensor_001": {
            "max_requests": 10000,  # Critical devices get higher limits
            "window_seconds": 3600,
            "strategy": "token_bucket",
            "burst_allowance": 1000
        }
    }
)

# Apply to device routes
router.on("devices/{device_id}/telemetry",
          DeviceController.handle_telemetry,
          middleware=[device_limiter])
```

### Multi-Tenant Rate Limiting

```python
# Per-tenant client rate limiting
def tenant_client_key_generator(context):
    """Generate client keys that include tenant information"""
    
    # Extract tenant from authentication or topic
    tenant_id = context.get('tenant_id') or context.get('topic', '').split('/')[0]
    
    # Extract client within tenant
    user_id = context.get('user_id')
    if user_id:
        return f"tenant:{tenant_id}:user:{user_id}"
    
    device_id = context.get('device_id')
    if device_id:
        return f"tenant:{tenant_id}:device:{device_id}"
    
    return f"tenant:{tenant_id}:anonymous"

tenant_limiter = RateLimitMiddleware(
    max_requests=1000,
    window_seconds=3600,
    key_generator=tenant_client_key_generator
)
```

## Testing Client-Based Rate Limiting

### Unit Testing

```python
import pytest
from unittest.mock import Mock

@pytest.mark.asyncio
async def test_client_based_rate_limiting():
    """Test rate limiting by client ID"""
    
    client_limiter = ClientRateLimitMiddleware(
        max_requests=3,
        window_seconds=60,
        fallback_enabled=True  # Use memory for testing
    )
    
    # Test different clients
    client1_context = {'user_id': 'user1', 'topic': 'test'}
    client2_context = {'user_id': 'user2', 'topic': 'test'}
    
    handler = Mock(return_value="success")
    
    # Client 1: 3 requests should pass
    for i in range(3):
        result = await client_limiter.handle(client1_context.copy(), handler)
        assert result == "success"
    
    # Client 1: 4th request should be blocked
    result = await client_limiter.handle(client1_context.copy(), handler)
    assert result['error'] == 'rate_limit_exceeded'
    
    # Client 2: should still have full quota
    result = await client_limiter.handle(client2_context.copy(), handler)
    assert result == "success"

@pytest.mark.asyncio
async def test_tiered_client_rate_limiting():
    """Test tier-based rate limiting"""
    
    def tier_resolver(context):
        user_data = context.get('user_data', {})
        return user_data.get('tier', 'free')
    
    tier_limiter = TieredClientRateLimitMiddleware(
        tier_configs={
            'free': {"max_requests": 2, "window_seconds": 60},
            'premium': {"max_requests": 5, "window_seconds": 60}
        },
        tier_resolver=tier_resolver
    )
    
    # Free user context
    free_context = {
        'user_id': 'free_user',
        'user_data': {'tier': 'free'}
    }
    
    # Premium user context
    premium_context = {
        'user_id': 'premium_user', 
        'user_data': {'tier': 'premium'}
    }
    
    handler = Mock(return_value="success")
    
    # Free user: only 2 requests allowed
    for i in range(2):
        result = await tier_limiter.handle(free_context.copy(), handler)
        assert result == "success"
    
    # Free user: 3rd request blocked
    result = await tier_limiter.handle(free_context.copy(), handler)
    assert result['error'] == 'rate_limit_exceeded'
    
    # Premium user: 5 requests allowed
    for i in range(5):
        result = await tier_limiter.handle(premium_context.copy(), handler)
        assert result == "success"
```

### Load Testing

```python
import asyncio
import random

async def test_client_distribution():
    """Test rate limiting with multiple clients"""
    
    client_limiter = ClientRateLimitMiddleware(
        max_requests=10,
        window_seconds=60
    )
    
    # Simulate 100 clients making requests
    clients = [f"user_{i}" for i in range(100)]
    
    async def make_request(client_id):
        context = {'user_id': client_id, 'topic': 'test'}
        handler = Mock(return_value="success")
        return await client_limiter.handle(context, handler)
    
    # Each client makes 5 requests (within limit)
    tasks = []
    for client_id in clients:
        for _ in range(5):
            tasks.append(make_request(client_id))
    
    # Execute all requests
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # All should succeed (5 < 10 limit per client)
    success_count = sum(1 for r in results if r == "success")
    
    print(f"Successful requests: {success_count}/{len(tasks)}")
    assert success_count == len(tasks)
```

## Performance Considerations

### Key Space Management

Client-based rate limiting can create many unique keys. Monitor and manage key proliferation:

```python
class MonitoredClientRateLimitMiddleware(ClientRateLimitMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.key_stats = {
            'unique_clients': set(),
            'total_requests': 0
        }
    
    async def handle(self, context, next_handler):
        # Track unique clients
        client_id = self._client_key_generator(context)
        self.key_stats['unique_clients'].add(client_id)
        self.key_stats['total_requests'] += 1
        
        # Log stats periodically
        if self.key_stats['total_requests'] % 1000 == 0:
            self.logger.info(f"Rate limiting stats: {len(self.key_stats['unique_clients'])} unique clients, "
                           f"{self.key_stats['total_requests']} total requests")
        
        return await super().handle(context, next_handler)
```

### Memory Usage Optimization

```python
# Clean up expired client keys periodically
class OptimizedClientRateLimitMiddleware(ClientRateLimitMiddleware):
    def __init__(self, *args, cleanup_interval: int = 3600, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup_interval = cleanup_interval
        self.last_cleanup = time.time()
    
    async def handle(self, context, next_handler):
        # Periodic cleanup
        if time.time() - self.last_cleanup > self.cleanup_interval:
            await self._cleanup_expired_keys()
            self.last_cleanup = time.time()
        
        return await super().handle(context, next_handler)
    
    async def _cleanup_expired_keys(self):
        """Clean up expired rate limit keys"""
        try:
            if redis_manager.is_enabled():
                # Find and remove expired keys
                pattern = f"{self.redis_key_prefix}:*"
                keys = await redis_manager.keys(pattern)
                
                # Check TTL for each key and remove expired ones
                expired_keys = []
                for key in keys:
                    ttl = await redis_manager.ttl(key)
                    if ttl == -1:  # No expiration set
                        await redis_manager.expire(key, self.window_seconds)
                    elif ttl == -2:  # Key doesn't exist or expired
                        expired_keys.append(key)
                
                if expired_keys:
                    await redis_manager.delete(*expired_keys)
                    self.logger.info(f"Cleaned up {len(expired_keys)} expired rate limit keys")
        
        except Exception as e:
            self.logger.error(f"Rate limit key cleanup failed: {e}")
```

## Next Steps

- [Advanced Features](advanced-features.md) - Whitelisting, custom messages, and fallbacks
- [Basic Rate Limiting](basic-rate-limiting.md) - Review the fundamentals
- [Rate Limiting Strategies](strategies.md) - Choose the right algorithm
- [Topic-Specific Limits](topic-specific.md) - Combine with topic-based limiting
