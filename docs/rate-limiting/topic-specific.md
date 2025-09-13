# Topic-Specific Rate Limits

Configure different rate limits for different topic patterns to provide fine-grained control over message processing rates.

## Overview

Topic-specific rate limiting allows you to set different limits based on MQTT topic patterns, enabling you to:

- Apply stricter limits to sensitive endpoints
- Allow higher throughput for bulk data endpoints
- Customize limits based on topic hierarchy
- Implement tiered rate limiting strategies

## Basic Topic-Specific Configuration

### Using Custom Key Generators

```python
from app.middleware.rate_limit import RateLimitMiddleware

def topic_based_key_generator(context):
    """Generate rate limit keys based on topic patterns"""
    topic = context.get('topic', 'unknown')
    
    # Different limits for different topic patterns
    if topic.startswith('api/admin/'):
        return f"admin_api:{topic}"
    elif topic.startswith('api/user/'):
        return f"user_api:{topic}"
    elif topic.startswith('devices/'):
        return f"device:{topic}"
    else:
        return f"general:{topic}"

# Create rate limiter with custom key generator
topic_rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    key_generator=topic_based_key_generator
)
```

### Topic Pattern Middleware

Create a specialized middleware for topic-specific limits:

```python
from typing import Dict, Any
from app.middleware.rate_limit import RateLimitMiddleware

class TopicRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiting middleware with topic-specific configurations"""
    
    def __init__(self, topic_limits: Dict[str, Dict[str, Any]], 
                 default_limit: Dict[str, Any] = None):
        """
        Initialize topic-specific rate limiting.
        
        Args:
            topic_limits: Dictionary mapping topic patterns to rate limit configs
            default_limit: Default rate limit configuration
        """
        # Use default configuration for initialization
        default_config = default_limit or {"max_requests": 50, "window_seconds": 60}
        super().__init__(**default_config)
        
        self.topic_limits = topic_limits
        self.default_limit = default_config
    
    def _get_topic_config(self, topic: str) -> Dict[str, Any]:
        """Get rate limit configuration for a specific topic"""
        
        # Check for exact matches first
        if topic in self.topic_limits:
            return self.topic_limits[topic]
        
        # Check for pattern matches
        for pattern, config in self.topic_limits.items():
            if self._matches_pattern(topic, pattern):
                return config
        
        # Return default configuration
        return self.default_limit
    
    def _matches_pattern(self, topic: str, pattern: str) -> bool:
        """Check if topic matches a pattern"""
        
        # Convert MQTT wildcards to regex-like matching
        if '*' in pattern:
            # Single level wildcard
            pattern_parts = pattern.split('/')
            topic_parts = topic.split('/')
            
            if len(pattern_parts) != len(topic_parts):
                return False
            
            for pattern_part, topic_part in zip(pattern_parts, topic_parts):
                if pattern_part != '*' and pattern_part != topic_part:
                    return False
            
            return True
        
        elif '#' in pattern:
            # Multi-level wildcard (matches everything after)
            if pattern.endswith('#'):
                prefix = pattern[:-1]  # Remove '#'
                return topic.startswith(prefix)
        
        # Exact match
        return topic == pattern
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Handle rate limiting with topic-specific configuration"""
        
        topic = context.get('topic', 'unknown')
        config = self._get_topic_config(topic)
        
        # Temporarily override configuration
        original_max_requests = self.max_requests
        original_window_seconds = self.window_seconds
        original_strategy = self.strategy
        
        self.max_requests = config.get('max_requests', self.max_requests)
        self.window_seconds = config.get('window_seconds', self.window_seconds)
        self.strategy = config.get('strategy', self.strategy)
        
        try:
            return await super().handle(context, next_handler)
        finally:
            # Restore original configuration
            self.max_requests = original_max_requests
            self.window_seconds = original_window_seconds
            self.strategy = original_strategy

# Usage example
topic_rate_limiter = TopicRateLimitMiddleware(
    topic_limits={
        # Admin endpoints - very restrictive
        "api/admin/*": {
            "max_requests": 10,
            "window_seconds": 60,
            "strategy": "sliding_window"
        },
        
        # User API endpoints - moderate limits
        "api/user/*": {
            "max_requests": 100,
            "window_seconds": 60,
            "strategy": "token_bucket",
            "burst_allowance": 20
        },
        
        # Bulk data endpoints - higher limits
        "data/bulk/*": {
            "max_requests": 1000,
            "window_seconds": 60,
            "strategy": "fixed_window"
        },
        
        # Device telemetry - per-device limits
        "devices/*/telemetry": {
            "max_requests": 100,
            "window_seconds": 60,
            "strategy": "token_bucket",
            "burst_allowance": 50
        },
        
        # Critical system endpoints - very strict
        "system/critical/*": {
            "max_requests": 5,
            "window_seconds": 60,
            "strategy": "sliding_window"
        }
    },
    default_limit={
        "max_requests": 50,
        "window_seconds": 60,
        "strategy": "sliding_window"
    }
)

# Apply to router
router.on("{topic:.*}", 
          DynamicController.handle,
          middleware=[topic_rate_limiter])
```

