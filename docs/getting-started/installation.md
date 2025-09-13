# Installation

This guide will help you install RouteMQ and its dependencies.

## Prerequisites

- Python 3.8 or higher
- Git (for cloning the repository)

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/ardzz/RouteMQ.git
cd RouteMQ
```

### 2. Install UV Package Manager

If you don't have `uv` installed:

```bash
# On Unix/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Install Dependencies

```bash
# Install basic dependencies
uv sync

# Or install with all optional dependencies (including Redis)
uv sync --extra all
```

## Installation Options

### Basic Installation
For basic MQTT functionality without Redis or MySQL:
```bash
uv sync
```

### Full Installation
For all features including Redis and MySQL support:
```bash
uv sync --extra all
```

### Development Installation
For development with testing and linting tools:
```bash
uv sync --extra dev
```

## Verify Installation

Run the following command to verify the installation:

```bash
uv run python main.py --help
```

You should see the RouteMQ help message with available commands.

## Next Steps

- [Quick Start](quick-start.md) - Get your first route running
- [Development Setup](development-setup.md) - Set up your development environment
