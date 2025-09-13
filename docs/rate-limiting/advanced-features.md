# Advanced Rate Limiting Features

Explore advanced rate limiting capabilities including whitelisting, custom error messages, fallback mechanisms, and sophisticated rate limiting patterns.

## Whitelisting and Exemptions

### Basic Whitelisting

```python
from app.middleware.rate_limit import RateLimitMiddleware

# Rate limiter with whitelisting
advanced_rate_limiter = RateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    whitelist=[
        "admin/*",              # All admin topics
        "emergency/*",          # Emergency endpoints
        "system/health",        # Health check endpoint
        "monitoring/*"          # Monitoring endpoints
    ],
    custom_error_message="Rate limit exceeded. Please try again later."
)

# Apply to routes
router.on("{topic:.*}", 
          DynamicController.handle,
          middleware=[advanced_rate_limiter])
```

### Advanced Whitelisting Patterns

```python
class AdvancedWhitelistMiddleware(RateLimitMiddleware):
    """Rate limiting with advanced whitelisting capabilities"""
    
    def __init__(self, whitelist_config: Dict[str, Any] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.whitelist_config = whitelist_config or {}
        
        # Different types of whitelists
        self.topic_whitelist = set(self.whitelist_config.get('topics', []))
        self.client_whitelist = set(self.whitelist_config.get('clients', []))
        self.ip_whitelist = set(self.whitelist_config.get('ip_addresses', []))
        self.user_whitelist = set(self.whitelist_config.get('users', []))
        self.role_whitelist = set(self.whitelist_config.get('roles', []))
        
        # Conditional whitelisting
        self.conditional_whitelist = self.whitelist_config.get('conditional', [])
    
    def _is_whitelisted(self, key: str, context: Dict[str, Any] = None) -> bool:
        """Advanced whitelist checking"""
        
        # Topic-based whitelisting
        topic = context.get('topic', '') if context else ''
        if self._matches_topic_whitelist(topic):
            return True
        
        # Client-based whitelisting
        if self._matches_client_whitelist(context):
            return True
        
        # IP-based whitelisting
        if self._matches_ip_whitelist(context):
            return True
        
        # User-based whitelisting
        if self._matches_user_whitelist(context):
            return True
        
        # Role-based whitelisting
        if self._matches_role_whitelist(context):
            return True
        
        # Conditional whitelisting
        if self._matches_conditional_whitelist(context):
            return True
        
        return False
    
    def _matches_topic_whitelist(self, topic: str) -> bool:
        """Check topic against whitelist patterns"""
        for pattern in self.topic_whitelist:
            if self._topic_matches_pattern(topic, pattern):
                return True
        return False
    
    def _matches_client_whitelist(self, context: Dict[str, Any]) -> bool:
        """Check client ID against whitelist"""
        if not context:
            return False
        
        # Check various client identifiers
        identifiers = [
            context.get('user_id'),
            context.get('device_id'),
            context.get('client_id'),
            context.get('auth_data', {}).get('key_id')
        ]
        
        for identifier in identifiers:
            if identifier and identifier in self.client_whitelist:
                return True
        
        return False
    
    def _matches_ip_whitelist(self, context: Dict[str, Any]) -> bool:
        """Check IP address against whitelist"""
        if not context:
            return False
        
        client_ip = context.get('client_ip')
        return client_ip in self.ip_whitelist if client_ip else False
    
    def _matches_user_whitelist(self, context: Dict[str, Any]) -> bool:
        """Check user against whitelist"""
        if not context:
            return False
        
        user_id = context.get('user_id')
        return user_id in self.user_whitelist if user_id else False
    
    def _matches_role_whitelist(self, context: Dict[str, Any]) -> bool:
        """Check user roles against whitelist"""
        if not context:
            return False
        
        user_roles = context.get('roles', [])
        return any(role in self.role_whitelist for role in user_roles)
    
    def _matches_conditional_whitelist(self, context: Dict[str, Any]) -> bool:
        """Check conditional whitelist rules"""
        if not context:
            return False
        
        for condition in self.conditional_whitelist:
            if self._evaluate_condition(condition, context):
                return True
        
        return False
    
    def _evaluate_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate a conditional whitelist rule"""
        
        condition_type = condition.get('type')
        
        if condition_type == 'time_range':
            return self._check_time_range(condition, context)
        elif condition_type == 'payload_field':
            return self._check_payload_field(condition, context)
        elif condition_type == 'request_size':
            return self._check_request_size(condition, context)
        elif condition_type == 'custom_header':
            return self._check_custom_header(condition, context)
        
        return False
    
    def _check_time_range(self, condition: Dict, context: Dict) -> bool:
        """Check if current time is within specified range"""
        import datetime
        
        now = datetime.datetime.now()
        start_hour = condition.get('start_hour', 0)
        end_hour = condition.get('end_hour', 23)
        
        return start_hour <= now.hour <= end_hour
    
    def _check_payload_field(self, condition: Dict, context: Dict) -> bool:
        """Check payload field value"""
        payload = context.get('payload', {})
        field = condition.get('field')
        expected_value = condition.get('value')
        
        return payload.get(field) == expected_value
    
    def _check_request_size(self, condition: Dict, context: Dict) -> bool:
        """Check request size"""
        payload = context.get('payload', {})
        max_size = condition.get('max_size', 1024)
        
        payload_size = len(str(payload))
        return payload_size <= max_size
    
    def _check_custom_header(self, condition: Dict, context: Dict) -> bool:
        """Check custom header value"""
        headers = context.get('headers', {})
        header_name = condition.get('header')
        expected_value = condition.get('value')
        
        return headers.get(header_name) == expected_value

# Advanced whitelist configuration
whitelist_config = {
    'topics': [
        'admin/*',
        'emergency/*',
        'system/health'
    ],
    'clients': [
        'user:admin_user',
        'device:critical_device_001',
        'api_key:admin_key_123'
    ],
    'ip_addresses': [
        '192.168.1.100',  # Admin workstation
        '10.0.0.50'       # Monitoring server
    ],
    'users': [
        'admin_user',
        'system_user'
    ],
    'roles': [
        'admin',
        'system_operator'
    ],
    'conditional': [
        {
            'type': 'time_range',
            'start_hour': 9,
            'end_hour': 17,
            'description': 'Business hours exemption'
        },
        {
            'type': 'payload_field',
            'field': 'priority',
            'value': 'emergency',
            'description': 'Emergency priority messages'
        },
        {
            'type': 'custom_header',
            'header': 'X-Bypass-Rate-Limit',
            'value': 'true',
            'description': 'Explicit bypass header'
        }
    ]
}

advanced_whitelist_limiter = AdvancedWhitelistMiddleware(
    max_requests=100,
    window_seconds=60,
    whitelist_config=whitelist_config
)
```

