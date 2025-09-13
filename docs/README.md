# RouteMQ Framework Documentation

{% hint style="warning" %}
RouteMQ **isn’t production-ready** yet. Use only in test/staging. Known gaps: stability, security hardening, performance tuning, docs. I’ll post updates as we land fixes.
{% endhint %}

<figure><img src=".gitbook/assets/Logo1-500x500.png" alt=""><figcaption></figcaption></figure>

Welcome to the RouteMQ Framework documentation! This guide will help you get started and master all the features of this flexible MQTT routing framework.

## Table of Contents

* [Getting Started](getting-started/) - Installation, quick start, and basic setup
* [Core Concepts](core-concepts/) - Understanding the framework architecture
* [Configuration](configuration/) - Environment variables and setup options
* [Routing](routing/) - Route definition, parameters, and organization
* [Controllers](controllers/) - Creating and organizing business logic
* [Middleware](middleware/) - Request processing and middleware chains
* [Redis Integration](redis/) - Caching, sessions, and distributed features
* [Rate Limiting](rate-limiting/) - Advanced rate limiting strategies
* [Database](database/) - MySQL integration and models
* [Testing](testing/) - Writing and running tests
* [Deployment](deployment/) - Docker, production setup, and scaling
* [Monitoring](monitoring/) - Metrics, health checks, and debugging
* [API Reference](api-reference/) - Complete API documentation
* [Examples](examples/) - Practical examples and use cases
* [Troubleshooting](troubleshooting/) - Common issues and solutions

## Quick Links

* [Installation Guide](getting-started/installation.md)
* [Your First Route](getting-started/first-route.md)
* [Configuration Reference](configuration/environment-variables.md)
* [Best Practices](best-practices.md)
* [FAQ](faq.md)

## About RouteMQ

RouteMQ is a flexible MQTT routing framework with middleware support, dynamic router loading, Redis integration, and horizontal scaling capabilities, inspired by web frameworks.

### Key Features

* **Dynamic Router Loading**: Automatically discover and load routes from multiple files
* **Route-based MQTT topic handling**: Define routes using a clean, expressive syntax
* **Middleware support**: Process messages through middleware chains
* **Parameter extraction**: Extract variables from MQTT topics using Laravel-style syntax
* **Shared Subscriptions**: Horizontal scaling with worker processes for high-throughput routes
* **Redis Integration**: Optional Redis support for distributed caching and rate limiting
* **Advanced Rate Limiting**: Multiple rate limiting strategies with Redis backend
* **Optional MySQL integration**: Use with or without a database
* **Group-based routing**: Group routes with shared prefixes and middleware
* **Context manager for route groups**: Use Python's `with` statement for cleaner route definitions
* **Environment-based configuration**: Flexible configuration through .env files
* **Comprehensive logging**: Built-in logging with configurable levels
