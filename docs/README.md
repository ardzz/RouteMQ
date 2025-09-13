# RouteMQ Framework Documentation

Welcome to the RouteMQ Framework documentation! This guide will help you get started and master all the features of this flexible MQTT routing framework.

## Table of Contents

- [Getting Started](getting-started/README.md) - Installation, quick start, and basic setup
- [Core Concepts](core-concepts/README.md) - Understanding the framework architecture
- [Configuration](configuration/README.md) - Environment variables and setup options
- [Routing](routing/README.md) - Route definition, parameters, and organization
- [Controllers](controllers/README.md) - Creating and organizing business logic
- [Middleware](middleware/README.md) - Request processing and middleware chains
- [Redis Integration](redis/README.md) - Caching, sessions, and distributed features
- [Rate Limiting](rate-limiting/README.md) - Advanced rate limiting strategies
- [Database](database/README.md) - MySQL integration and models
- [Testing](testing/README.md) - Writing and running tests
- [Deployment](deployment/README.md) - Docker, production setup, and scaling
- [Monitoring](monitoring/README.md) - Metrics, health checks, and debugging
- [API Reference](api-reference/README.md) - Complete API documentation
- [Examples](examples/README.md) - Practical examples and use cases
- [Troubleshooting](troubleshooting/README.md) - Common issues and solutions

## Quick Links

- [Installation Guide](getting-started/installation.md)
- [Your First Route](getting-started/first-route.md)
- [Configuration Reference](configuration/environment-variables.md)
- [Best Practices](best-practices.md)
- [FAQ](faq.md)

## About RouteMQ

RouteMQ is a flexible MQTT routing framework with middleware support, dynamic router loading, Redis integration, and horizontal scaling capabilities, inspired by web frameworks.

### Key Features

- **Dynamic Router Loading**: Automatically discover and load routes from multiple files
- **Route-based MQTT topic handling**: Define routes using a clean, expressive syntax
- **Middleware support**: Process messages through middleware chains
- **Parameter extraction**: Extract variables from MQTT topics using Laravel-style syntax
- **Shared Subscriptions**: Horizontal scaling with worker processes for high-throughput routes
- **Redis Integration**: Optional Redis support for distributed caching and rate limiting
- **Advanced Rate Limiting**: Multiple rate limiting strategies with Redis backend
- **Optional MySQL integration**: Use with or without a database
- **Group-based routing**: Group routes with shared prefixes and middleware
- **Context manager for route groups**: Use Python's `with` statement for cleaner route definitions
- **Environment-based configuration**: Flexible configuration through .env files
- **Comprehensive logging**: Built-in logging with configurable levels