## Custom Error Messages and Responses

### Dynamic Error Messages

```python
class CustomErrorMessageMiddleware(RateLimitMiddleware):
    """Rate limiter with customizable error messages"""
    
    def __init__(self, error_message_generator: Callable = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_message_generator = error_message_generator or self._default_error_message
    
    def _default_error_message(self, context: Dict[str, Any], rate_limit_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate default error message"""
        
        client_type = self._identify_client_type(context)
        remaining_time = rate_limit_info.get('reset_time', self.window_seconds)
        
        messages = {
            'user': f"You've exceeded your rate limit of {self.max_requests} requests per {self.window_seconds} seconds. Please try again in {remaining_time} seconds.",
            'device': f"Device rate limit exceeded. Your device can send {self.max_requests} messages per {self.window_seconds} seconds. Next allowed message in {remaining_time} seconds.",
            'api': f"API rate limit exceeded. Limit: {self.max_requests} requests per {self.window_seconds} seconds. Reset in {remaining_time} seconds.",
            'anonymous': f"Rate limit exceeded for anonymous requests. Please authenticate for higher limits or try again in {remaining_time} seconds."
        }
        
        return {
            "error": "rate_limit_exceeded",
            "message": messages.get(client_type, messages['anonymous']),
            "rate_limit": {
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "remaining": rate_limit_info.get('remaining', 0),
                "reset_time": remaining_time,
                "client_type": client_type
            },
            "suggestions": self._get_suggestions(client_type, context)
        }
    
    def _identify_client_type(self, context: Dict[str, Any]) -> str:
        """Identify the type of client making the request"""
        
        if context.get('user_id'):
            return 'user'
        elif context.get('device_id'):
            return 'device'
        elif context.get('auth_data', {}).get('key_id'):
            return 'api'
        else:
            return 'anonymous'
    
    def _get_suggestions(self, client_type: str, context: Dict[str, Any]) -> List[str]:
        """Get suggestions for the client"""
        
        suggestions = {
            'user': [
                "Consider upgrading to a premium account for higher rate limits",
                "Batch your requests to be more efficient",
                "Implement exponential backoff in your client"
            ],
            'device': [
                "Implement local data buffering to reduce message frequency",
                "Send only critical data during high-traffic periods",
                "Contact support to increase device limits"
            ],
            'api': [
                "Implement caching to reduce API calls",
                "Use bulk operations where available",
                "Consider upgrading your API plan"
            ],
            'anonymous': [
                "Register for an account to get higher rate limits",
                "Authenticate your requests using API keys",
                "Implement request retry with exponential backoff"
            ]
        }
        
        return suggestions.get(client_type, [])
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Handle with custom error messages"""
        
        # Generate rate limit key
        rate_limit_key = self.key_generator(context)
        
        # Check whitelist
        if self._is_whitelisted(rate_limit_key, context):
            return await next_handler(context)
        
        # Apply rate limiting
        allowed, remaining, reset_time = await self._check_rate_limit(rate_limit_key)
        
        if not allowed:
            rate_limit_info = {
                'remaining': remaining,
                'reset_time': reset_time
            }
            
            # Generate custom error response
            error_response = self.error_message_generator(context, rate_limit_info)
            
            # Log with context
            self.logger.warning(f"Rate limit exceeded", extra={
                'rate_limit_key': rate_limit_key,
                'client_type': self._identify_client_type(context),
                'topic': context.get('topic'),
                'remaining': remaining,
                'reset_time': reset_time
            })
            
            return error_response
        
        # Add rate limit info to context
        context['rate_limit'] = {
            'exceeded': False,
            'key': rate_limit_key,
            'remaining': remaining,
            'reset_time': reset_time
        }
        
        return await next_handler(context)

# Usage with custom error messages
def custom_error_generator(context, rate_limit_info):
    """Custom error message generator"""
    
    topic = context.get('topic', 'unknown')
    user_id = context.get('user_id', 'anonymous')
    
    return {
        "error": "rate_limit_exceeded",
        "message": f"Hello {user_id}, you've exceeded the rate limit for {topic}. Please slow down!",
        "rate_limit": rate_limit_info,
        "retry_after": rate_limit_info.get('reset_time', 60),
        "contact_support": "support@example.com"
    }

custom_error_limiter = CustomErrorMessageMiddleware(
    max_requests=100,
    window_seconds=60,
    error_message_generator=custom_error_generator
)
```