## Advanced Topic Patterns

### Hierarchical Rate Limiting

```python
class HierarchicalRateLimitMiddleware(TopicRateLimitMiddleware):
    """Rate limiting that considers topic hierarchy"""
    
    def __init__(self, hierarchical_limits: Dict[str, Dict], *args, **kwargs):
        super().__init__({}, *args, **kwargs)
        self.hierarchical_limits = hierarchical_limits
    
    def _get_topic_config(self, topic: str) -> Dict[str, Any]:
        """Get configuration considering topic hierarchy"""
        
        topic_parts = topic.split('/')
        
        # Check from most specific to least specific
        for i in range(len(topic_parts), 0, -1):
            partial_topic = '/'.join(topic_parts[:i])
            
            # Check exact match
            if partial_topic in self.hierarchical_limits:
                return self.hierarchical_limits[partial_topic]
            
            # Check with wildcard
            if i < len(topic_parts):
                wildcard_topic = partial_topic + '/*'
                if wildcard_topic in self.hierarchical_limits:
                    return self.hierarchical_limits[wildcard_topic]
        
        return self.default_limit

# Hierarchical configuration
hierarchical_limiter = HierarchicalRateLimitMiddleware(
    hierarchical_limits={
        # Top level - most restrictive
        "api": {"max_requests": 1000, "window_seconds": 3600},
        
        # Second level - more specific
        "api/admin": {"max_requests": 50, "window_seconds": 3600},
        "api/user": {"max_requests": 500, "window_seconds": 3600},
        "api/public": {"max_requests": 100, "window_seconds": 3600},
        
        # Third level - very specific
        "api/admin/users": {"max_requests": 20, "window_seconds": 3600},
        "api/admin/system": {"max_requests": 10, "window_seconds": 3600},
        
        # Device hierarchy
        "devices": {"max_requests": 10000, "window_seconds": 3600},
        "devices/sensors": {"max_requests": 5000, "window_seconds": 3600},
        "devices/actuators": {"max_requests": 1000, "window_seconds": 3600},
    },
    default_limit={"max_requests": 100, "window_seconds": 3600}
)
```

### Dynamic Topic Configuration

