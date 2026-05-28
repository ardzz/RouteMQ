# MQTT Monitoring

RouteMQ readiness depends on MQTT connectivity. Monitor both RouteMQ logs and broker-level signals.

## RouteMQ readiness

Enable the health server and use `/ready` as the primary RouteMQ signal. The app marks readiness true
after startup completes and the MQTT client connects, then marks it false when MQTT disconnects or
shutdown begins.

## Broker signals

For Mosquitto-compatible brokers, `$SYS/#` topics can provide broker uptime, client counts, and message
statistics:

```bash
mosquitto_sub -h localhost -t '$SYS/#' -v
```

## Logs

Set `LOG_LEVEL=DEBUG` temporarily when debugging connection retries, route discovery, or middleware
execution. Avoid leaving debug logging enabled in high-throughput environments.
