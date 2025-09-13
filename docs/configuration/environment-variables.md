# Environment Variables

Complete reference for all RouteMQ configuration options.

## MQTT Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | localhost | MQTT broker hostname |
| `MQTT_PORT` | 1883 | MQTT broker port |
| `MQTT_USERNAME` | None | MQTT username (optional) |
| `MQTT_PASSWORD` | None | MQTT password (optional) |
| `MQTT_CLIENT_ID` | mqtt-framework-main | MQTT client ID prefix |
| `MQTT_GROUP_NAME` | mqtt_framework_group | Shared subscription group name |

## Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_MYSQL` | true | Enable/disable MySQL integration |
| `DB_HOST` | localhost | Database hostname |
| `DB_PORT` | 3306 | Database port |
| `DB_NAME` | mqtt_framework | Database name |
| `DB_USER` | root | Database username |
| `DB_PASS` | (empty) | Database password |

## Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_REDIS` | false | Enable/disable Redis integration |
| `REDIS_HOST` | localhost | Redis hostname |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_DB` | 0 | Redis database number |
| `REDIS_PASSWORD` | None | Redis password (optional) |
| `REDIS_USERNAME` | None | Redis username (optional) |
| `REDIS_MAX_CONNECTIONS` | 10 | Redis connection pool size |
| `REDIS_SOCKET_TIMEOUT` | 5.0 | Redis socket timeout |

## Logging Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | %(asctime)s - %(name)s - %(levelname)s - %(message)s | Log message format |

## Example .env File

```env
# MQTT Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password
MQTT_CLIENT_ID=mqtt-framework-main
MQTT_GROUP_NAME=mqtt_framework_group

# Database Configuration
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password

# Redis Configuration
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password
REDIS_USERNAME=your_redis_username
REDIS_MAX_CONNECTIONS=10
REDIS_SOCKET_TIMEOUT=5.0

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```