```python
class DynamicTopicRateLimitMiddleware(TopicRateLimitMiddleware):
    """Rate limiting with dynamic topic configuration loading"""
    
    def __init__(self, config_loader: callable, refresh_interval: int = 300, *args, **kwargs):
        super().__init__({}, *args, **kwargs)
        self.config_loader = config_loader
        self.refresh_interval = refresh_interval
        self.last_refresh = 0
        self.cached_config = {}
    
    async def _refresh_config(self):
        """Refresh topic configuration from external source"""
        current_time = time.time()
        
        if current_time - self.last_refresh > self.refresh_interval:
            try:
                new_config = await self.config_loader()
                self.topic_limits = new_config
                self.last_refresh = current_time
                self.logger.info("Topic rate limit configuration refreshed")
            except Exception as e:
                self.logger.error(f"Failed to refresh topic configuration: {e}")
    
    async def handle(self, context, next_handler):
        """Handle with dynamic configuration refresh"""
        await self._refresh_config()
        return await super().handle(context, next_handler)

# Configuration loader function
async def load_topic_config_from_database():
    """Load topic rate limit configuration from database"""
    # This would typically load from your configuration database
    from core.model import Model
    
    try:
        # Example: load from a configuration table
        configs = await Model.all(TopicRateLimitConfig)
        
        topic_limits = {}
        for config in configs:
            topic_limits[config.topic_pattern] = {
                "max_requests": config.max_requests,
                "window_seconds": config.window_seconds,
                "strategy": config.strategy
            }
        
        return topic_limits
    except Exception as e:
        # Return default configuration on error
        return {
            "api/*": {"max_requests": 100, "window_seconds": 60}
        }

# Usage with dynamic loading
dynamic_limiter = DynamicTopicRateLimitMiddleware(
    config_loader=load_topic_config_from_database,
    refresh_interval=300  # Refresh every 5 minutes
)
```

## Topic-Specific Use Cases

### IoT Device Management

```python
# Different limits for different device operations
iot_topic_limiter = TopicRateLimitMiddleware(
    topic_limits={
        # Device registration - strict limits
        "devices/register": {
            "max_requests": 10,
            "window_seconds": 3600,  # 10 registrations per hour
            "strategy": "sliding_window"
        },
        
        # Device heartbeat - moderate limits
        "devices/*/heartbeat": {
            "max_requests": 60,
            "window_seconds": 3600,  # Once per minute
            "strategy": "fixed_window"
        },
        
        # Sensor data - high throughput
        "devices/*/sensors/*": {
            "max_requests": 1000,
            "window_seconds": 3600,  # High frequency data
            "strategy": "token_bucket",
            "burst_allowance": 200
        },
        
        # Device commands - controlled access
        "devices/*/commands": {
            "max_requests": 100,
            "window_seconds": 3600,
            "strategy": "sliding_window"
        },
        
        # Firmware updates - very restricted
        "devices/*/firmware": {
            "max_requests": 1,
            "window_seconds": 86400,  # Once per day
            "strategy": "sliding_window"
        }
    },
    default_limit={"max_requests": 50, "window_seconds": 3600}
)
```

### API Versioning

```python
# Different limits for different API versions
api_version_limiter = TopicRateLimitMiddleware(
    topic_limits={
        # Legacy API v1 - restrictive to encourage migration
        "api/v1/*": {
            "max_requests": 100,
            "window_seconds": 3600,
            "strategy": "fixed_window"
        },
        
        # Current API v2 - standard limits
        "api/v2/*": {
            "max_requests": 1000,
            "window_seconds": 3600,
            "strategy": "sliding_window"
        },
        
        # Beta API v3 - controlled access
        "api/v3/*": {
            "max_requests": 500,
            "window_seconds": 3600,
            "strategy": "token_bucket",
            "burst_allowance": 100
        },
        
        # Admin API - very restricted
        "api/*/admin/*": {
            "max_requests": 50,
            "window_seconds": 3600,
            "strategy": "sliding_window"
        }
    }
)
```

### Multi-Tenant Applications

```python
# Per-tenant rate limiting
def create_tenant_rate_limiter():
    """Create rate limiter with tenant-specific limits"""
    
    # Load tenant configurations (example)
    tenant_configs = {
        "tenant/premium/*": {
            "max_requests": 10000,
            "window_seconds": 3600,
            "strategy": "token_bucket",
            "burst_allowance": 2000
        },
        "tenant/standard/*": {
            "max_requests": 1000,
            "window_seconds": 3600,
            "strategy": "sliding_window"
        },
        "tenant/basic/*": {
            "max_requests": 100,
            "window_seconds": 3600,
            "strategy": "fixed_window"
        }
    }
    
    return TopicRateLimitMiddleware(
        topic_limits=tenant_configs,
        default_limit={"max_requests": 50, "window_seconds": 3600}
    )

tenant_limiter = create_tenant_rate_limiter()
```

