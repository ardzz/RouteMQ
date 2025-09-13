## v0.2.1 (2025-09-13)

### Refactor

- Add example files for middleware and router in the application

## v0.2.0 (2025-09-13)

### Feat

- Add Commitizen for conventional commit management and create release workflow
- Update Docker setup and enhance README for uv integration
- Enhance README with Redis integration and rate limiting details
- Add Redis integration and rate limiting middleware
- Implement dynamic router loading and enhance worker management
- Implement worker management for shared MQTT subscriptions
- Add initial implementation of RouteMQ framework with MQTT and MySQL support

### Fix

- update release workflow permissions and add GitHub token for checkout
- Update router path to point to device.py for correct routing

### Refactor

- Update logger names to use RouteMQ namespace for consistency
- Refactor RedisManager to improve type hinting and logging