## Fallback Mechanisms

### Multi-Backend Fallback

```python
class FallbackRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiter with multiple fallback mechanisms"""
    
    def __init__(self, fallback_strategy: str = "memory", 
                 degraded_limits: Dict[str, Any] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallback_strategy = fallback_strategy
        self.degraded_limits = degraded_limits or {}
        self.redis_healthy = True
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
    
    async def _check_rate_limit(self, key: str) -> tuple[bool, int, int]:
        """Check rate limit with fallback mechanisms"""
        
        # Check Redis health periodically
        current_time = time.time()
        if current_time - self.last_health_check > self.health_check_interval:
            await self._check_redis_health()
            self.last_health_check = current_time
        
        # Try Redis first if healthy
        if self.redis_healthy and redis_manager.is_enabled():
            try:
                return await self._check_rate_limit_redis(f"{self.redis_key_prefix}:{key}")
            except Exception as e:
                self.logger.error(f"Redis rate limit check failed: {e}")
                self.redis_healthy = False
                return await self._handle_redis_failure(key)
        
        # Fallback to alternative strategies
        return await self._fallback_rate_limit_check(key)
    
    async def _check_redis_health(self):
        """Check Redis health status"""
        try:
            if redis_manager.is_enabled():
                await redis_manager.ping()
                if not self.redis_healthy:
                    self.logger.info("Redis connection restored")
                self.redis_healthy = True
        except Exception:
            if self.redis_healthy:
                self.logger.warning("Redis connection lost, switching to fallback")
            self.redis_healthy = False
    
    async def _handle_redis_failure(self, key: str) -> tuple[bool, int, int]:
        """Handle Redis failure based on strategy"""
        
        if self.fallback_strategy == "allow_all":
            # Allow all requests when Redis is down
            self.logger.warning("Rate limiting disabled due to Redis failure")
            return True, self.max_requests - 1, 0
        
        elif self.fallback_strategy == "deny_all":
            # Deny all requests when Redis is down
            self.logger.warning("All requests denied due to Redis failure")
            return False, 0, self.window_seconds
        
        elif self.fallback_strategy == "degraded":
            # Use degraded limits
            degraded_max = self.degraded_limits.get('max_requests', self.max_requests // 2)
            degraded_window = self.degraded_limits.get('window_seconds', self.window_seconds)
            
            # Temporarily adjust limits
            original_max = self.max_requests
            original_window = self.window_seconds
            
            self.max_requests = degraded_max
            self.window_seconds = degraded_window
            
            try:
                return await self._fallback_rate_limit_check(key)
            finally:
                self.max_requests = original_max
                self.window_seconds = original_window
        
        else:  # fallback_strategy == "memory"
            return await self._fallback_rate_limit_check(key)
    
    async def _fallback_rate_limit_check(self, key: str) -> tuple[bool, int, int]:
        """Fallback rate limit check using in-memory storage"""
        
        if self.fallback_enabled:
            return await self._check_rate_limit_memory(key)
        else:
            # No fallback enabled, allow request
            return True, self.max_requests - 1, 0

# Fallback configurations
fallback_configs = {
    "allow_all": FallbackRateLimitMiddleware(
        max_requests=100,
        window_seconds=60,
        fallback_strategy="allow_all"
    ),
    
    "degraded": FallbackRateLimitMiddleware(
        max_requests=100,
        window_seconds=60,
        fallback_strategy="degraded",
        degraded_limits={
            "max_requests": 50,  # Half the normal limit
            "window_seconds": 60
        }
    ),
    
    "memory_fallback": FallbackRateLimitMiddleware(
        max_requests=100,
        window_seconds=60,
        fallback_strategy="memory",
        fallback_enabled=True
    )
}
```

