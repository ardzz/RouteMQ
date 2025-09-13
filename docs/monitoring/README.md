# Monitoring and Metrics

Monitor your RouteMQ application performance and health.

## Topics

- [Health Checks](health-checks.md) - Application health monitoring
- [Metrics Collection](metrics.md) - Performance metrics and statistics
- [Redis Monitoring](redis-monitoring.md) - Redis performance tracking
- [MQTT Monitoring](mqtt-monitoring.md) - MQTT broker monitoring

## Health Check Endpoint

```python
from core.redis_manager import redis_manager
from core.controller import Controller

class HealthController(Controller):
    @staticmethod
    async def health_check(payload, client):
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "services": {}
        }
        
        # Check Redis
        if redis_manager.is_enabled():
            try:
                await redis_manager.set("health_check", "ok", ex=10)
                health_status["services"]["redis"] = "healthy"
            except:
                health_status["services"]["redis"] = "unhealthy"
                health_status["status"] = "degraded"
        
        return health_status
```

## Redis-Based Metrics

```python
from core.redis_manager import redis_manager

class MetricsMiddleware(Middleware):
    async def handle(self, context, next_handler):
        topic = context['topic']
        
        # Track message counts
        await redis_manager.incr(f"metrics:messages:{topic}")
        await redis_manager.incr("metrics:messages:total")
        
        # Track processing time
        start_time = time.time()
        result = await next_handler(context)
        processing_time = time.time() - start_time
        
        # Store processing time metrics
        await redis_manager.set_json(f"metrics:processing_time:{topic}", {
            "last": processing_time,
            "timestamp": time.time()
        }, ex=3600)
        
        return result
```

## Performance Monitoring

Monitor your application performance:

```bash
# Check Redis statistics
redis-cli info stats

# Monitor MQTT broker
mosquitto_sub -h localhost -t '$SYS/#' -v

# Check application logs
tail -f logs/app.log
```

## Debug Mode

Enable debug logging:

```env
LOG_LEVEL=DEBUG
```

This shows detailed information about:
- Route discovery and loading
- Message processing and middleware execution
- Worker management
- Redis operations and connection status
- Rate limiting decisions

## Next Steps

- [Health Checks](health-checks.md) - Set up health monitoring
- [Metrics](metrics.md) - Collect performance data
- [Troubleshooting](../troubleshooting/README.md) - Debug common issues
