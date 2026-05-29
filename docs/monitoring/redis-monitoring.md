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

RouteMQ records reserved jobs and refreshes active reservations with worker heartbeats. If a worker
crashes and stops refreshing a reservation, the worker reaper returns the job to the ready queue after
`QUEUE_VISIBILITY_TIMEOUT` seconds, or moves it to failed-job storage when attempts are exhausted. The
reaper runs every `QUEUE_REAPER_INTERVAL` seconds from active queue workers.

Redis worker heartbeat metadata is stored as `routemq:queue:workers:{worker_id}` with a TTL of roughly
three heartbeat intervals. Inspect these keys when diagnosing stuck workers:

```bash
redis-cli keys 'routemq:queue:workers:*'
redis-cli hgetall routemq:queue:workers:<worker_id>
redis-cli llen routemq:queue:default
redis-cli llen routemq:queue:default:reserved
redis-cli zcard routemq:queue:default:delayed
redis-cli llen routemq:queue:failed:default
```