### Circuit Breaker Pattern

```python
class CircuitBreakerRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiter with circuit breaker pattern"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.circuit_open_time = None
        self.circuit_state = "closed"  # closed, open, half_open
    
    async def _check_rate_limit(self, key: str) -> tuple[bool, int, int]:
        """Check rate limit with circuit breaker pattern"""
        
        # Check circuit state
        if self.circuit_state == "open":
            if time.time() - self.circuit_open_time > self.recovery_timeout:
                self.circuit_state = "half_open"
                self.logger.info("Circuit breaker entering half-open state")
            else:
                # Circuit is open, use fallback
                return await self._circuit_open_fallback(key)
        
        try:
            # Try normal rate limiting
            result = await super()._check_rate_limit(key)
            
            # Success - reset failure count
            if self.circuit_state == "half_open":
                self.circuit_state = "closed"
                self.failure_count = 0
                self.logger.info("Circuit breaker closed - service recovered")
            
            return result
            
        except Exception as e:
            # Failure - increment counter
            self.failure_count += 1
            self.logger.error(f"Rate limit check failed: {e}")
            
            # Check if we should open circuit
            if self.failure_count >= self.failure_threshold:
                self.circuit_state = "open"
                self.circuit_open_time = time.time()
                self.logger.warning("Circuit breaker opened due to repeated failures")
            
            # Return fallback result
            return await self._circuit_open_fallback(key)
    
    async def _circuit_open_fallback(self, key: str) -> tuple[bool, int, int]:
        """Fallback behavior when circuit is open"""
        
        # Use in-memory fallback or allow all requests
        if self.fallback_enabled:
            return await self._check_rate_limit_memory(key)
        else:
            # Allow requests when circuit is open
            return True, self.max_requests - 1, 0

circuit_breaker_limiter = CircuitBreakerRateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    failure_threshold=3,
    recovery_timeout=30
)
```