## Configuration Management

### Database-Driven Configuration

```python
# Database model for topic rate limit configuration
class TopicRateLimitConfig(Base):
    __tablename__ = "topic_rate_limits"
    
    id = Column(Integer, primary_key=True)
    topic_pattern = Column(String(255), unique=True, nullable=False)
    max_requests = Column(Integer, nullable=False)
    window_seconds = Column(Integer, nullable=False)
    strategy = Column(String(50), default="sliding_window")
    burst_allowance = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Configuration loader
class DatabaseTopicConfigLoader:
    @staticmethod
    async def load_config():
        """Load topic rate limit configuration from database"""
        try:
            configs = await Model.all(TopicRateLimitConfig)
            
            topic_limits = {}
            for config in configs:
                if config.enabled:
                    topic_limits[config.topic_pattern] = {
                        "max_requests": config.max_requests,
                        "window_seconds": config.window_seconds,
                        "strategy": config.strategy,
                        "burst_allowance": config.burst_allowance
                    }
            
            return topic_limits
        except Exception as e:
            logging.error(f"Failed to load topic config from database: {e}")
            return {}

# Usage
async def create_database_driven_limiter():
    config = await DatabaseTopicConfigLoader.load_config()
    return TopicRateLimitMiddleware(
        topic_limits=config,
        default_limit={"max_requests": 100, "window_seconds": 60}
    )
```

### Configuration File Management

```python
import yaml
from pathlib import Path

class FileTopicConfigLoader:
    def __init__(self, config_file: str):
        self.config_file = Path(config_file)
        self.last_modified = 0
    
    async def load_config(self):
        """Load configuration from YAML file"""
        try:
            # Check if file was modified
            current_modified = self.config_file.stat().st_mtime
            if current_modified <= self.last_modified:
                return self.cached_config
            
            # Load configuration
            with open(self.config_file, 'r') as f:
                config_data = yaml.safe_load(f)
            
            self.cached_config = config_data.get('topic_limits', {})
            self.last_modified = current_modified
            
            return self.cached_config
        except Exception as e:
            logging.error(f"Failed to load config file {self.config_file}: {e}")
            return {}

# Example configuration file: topic_limits.yaml
"""
topic_limits:
  "api/admin/*":
    max_requests: 50
    window_seconds: 3600
    strategy: "sliding_window"
  
  "api/user/*":
    max_requests: 1000
    window_seconds: 3600
    strategy: "token_bucket"
    burst_allowance: 200
  
  "devices/*/telemetry":
    max_requests: 500
    window_seconds: 60
    strategy: "fixed_window"

default_limit:
  max_requests: 100
  window_seconds: 60
  strategy: "sliding_window"
"""

# Usage
config_loader = FileTopicConfigLoader("config/topic_limits.yaml")
file_driven_limiter = DynamicTopicRateLimitMiddleware(
    config_loader=config_loader.load_config,
    refresh_interval=60  # Check file every minute
)
```

## Testing Topic-Specific Limits

### Unit Testing

