# Getting Started

This section will help you get RouteMQ up and running quickly.

## Topics

- [Installation](installation.md) - Install RouteMQ and its dependencies
- [Quick Start](quick-start.md) - Get your first route running
- [First Route](first-route.md) - Create your first MQTT route
- [Development Setup](development-setup.md) - Set up your development environment

## What is RouteMQ?

RouteMQ is a flexible MQTT routing framework with middleware support, dynamic router loading, Redis integration, and horizontal scaling capabilities, inspired by web frameworks.

### Key Features

- **Dynamic Router Loading**: Automatically discover and load routes from multiple files
- **Route-based MQTT topic handling**: Define routes using a clean, expressive syntax
- **Middleware support**: Process messages through middleware chains
- **Parameter extraction**: Extract variables from MQTT topics using Laravel-style syntax
- **Shared Subscriptions**: Horizontal scaling with worker processes for high-throughput routes
- **Redis Integration**: Optional Redis support for distributed caching and rate limiting
- **Advanced Rate Limiting**: Multiple rate limiting strategies with Redis backend

## Next Steps

After installation, check out the [Quick Start](quick-start.md) guide to create your first route.
