# Redis Monitoring

When Redis is enabled, monitor both Redis server health and RouteMQ queue behavior.

## Redis server checks

Useful Redis commands:

```bash
redis-cli ping
redis-cli info stats
redis-cli info memory
redis-cli slowlog get 10
```

## RouteMQ queue keys

The Redis queue driver stores ready, delayed, reserved, and failed jobs in separate Redis structures.
Operational checks should watch:

- ready queue depth;
- delayed job count;
- reserved job count;
- failed job count;
- Redis memory pressure and command latency.

## Reliability note

RouteMQ currently records reserved jobs, but automatic lease reaping for worker crashes is future work.
If workers are interrupted, inspect reserved and failed job keys before restarting high-volume queues.
