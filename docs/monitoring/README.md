# Monitoring and Metrics

Monitor RouteMQ health, readiness, logs, and stdlib observability hooks. RouteMQ currently ships a
small built-in health server and backend-neutral trace/metric hook seam; it does not bundle a
mandatory Prometheus or OpenTelemetry exporter.

## Topics

- [Health Checks](health-checks.md) - Built-in `/health` and `/ready` endpoints
- [Metrics Collection](metrics.md) - Observability hook seam and custom metric collection
- [Redis Monitoring](redis-monitoring.md) - Redis operations to monitor when Redis is enabled
- [MQTT Monitoring](mqtt-monitoring.md) - MQTT connectivity, readiness, and broker signals

## Built-in health endpoints

Set `HEALTH_HTTP_ENABLED=true` to expose a small HTTP server from the running application process.
The server provides:

- `GET /health` - liveness; returns `200` while the process is alive.
- `GET /ready` - readiness; returns `200` only after startup completes and MQTT is connected.

Configuration lives in the environment variables documented in
[Environment Variables](../configuration/environment-variables.md#health-and-readiness).

## Observability hooks

```python
from routemq.observability import register_metric_hook, register_trace_hook

def trace_hook(name, attributes):
    print("trace", name, attributes)

def metric_hook(name, value, attributes):
    print("metric", name, value, attributes)

unregister_trace = register_trace_hook(trace_hook)
unregister_metric = register_metric_hook(metric_hook)
```

Hook failures are swallowed and logged at debug level so observability integrations do not break
message processing.

## Performance monitoring

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
