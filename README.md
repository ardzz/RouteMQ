<img alt="logo.png" height="200" src="logo.png" width="200"/>

# RouteMQ Framework

A flexible MQTT routing framework with middleware support, dynamic router loading, Redis integration, and horizontal scaling capabilities, inspired by web frameworks.

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ
uv sync

# Initialize project
python main.py --init

# Configure .env file with your MQTT broker details
# Run the application
uv run python main.py --run
```

## ✨ Features

- **Dynamic Router Loading** - Automatically discover and load routes from multiple files
- **Route-based MQTT topic handling** - Define routes using a clean, expressive syntax
- **Middleware support** - Process messages through middleware chains
- **Parameter extraction** - Extract variables from MQTT topics using Laravel-style syntax
- **Shared Subscriptions** - Horizontal scaling with worker processes
- **Redis Integration** - Optional Redis support for distributed caching and rate limiting
- **Advanced Rate Limiting** - Multiple rate limiting strategies with Redis backend
- **Optional MySQL integration** - Use with or without a database
- **Environment-based configuration** - Flexible configuration through .env files

## 📚 Documentation

**Complete documentation is available in the [docs](./docs) folder, optimized for GitBook integration.**

### Quick Links

- **[Getting Started](./docs/getting-started/README.md)** - Installation, quick start, and basic setup
- **[Configuration](./docs/configuration/README.md)** - Environment variables and setup options
- **[Routing](./docs/routing/README.md)** - Route definition, parameters, and organization
- **[Controllers](./docs/controllers/README.md)** - Creating and organizing business logic
- **[Middleware](./docs/middleware/README.md)** - Request processing and middleware chains
- **[Redis Integration](./docs/redis/README.md)** - Caching, sessions, and distributed features
- **[Rate Limiting](./docs/rate-limiting/README.md)** - Advanced rate limiting strategies
- **[Examples](./docs/examples/README.md)** - Practical examples and use cases
- **[API Reference](./docs/api-reference/README.md)** - Complete API documentation
- **[FAQ](./docs/faq.md)** - Frequently asked questions

## 🏗️ Project Structure

```
RouteMQ/
├── docs/                   # 📖 Complete documentation
├── app/                    # 🚀 Your application code
│   ├── controllers/        # 🎮 Route handlers
│   ├── middleware/         # 🔧 Custom middleware
│   ├── models/            # 🗄️ Database models
│   └── routers/           # 🛣️ Route definitions
├── core/                  # ⚡ Framework core
├── bootstrap/             # 🌟 Application bootstrap
└── tests/                 # 🧪 Test files
```

## 🤝 Contributing

We welcome contributions! Please see our documentation for development setup and contribution guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

**📖 For detailed documentation, examples, and guides, visit the [docs](./docs) folder.**
