# RouteMQ Tinker - Interactive REPL

The RouteMQ Tinker is an interactive REPL (Read-Eval-Print Loop) environment similar to Laravel Artisan Tinker. It allows you to test your ORM relationships, queries, and interact with your application components in real-time.

## Features

- 🔧 Interactive Python shell with async/await support via `run_async()` helper
- 📊 Pre-loaded ORM models and database session
- 🔍 SQLAlchemy query helpers (select, and_, or_, func, etc.)
- 🚀 Redis manager integration (if enabled)
- 📝 Auto-completion and syntax highlighting via IPython

## Usage

### Starting Tinker

```bash
# Start the interactive REPL
python main.py --tinker
```

### Available Objects

When you start tinker, the following objects are automatically available:

- `app` - Application instance
- `Model` - Base Model class
- `Base` - SQLAlchemy declarative base
- `session` - Database session (if MySQL is enabled)
- `redis_manager` - Redis manager (if Redis is enabled)
- `select` - SQLAlchemy select function
- `and_`, `or_` - SQLAlchemy logical operators
- `func` - SQLAlchemy functions
- `desc`, `asc` - SQLAlchemy ordering functions
- `run_async()` - Helper function to execute async operations

All your models from `app/models/` are automatically imported and available by their class names.

## Example Usage

### Basic Queries

Since all database operations are async, you need to use the `run_async()` helper function:

```python
# Get all devices using run_async helper
result = run_async(session.execute(select(Device)))
devices = result.scalars().all()

# Get a specific device
result = run_async(session.execute(select(Device).where(Device.device_id == 'sensor-001')))
device = result.scalar_one_or_none()

# Using the built-in helper functions
devices = run_async(query_devices())
users = run_async(query_users())
```

### Creating Records

```python
# Create a new device
device = Device(
    device_id='test-001',
    name='Test Device',
    description='Created from tinker',
    status='active'
)
session.add(device)
run_async(session.commit())

# Or use the helper function
new_device = run_async(create_sample_device())
print(new_device)
```

### Working with Relationships

```python
# Get device with related data
result = run_async(session.execute(select(Device).where(Device.id == 1)))
device = result.scalar_one_or_none()

if device:
    # Refresh to load relationships (adjust relationship names based on your models)
    run_async(session.refresh(device, ['trips', 'user_devices']))
    
    print(f"Device: {device.name}")
    print(f"Related trips: {len(device.trips) if hasattr(device, 'trips') else 'N/A'}")
    print(f"User devices: {len(device.user_devices) if hasattr(device, 'user_devices') else 'N/A'}")
```

### Complex Queries

```python
# Query with joins and filters
from sqlalchemy.orm import selectinload

result = run_async(session.execute(
    select(Device)
    .options(selectinload(Device.trips))  # Adjust based on your relationships
    .where(Device.status == 'active')
    .order_by(Device.created_at.desc())
))
active_devices = result.scalars().all()

# Count devices by status
result = run_async(session.execute(
    select(Device.status, func.count(Device.id))
    .group_by(Device.status)
))
device_counts = result.all()
print("Device counts by status:", device_counts)

# Query users with their devices
result = run_async(session.execute(
    select(User)
    .options(selectinload(User.user_devices))  # Adjust based on your relationships
))
users_with_devices = result.scalars().all()
```

### Redis Operations (if enabled)

```python
# Set a value in Redis
run_async(redis_manager.set('test_key', 'test_value'))

# Get a value from Redis
value = run_async(redis_manager.get('test_key'))
print(value)

# Work with JSON data
device_data = {'device_id': 'sensor-001', 'temperature': 25.5}
run_async(redis_manager.set('device:sensor-001', device_data))
cached_data = run_async(redis_manager.get('device:sensor-001'))
```

## Available Helper Functions

The tinker environment provides several pre-built helper functions:

- `query_devices()` - Get all devices from the database
- `query_users()` - Get all users from the database  
- `create_sample_device()` - Create a sample device with timestamp
- `run_async(coroutine)` - Execute any async operation

## Important: Using `run_async()`

Since your application uses async/await patterns for database operations, you **must** wrap all async calls with `run_async()`:

```python
# ✅ CORRECT - Using run_async()
result = run_async(session.execute(select(Device)))
devices = result.scalars().all()

# ❌ INCORRECT - This will cause a SyntaxError
result = await session.execute(select(Device))  # Don't do this in tinker
```

## Tips

- **Always use `run_async()`** for database operations and other async functions
- Use `;` at the end of a line to suppress output printing
- Press `Tab` for auto-completion
- Use `Ctrl+D` or type `exit()` to quit
- All your models are automatically imported and available by name
- The session is automatically created and available when MySQL is enabled

## Prerequisites

Make sure you have the following dependencies installed:

```bash
pip install IPython==8.16.1 nest-asyncio==1.5.8
```

## Configuration

Enable MySQL in your `.env` file for database operations:

```env
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=your_database
DB_USER=your_username
DB_PASS=your_password
```

Enable Redis if you want to test Redis operations:

```env
ENABLE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
```

## Real-World Examples

Here are some practical examples using your actual models:

### Working with Devices and Trips

```python
# Get all active devices
result = run_async(session.execute(
    select(Device).where(Device.status == 'active')
))
active_devices = result.scalars().all()
print(f"Found {len(active_devices)} active devices")

# Get a device with its trips
result = run_async(session.execute(
    select(Device)
    .options(selectinload(Device.trips))
    .where(Device.device_id == 'your-device-id')
))
device = result.scalar_one_or_none()
if device:
    print(f"Device {device.name} has {len(device.trips)} trips")
```

### Parameter Values and States

```python
# Query parameter values for a specific device
result = run_async(session.execute(
    select(ParameterValue)
    .join(DeviceParameter)
    .join(Device)
    .where(Device.device_id == 'your-device-id')
))
param_values = result.scalars().all()
print(f"Found {len(param_values)} parameter values")

# Check parameter states
result = run_async(session.execute(select(ParameterState)))
states = result.scalars().all()
for state in states:
    print(f"Parameter State: {state}")
```

### Creating Test Data

```python
# Create a test device with parameters
device = Device(
    device_id='test-device-001',
    name='Test Device',
    description='Test device created in tinker',
    status='active'
)
session.add(device)
run_async(session.commit())

# Create a parameter for the device
param = DeviceParameter(
    device_id=device.id,
    parameter_name='temperature',
    unit='°C'
)
session.add(param)
run_async(session.commit())

print(f"Created device {device.device_id} with parameter {param.parameter_name}")
```

## Troubleshooting

### Database Not Available

If you see "Database is disabled in configuration", make sure:
1. `ENABLE_MYSQL=true` in your `.env` file
2. Database credentials are correct
3. MySQL server is running

### Models Not Imported

If your models aren't showing up:
1. Make sure they're in the `app/models/` directory
2. They should inherit from `Base`
3. They should have a `__tablename__` attribute

### Async Issues

If you encounter async-related errors:
1. Always use `run_async()` for database operations
2. Don't use bare `await` statements in the REPL
3. The tinker environment handles event loop conflicts automatically

### SyntaxError with await

If you get "SyntaxError: 'await' outside function":
```python
# ❌ Don't do this
result = await session.execute(select(Device))

# ✅ Do this instead
result = run_async(session.execute(select(Device)))
```