## Advanced Rate Limiting Patterns

### Adaptive Rate Limiting

```python
class AdaptiveRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiter that adapts based on system load"""
    
    def __init__(self, load_thresholds: Dict[str, Dict] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_thresholds = load_thresholds or {
            "low": {"multiplier": 1.5, "threshold": 0.3},
            "medium": {"multiplier": 1.0, "threshold": 0.7},
            "high": {"multiplier": 0.5, "threshold": 1.0}
        }
        self.current_load = 0.0
        self.last_load_check = 0
        self.load_check_interval = 10  # seconds
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Handle with adaptive rate limiting"""
        
        # Update system load
        await self._update_system_load()
        
        # Adjust limits based on load
        adjusted_limits = self._calculate_adjusted_limits()
        
        # Temporarily override limits
        original_max_requests = self.max_requests
        self.max_requests = adjusted_limits["max_requests"]
        
        try:
            return await super().handle(context, next_handler)
        finally:
            self.max_requests = original_max_requests
    
    async def _update_system_load(self):
        """Update current system load"""
        current_time = time.time()
        
        if current_time - self.last_load_check > self.load_check_interval:
            self.current_load = await self._get_system_load()
            self.last_load_check = current_time
    
    async def _get_system_load(self) -> float:
        """Get current system load (0.0 to 1.0)"""
        try:
            # This could integrate with system monitoring
            # For example: CPU usage, memory usage, active connections
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            # Combined load metric
            load = max(cpu_percent, memory_percent) / 100.0
            return min(1.0, load)
            
        except Exception:
            return 0.5  # Default to medium load
    
    def _calculate_adjusted_limits(self) -> Dict[str, int]:
        """Calculate adjusted limits based on current load"""
        
        # Find appropriate threshold
        multiplier = 1.0
        for level, config in self.load_thresholds.items():
            if self.current_load <= config["threshold"]:
                multiplier = config["multiplier"]
                break
        
        adjusted_max_requests = int(self.max_requests * multiplier)
        
        return {
            "max_requests": max(1, adjusted_max_requests)  # Ensure at least 1
        }

adaptive_limiter = AdaptiveRateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    load_thresholds={
        "low": {"multiplier": 2.0, "threshold": 0.3},     # Double limits when load is low
        "medium": {"multiplier": 1.0, "threshold": 0.7},  # Normal limits
        "high": {"multiplier": 0.3, "threshold": 1.0}     # Reduce to 30% when high load
    }
)
```

### Quota-Based Rate Limiting

```python
class QuotaRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiter with daily/monthly quotas"""
    
    def __init__(self, quotas: Dict[str, Dict] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.quotas = quotas or {}
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Handle with quota checking"""
        
        # Check quotas first
        quota_result = await self._check_quotas(context)
        if not quota_result["allowed"]:
            return {
                "error": "quota_exceeded",
                "message": quota_result["message"],
                "quota_info": quota_result["quota_info"]
            }
        
        # Then check regular rate limits
        return await super().handle(context, next_handler)
    
    async def _check_quotas(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Check various quota limits"""
        
        client_id = self.key_generator(context)
        
        for quota_name, quota_config in self.quotas.items():
            quota_key = f"quota:{quota_name}:{client_id}"
            
            # Check quota
            allowed, remaining, reset_time = await self._check_quota_limit(
                quota_key, 
                quota_config["max_requests"],
                quota_config["window_seconds"]
            )
            
            if not allowed:
                return {
                    "allowed": False,
                    "message": f"{quota_name.title()} quota exceeded. Limit: {quota_config['max_requests']} requests per {quota_config['window_seconds']} seconds.",
                    "quota_info": {
                        "quota_type": quota_name,
                        "max_requests": quota_config["max_requests"],
                        "remaining": remaining,
                        "reset_time": reset_time
                    }
                }
        
        return {"allowed": True}
    
    async def _check_quota_limit(self, quota_key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """Check specific quota limit"""
        
        if redis_manager.is_enabled():
            try:
                current_time = int(time.time())
                window_start = current_time - window_seconds
                
                # Remove old entries
                await redis_manager.zremrangebyscore(quota_key, 0, window_start)
                
                # Count current requests
                current_count = await redis_manager.zcard(quota_key)
                
                if current_count >= max_requests:
                    return False, 0, window_seconds
                
                # Add current request
                await redis_manager.zadd(quota_key, {str(current_time): current_time})
                await redis_manager.expire(quota_key, window_seconds + 1)
                
                remaining = max_requests - current_count - 1
                return True, remaining, window_seconds
                
            except Exception as e:
                self.logger.error(f"Quota check failed: {e}")
                return True, max_requests - 1, 0  # Allow on error
        
        return True, max_requests - 1, 0

# Quota configuration
quota_limiter = QuotaRateLimitMiddleware(
    max_requests=100,      # Regular rate limit: 100/hour
    window_seconds=3600,
    quotas={
        "daily": {
            "max_requests": 10000,    # Daily quota: 10k requests
            "window_seconds": 86400   # 24 hours
        },
        "monthly": {
            "max_requests": 100000,   # Monthly quota: 100k requests
            "window_seconds": 2592000 # 30 days
        }
    }
)
```

