# Monitoring and Metrics

Monitor RouteMQ health, readiness, structured logs, and stdlib observability hooks. RouteMQ ships a
small built-in health server, backend-neutral JSON logs, and hook seams; it does not bundle a
mandatory Prometheus, OpenTelemetry, or vendor-specific exporter.

## Topics

- [Health Checks](health-checks.md) - Built-in `/health` and `/ready` endpoints
- [Metrics Collection](metrics.md) - Observability hook seam and custom metric collection
- [Logging Configuration](../configuration/logging.md) - JSON/NDJSON logs, field profiles, and lifecycle events
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

# Check stdout logs when running in Docker
docker compose logs -f app

# Or tail a file when LOG_TO_FILE=true
tail -f logs/app.log
```

## Debug Mode

Enable debug logging:

```env
LOG_LEVEL=DEBUG
```

RouteMQ defaults to `LOG_FORMATTER=json` and `LOG_FIELD_PROFILE=otel`, so debug output remains one
JSON object per line unless you explicitly set `LOG_FORMATTER=plain`.

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
