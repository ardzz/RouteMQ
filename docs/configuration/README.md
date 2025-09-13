# Configuration

Learn how to configure RouteMQ for your specific needs.

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

### With Custom Timezone

```env
MQTT_BROKER=localhost
MQTT_PORT=1883
TIMEZONE=Asia/Jakarta
```

## Configuration Files

RouteMQ looks for configuration in this order:

1. Environment variables
2. `.env` file in project root
3. Default values

## Configuration Topics

- **[Environment Variables](environment-variables.md)** - Complete reference of all configuration options
- **[Logging Configuration](logging.md)** - Configure logging levels, formats, and file rotation
- **[Timezone Configuration](timezone.md)** - Set up timezone for logs and application operations

## Next Steps

After configuring your environment:

1. **[Getting Started Guide](../getting-started/README.md)** - Set up your first RouteMQ application
2. **[Routing](../routing/README.md)** - Configure MQTT topic routing
3. **[Controllers](../controllers/README.md)** - Create message handlers
4. **[Middleware](../middleware/README.md)** - Add middleware for cross-cutting concerns