## Monitoring and Analytics

### Rate Limiting Analytics

```python
class AnalyticsRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiter with comprehensive analytics"""
    
    def __init__(self, analytics_config: Dict[str, Any] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analytics_config = analytics_config or {}
        self.metrics = {
            "total_requests": 0,
            "blocked_requests": 0,
            "unique_clients": set(),
            "top_blocked_clients": {},
            "hourly_stats": {}
        }
        self.analytics_interval = self.analytics_config.get("interval", 300)  # 5 minutes
        self.last_analytics_export = 0
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Handle with analytics collection"""
        
        client_id = self.key_generator(context)
        current_hour = int(time.time()) // 3600
        
        # Update metrics
        self.metrics["total_requests"] += 1
        self.metrics["unique_clients"].add(client_id)
        
        # Initialize hourly stats
        if current_hour not in self.metrics["hourly_stats"]:
            self.metrics["hourly_stats"][current_hour] = {
                "requests": 0,
                "blocked": 0,
                "unique_clients": set()
            }
        
        self.metrics["hourly_stats"][current_hour]["requests"] += 1
        self.metrics["hourly_stats"][current_hour]["unique_clients"].add(client_id)
        
        # Call parent handler
        result = await super().handle(context, next_handler)
        
        # Check if request was blocked
        if isinstance(result, dict) and result.get("error") == "rate_limit_exceeded":
            self.metrics["blocked_requests"] += 1
            self.metrics["hourly_stats"][current_hour]["blocked"] += 1
            
            # Track top blocked clients
            if client_id not in self.metrics["top_blocked_clients"]:
                self.metrics["top_blocked_clients"][client_id] = 0
            self.metrics["top_blocked_clients"][client_id] += 1
        
        # Export analytics periodically
        await self._maybe_export_analytics()
        
        return result
    
    async def _maybe_export_analytics(self):
        """Export analytics if interval has passed"""
        current_time = time.time()
        
        if current_time - self.last_analytics_export > self.analytics_interval:
            await self._export_analytics()
            self.last_analytics_export = current_time
    
    async def _export_analytics(self):
        """Export analytics data"""
        
        analytics_data = self._prepare_analytics_data()
        
        # Export to Redis
        if redis_manager.is_enabled():
            analytics_key = f"rate_limit_analytics:{int(time.time())}"
            await redis_manager.set_json(analytics_key, analytics_data, ex=86400)  # Keep for 24 hours
        
        # Log analytics
        self.logger.info("Rate limiting analytics", extra=analytics_data)
        
        # Clean up old hourly stats (keep last 24 hours)
        current_hour = int(time.time()) // 3600
        hours_to_keep = list(range(current_hour - 23, current_hour + 1))
        
        self.metrics["hourly_stats"] = {
            hour: stats for hour, stats in self.metrics["hourly_stats"].items()
            if hour in hours_to_keep
        }
    
    def _prepare_analytics_data(self) -> Dict[str, Any]:
        """Prepare analytics data for export"""
        
        # Calculate statistics
        total_requests = self.metrics["total_requests"]
        blocked_requests = self.metrics["blocked_requests"]
        block_rate = (blocked_requests / total_requests * 100) if total_requests > 0 else 0
        
        # Top blocked clients (top 10)
        top_blocked = sorted(
            self.metrics["top_blocked_clients"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Recent hourly stats
        recent_hours = sorted(self.metrics["hourly_stats"].items())[-24:]  # Last 24 hours
        
        hourly_data = []
        for hour, stats in recent_hours:
            hourly_data.append({
                "hour": hour,
                "requests": stats["requests"],
                "blocked": stats["blocked"],
                "unique_clients": len(stats["unique_clients"]),
                "block_rate": (stats["blocked"] / stats["requests"] * 100) if stats["requests"] > 0 else 0
            })
        
        return {
            "timestamp": time.time(),
            "summary": {
                "total_requests": total_requests,
                "blocked_requests": blocked_requests,
                "block_rate_percent": round(block_rate, 2),
                "unique_clients": len(self.metrics["unique_clients"])
            },
            "top_blocked_clients": [{"client": client, "count": count} for client, count in top_blocked],
            "hourly_stats": hourly_data
        }
    
    def get_current_analytics(self) -> Dict[str, Any]:
        """Get current analytics data"""
        return self._prepare_analytics_data()

analytics_limiter = AnalyticsRateLimitMiddleware(
    max_requests=100,
    window_seconds=60,
    analytics_config={
        "interval": 300,  # Export every 5 minutes
        "enable_detailed_logging": True
    }
)
```

