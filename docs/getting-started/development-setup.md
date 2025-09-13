# Development Setup

Set up your development environment for contributing to RouteMQ or building custom features.

## Development Installation

Install RouteMQ with development dependencies:

```bash
# Install with development dependencies
uv sync --extra dev
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
uv add --dev pytest-cov
```

### Removing Dependencies

```bash
uv remove package-name
```

## Running the Application

```bash
# Run the application
uv run python main.py --run

# Run with specific configuration
uv run python main.py --run --config custom.env
```

## Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_router.py

# Run with coverage
uv run pytest --cov=core --cov-report=html
```

## Development Commands

```bash
# Run tests
python run_tests.py

# Check code style (if configured)
uv run flake8 .

# Format code (if black is installed)
uv run black .
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
├── core/                  # Framework core
├── docs/                  # Documentation
├── tests/                 # Test files
├── main.py               # Entry point
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
