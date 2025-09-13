# Configuration

Learn how to configure RouteMQ for your specific needs.

## Topics

- [Environment Variables](environment-variables.md) - Complete list of configuration options
- [MQTT Configuration](mqtt-configuration.md) - MQTT broker setup
- [Database Configuration](database-configuration.md) - MySQL setup
- [Redis Configuration](redis-configuration.md) - Redis integration
- [Logging Configuration](logging-configuration.md) - Logging setup

## Configuration Overview

RouteMQ uses environment variables for configuration, typically stored in a `.env` file in your project root.

## Quick Configuration

### Basic MQTT Setup

```env
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password
```

### With Redis (Recommended)

```env
MQTT_BROKER=localhost
MQTT_PORT=1883
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
```

### With Database

```env
MQTT_BROKER=localhost
MQTT_PORT=1883
ENABLE_MYSQL=true
DB_HOST=localhost
DB_NAME=routemq
DB_USER=root
DB_PASS=password
```

## Configuration Files

RouteMQ looks for configuration in this order:

1. Environment variables
2. `.env` file in project root
3. Default values

## Next Steps

- [Environment Variables](environment-variables.md) - See all available options
- [MQTT Configuration](mqtt-configuration.md) - Detailed MQTT setup
