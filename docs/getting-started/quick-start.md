# Quick Start

Get RouteMQ up and running in just a few minutes.

## 1. Initialize Your Project

After installation, initialize a new RouteMQ project:

```bash
python main.py --init
```

This creates the basic project structure and configuration files.

## 2. Configure Your Environment

Edit the `.env` file with your MQTT broker details:

```env
# MQTT Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=your_username  # Optional
MQTT_PASSWORD=your_password  # Optional
MQTT_CLIENT_ID=mqtt-framework-main  # Optional
MQTT_GROUP_NAME=mqtt_framework_group  # For shared subscriptions

# Database Configuration (Optional)
ENABLE_MYSQL=false

# Redis Configuration (Optional)
ENABLE_REDIS=false

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

## 3. Run the Application

Start RouteMQ:

```bash
uv run python main.py --run
```

Your MQTT routing framework is now running and ready to handle messages!

## 4. Test Your Setup

You can test your setup by publishing a message to any of the example routes that are created during initialization.

## What's Next?

- [Create Your First Route](first-route.md) - Learn how to define custom routes
- [Configuration Guide](../configuration/README.md) - Detailed configuration options
- [Core Concepts](../core-concepts/README.md) - Understand the framework architecture