## Testing Advanced Features

### Comprehensive Testing

```python
import pytest
from unittest.mock import Mock, patch
import time

@pytest.mark.asyncio
async def test_whitelisting():
    """Test whitelist functionality"""
    
    whitelist_limiter = AdvancedWhitelistMiddleware(
        max_requests=2,
        window_seconds=60,
        whitelist_config={
            'topics': ['admin/*'],
            'users': ['admin_user']
        }
    )
    
    handler = Mock(return_value="success")
    
    # Regular topic should be rate limited
    regular_context = {'topic': 'api/data', 'user_id': 'regular_user'}
    
    # Use up the quota
    for i in range(2):
        result = await whitelist_limiter.handle(regular_context.copy(), handler)
        assert result == "success"
    
    # Next request should be blocked
    result = await whitelist_limiter.handle(regular_context.copy(), handler)
    assert result['error'] == 'rate_limit_exceeded'
    
    # Whitelisted topic should not be rate limited
    admin_topic_context = {'topic': 'admin/users', 'user_id': 'regular_user'}
    result = await whitelist_limiter.handle(admin_topic_context, handler)
    assert result == "success"
    
    # Whitelisted user should not be rate limited
    admin_user_context = {'topic': 'api/data', 'user_id': 'admin_user'}
    result = await whitelist_limiter.handle(admin_user_context, handler)
    assert result == "success"

@pytest.mark.asyncio
async def test_fallback_mechanism():
    """Test fallback when Redis fails"""
    
    fallback_limiter = FallbackRateLimitMiddleware(
        max_requests=2,
        window_seconds=60,
        fallback_strategy="memory",
        fallback_enabled=True
    )
    
    handler = Mock(return_value="success")
    context = {'topic': 'test'}
    
    # Mock Redis failure
    with patch.object(redis_manager, 'is_enabled', return_value=True), \
         patch.object(fallback_limiter, '_check_rate_limit_redis', side_effect=Exception("Redis failed")):
        
        # Should fallback to memory and still work
        result = await fallback_limiter.handle(context.copy(), handler)
        assert result == "success"

@pytest.mark.asyncio
async def test_adaptive_rate_limiting():
    """Test adaptive rate limiting based on system load"""
    
    adaptive_limiter = AdaptiveRateLimitMiddleware(
        max_requests=100,
        window_seconds=60,
        load_thresholds={
            "low": {"multiplier": 2.0, "threshold": 0.3},
            "high": {"multiplier": 0.5, "threshold": 1.0}
        }
    )
    
    handler = Mock(return_value="success")
    context = {'topic': 'test'}
    
    # Mock low system load
    with patch.object(adaptive_limiter, '_get_system_load', return_value=0.2):
        # Should get higher limits (200 requests)
        adaptive_limiter.current_load = 0.2
        adjusted = adaptive_limiter._calculate_adjusted_limits()
        assert adjusted['max_requests'] == 200
    
    # Mock high system load
    with patch.object(adaptive_limiter, '_get_system_load', return_value=0.9):
        # Should get lower limits (50 requests)
        adaptive_limiter.current_load = 0.9
        adjusted = adaptive_limiter._calculate_adjusted_limits()
        assert adjusted['max_requests'] == 50

@pytest.mark.asyncio
async def test_quota_system():
    """Test quota-based rate limiting"""
    
    quota_limiter = QuotaRateLimitMiddleware(
        max_requests=10,  # Regular limit: 10/hour
        window_seconds=3600,
        quotas={
            "daily": {
                "max_requests": 5,  # Very low for testing
                "window_seconds": 86400
            }
        }
    )
    
    handler = Mock(return_value="success")
    context = {'topic': 'test'}
    
    # Should be allowed within daily quota
    for i in range(5):
        result = await quota_limiter.handle(context.copy(), handler)
        assert result == "success"
    
    # 6th request should exceed daily quota
    result = await quota_limiter.handle(context.copy(), handler)
    assert result['error'] == 'quota_exceeded'
    assert 'daily' in result['message'].lower()
```

