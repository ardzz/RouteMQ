# Development Setup

Set up your development environment for contributing to RouteMQ or building custom features.

## Development Installation

Install RouteMQ with development dependencies:

```bash
# Install with development dependencies
uv sync --all-extras --dev
```

This includes additional tools for testing, linting, and development.

## Managing Dependencies

### Adding Dependencies

```bash
# Add a regular dependency
uv add package-name

# Add an optional dependency (e.g., Redis)
uv add --optional redis redis

# Add a development dependency
uv add --dev coverage
```

### Removing Dependencies

```bash
uv remove package-name
```

## Running the Application

```bash
# Run the application
uv run routemq run

# Run with specific configuration
uv run routemq run
```

## Running Tests

```bash
# Run all tests
uv run python run_tests.py

# Run a specific unittest module
uv run python -m unittest tests.unit.test_router

# Run Docker-backed integration tests
RUN_INTEGRATION_TESTS=1 uv run python -m unittest tests.integration.test_queue_backends tests.integration.test_mqtt_end_to_end

# Run with coverage using pyproject configuration
uv run coverage run && uv run coverage report -m
```

## Development Commands

```bash
# Run tests
uv run python run_tests.py

# Check code style
uv run ruff check .

# Check formatting
uv run ruff format --check .
```

## Project Structure

```
RouteMQ/
├── app/                    # Application code
│   ├── controllers/        # Route handlers
│   ├── middleware/         # Custom middleware
│   ├── models/            # Database models
│   └── routers/           # Route definitions
├── bootstrap/             # Application bootstrap
├── routemq/               # Framework core (CLI lives at routemq/cli.py; installed as `routemq` console script)
├── docs/                  # Documentation
├── tests/                 # Test files
└── pyproject.toml        # Project configuration
```

## Development Best Practices

1. **Write Tests**: Add tests for new features in the `tests/` directory
2. **Follow Naming Conventions**: Use clear, descriptive names for files and classes
3. **Document Your Code**: Add docstrings to functions and classes
4. **Use Type Hints**: Add type hints for better code clarity
5. **Keep Routes Organized**: Group related routes in separate files

## Next Steps

- [Create Your First Route](first-route.md) - Learn route creation
- [Core Concepts](../core-concepts/README.md) - Understand the architecture
