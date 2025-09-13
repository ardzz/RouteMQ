# RouteMQ Tinker - Interactive REPL

The RouteMQ Tinker is an interactive REPL (Read-Eval-Print Loop) environment similar to Laravel Artisan Tinker. It allows you to test your ORM relationships, queries, and interact with your application components in real-time.

## Features

- 🔧 Interactive Python shell with async/await support
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

All your models from `app/models/` are automatically imported and available by their class names.

## Example Usage

### Basic Queries

```python
# Get all devices
result = await session.execute(select(Device))
devices = result.scalars().all()

# Get a specific device
result = await session.execute(select(Device).where(Device.device_id == 'sensor-001'))
device = result.scalar_one_or_none()
```

### Creating Records

```python
# Create a new device
device = Device(
    device_id='test-001',
    name='Test Device',
    device_type='sensor',
    status='active'
)
session.add(device)
await session.commit()

# Create a sensor for the device
sensor = Sensor(
    device_id=device.id,
    sensor_type='temperature',
    unit='°C'
)
session.add(sensor)
await session.commit()
```

### Working with Relationships

```python
# Get device with related data
result = await session.execute(
    select(Device).where(Device.id == 1)
)
device = result.scalar_one_or_none()

if device:
    # Refresh to load relationships
    await session.refresh(device, ['messages', 'sensors'])
    
    print(f"Device: {device.name}")
    print(f"Messages: {len(device.messages)}")
    print(f"Sensors: {len(device.sensors)}")
    
    # Access related sensors
    for sensor in device.sensors:
        print(f"Sensor: {sensor.sensor_type} ({sensor.unit})")
```

### Complex Queries

```python
# Query with joins and filters
from sqlalchemy.orm import selectinload

result = await session.execute(
    select(Device)
    .options(selectinload(Device.sensors))
    .where(Device.status == 'active')
    .order_by(Device.created_at.desc())
)
active_devices = result.scalars().all()

# Count sensors by type
result = await session.execute(
    select(Sensor.sensor_type, func.count(Sensor.id))
    .group_by(Sensor.sensor_type)
)
sensor_counts = result.all()
```

### Redis Operations (if enabled)

```python
# Set a value in Redis
await redis_manager.set('test_key', 'test_value')

# Get a value from Redis
value = await redis_manager.get('test_key')
print(value)

# Work with JSON data
device_data = {'device_id': 'sensor-001', 'temperature': 25.5}
await redis_manager.set('device:sensor-001', device_data)
cached_data = await redis_manager.get('device:sensor-001')
```

## Tips

- Use `;` at the end of a line to suppress output printing
- Press `Tab` for auto-completion
- Use `Ctrl+D` or type `exit()` to quit
- All operations are asynchronous, so use `await` for database and Redis operations
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

### Event Loop Issues

The tinker environment handles asyncio event loop conflicts automatically using `nest-asyncio`. If you still encounter issues, try restarting the tinker session.