```python
import pytest
from app.middleware.rate_limit import TopicRateLimitMiddleware

@pytest.mark.asyncio
async def test_topic_specific_limits():
    """Test different limits for different topics"""
    
    topic_limiter = TopicRateLimitMiddleware(
        topic_limits={
            "api/admin/*": {"max_requests": 2, "window_seconds": 60},
            "api/user/*": {"max_requests": 5, "window_seconds": 60},
        },
        default_limit={"max_requests": 3, "window_seconds": 60}
    )
    
    # Test admin endpoint (limit: 2)
    admin_context = {'topic': 'api/admin/users'}
    handler = AsyncMock(return_value="success")
    
    # First 2 requests should pass
    for i in range(2):
        result = await topic_limiter.handle(admin_context.copy(), handler)
        assert result == "success"
    
    # 3rd request should be blocked
    result = await topic_limiter.handle(admin_context.copy(), handler)
    assert result['error'] == 'rate_limit_exceeded'
    
    # Test user endpoint (limit: 5) - should still work
    user_context = {'topic': 'api/user/profile'}
    result = await topic_limiter.handle(user_context.copy(), handler)
    assert result == "success"

@pytest.mark.asyncio
async def test_topic_pattern_matching():
    """Test topic pattern matching functionality"""
    
    topic_limiter = TopicRateLimitMiddleware(
        topic_limits={
            "devices/*/sensors": {"max_requests": 10, "window_seconds": 60},
            "api/v1/*": {"max_requests": 5, "window_seconds": 60},
        }
    )
    
    # Test wildcard matching
    test_cases = [
        ("devices/device123/sensors", "devices/*/sensors"),
        ("devices/device456/sensors", "devices/*/sensors"),
        ("api/v1/users", "api/v1/*"),
        ("api/v1/orders", "api/v1/*"),
    ]
    
    for topic, expected_pattern in test_cases:
        config = topic_limiter._get_topic_config(topic)
        # Verify correct configuration is returned
        assert config['max_requests'] in [10, 5]  # From our test patterns
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_topic_limits_with_router():
    """Test topic-specific rate limiting with router"""
    
    from core.router import Router
    
    # Create topic-specific rate limiter
    topic_limiter = TopicRateLimitMiddleware(
        topic_limits={
            "api/*": {"max_requests": 3, "window_seconds": 60},
            "data/*": {"max_requests": 5, "window_seconds": 60},
        }
    )
    
    router = Router()
    router.on("{topic:.*}", 
              lambda ctx: {"topic": ctx['topic'], "status": "success"},
              middleware=[topic_limiter])
    
    # Test API endpoints
    for i in range(3):
        result = await router.dispatch("api/test", {}, None)
        assert result['status'] == 'success'
    
    # 4th API request should be blocked
    result = await router.dispatch("api/test", {}, None)
    assert result['error'] == 'rate_limit_exceeded'
    
    # Data endpoints should still work (different limit)
    result = await router.dispatch("data/test", {}, None)
    assert result['status'] == 'success'
```

## Performance Considerations

### Key Generation Efficiency

Topic-specific rate limiting can generate many different keys. Consider:

```python
# Efficient key generation
def efficient_topic_key_generator(context):
    """Generate efficient rate limit keys"""
    topic = context.get('topic', 'unknown')
    
    # Normalize topic to reduce key proliferation
    topic_parts = topic.split('/')
    
    # Limit depth to prevent too many unique keys
    if len(topic_parts) > 3:
        normalized_topic = '/'.join(topic_parts[:3]) + '/*'
    else:
        normalized_topic = topic
    
    return f"topic:{normalized_topic}"
```

### Memory Management

```python
# Monitor key proliferation
class MonitoredTopicRateLimitMiddleware(TopicRateLimitMiddleware):
    def __init__(self, *args, max_keys: int = 10000, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_keys = max_keys
        self.key_count_check_interval = 300  # 5 minutes
        self.last_key_count_check = 0
    
    async def handle(self, context, next_handler):
        # Periodically check key count
        current_time = time.time()
        if current_time - self.last_key_count_check > self.key_count_check_interval:
            await self._check_key_count()
            self.last_key_count_check = current_time
        
        return await super().handle(context, next_handler)
    
    async def _check_key_count(self):
        """Check and log rate limit key count"""
        try:
            if redis_manager.is_enabled():
                keys = await redis_manager.keys(f"{self.redis_key_prefix}:*")
                key_count = len(keys)
                
                if key_count > self.max_keys:
                    self.logger.warning(f"High rate limit key count: {key_count}")
                
                self.logger.info(f"Rate limit key count: {key_count}")
        except Exception as e:
            self.logger.error(f"Failed to check key count: {e}")
```

## Next Steps

- [Client-Based Limiting](client-based.md) - Rate limit by client instead of topic
- [Advanced Features](advanced-features.md) - Whitelisting, custom messages, and more
- [Basic Rate Limiting](basic-rate-limiting.md) - Review the fundamentals
- [Rate Limiting Strategies](strategies.md) - Choose the right algorithm for each topic
