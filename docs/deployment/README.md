# Deployment

Learn how to deploy RouteMQ in production environments.

## Topics

- [Docker Deployment](docker.md) - Containerized deployment
- [Scaling](scaling.md) - Horizontal and vertical scaling
- [Load Balancing](load-balancing.md) - Distributing traffic

## Quick Docker Deployment

Run with Docker:

```bash
# Build the image
docker build -t routemq .

# Run with docker-compose (includes MQTT broker, MySQL, and Redis)
docker-compose up
```

## Docker Compose Example

```yaml
version: '3.8'

services:
  routemq:
    build: .
    depends_on:
      - mqtt
      - mysql
      - redis
    environment:
      - MQTT_BROKER=mqtt
      - ENABLE_MYSQL=true
      - DB_HOST=mysql
      - ENABLE_REDIS=true
      - REDIS_HOST=redis
    volumes:
      - ./app:/app/app
      - ./.env:/app/.env

  mqtt:
    image: eclipse-mosquitto:2.0
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./docker/mosquitto.conf:/mosquitto/config/mosquitto.conf

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: mqtt_framework
    ports:
      - "3306:3306"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
```

## Production Considerations

- **Environment Variables**: Use secure secret management
- **Database Connections**: Configure connection pooling
- **Redis Clustering**: Use Redis cluster for high availability
- **Monitoring**: Set up application and infrastructure monitoring
- **Logging**: Centralized logging with log aggregation
- **Security**: TLS/SSL, authentication, authorization

## Next Steps

- [Docker Deployment](docker.md) - Detailed Docker setup
- [Production Configuration](production-config.md) - Production settings
- [Monitoring](../monitoring/README.md) - Application monitoring