## Production Deployment

### Performance Optimization

```python
class OptimizedRateLimitMiddleware(RateLimitMiddleware):
    """Production-optimized rate limiting middleware"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Performance optimizations
        self.pipeline_requests = True
        self.batch_size = 10
        self.request_batch = []
        self.last_batch_flush = time.time()
        self.batch_timeout = 0.1  # 100ms
    
    async def handle(self, context: Dict[str, Any], next_handler):
        """Optimized handle with request batching"""
        
        if self.pipeline_requests and redis_manager.is_enabled():
            return await self._handle_with_batching(context, next_handler)
        else:
            return await super().handle(context, next_handler)
    
    async def _handle_with_batching(self, context: Dict[str, Any], next_handler):
        """Handle requests with Redis pipelining for better performance"""
        
        # Add to batch
        request_info = {
            'context': context,
            'handler': next_handler,
            'key': self.key_generator(context),
            'timestamp': time.time()
        }
        
        self.request_batch.append(request_info)
        
        # Process batch if full or timeout reached
        if (len(self.request_batch) >= self.batch_size or 
            time.time() - self.last_batch_flush > self.batch_timeout):
            
            return await self._process_batch()
        
        # For now, process individually (in production, you'd need async batching)
        return await super().handle(context, next_handler)
    
    async def _process_batch(self):
        """Process batch of requests with Redis pipeline"""
        
        if not self.request_batch:
            return
        
        # This is a simplified version - production would need proper async batching
        batch = self.request_batch
        self.request_batch = []
        self.last_batch_flush = time.time()
        
        # Process each request (simplified)
        for request_info in batch:
            await super().handle(request_info['context'], request_info['handler'])

# Production configuration
production_limiter = OptimizedRateLimitMiddleware(
    max_requests=1000,
    window_seconds=3600,
    strategy="sliding_window",
    fallback_enabled=True,
    whitelist=[
        "admin/*",
        "health/*",
        "monitoring/*"
    ],
    custom_error_message="Rate limit exceeded. Please implement exponential backoff and try again.",
    redis_key_prefix="prod_rate_limit",
    block_duration=3600  # Block for 1 hour after limit exceeded
)
```

## Next Steps

- [Basic Rate Limiting](basic-rate-limiting.md) - Review fundamentals
- [Rate Limiting Strategies](strategies.md) - Choose the right algorithm  
- [Topic-Specific Limits](topic-specific.md) - Implement topic-based limits
- [Client-Based Limiting](client-based.md) - Rate limit by client identity
