# Database Operations

RouteMQ provides async database operations through the Model base class and SQLAlchemy sessions.

## Basic CRUD Operations

### Create Operations

#### Using Model.create()

```python
from core.model import Model
from app.models.sensor_reading import SensorReading

# Create a new sensor reading
reading = await Model.create(
    SensorReading,
    sensor_id="temp_001",
    sensor_type="temperature",
    value=25.6,
    unit="celsius",
    timestamp=time.time()
)

print(f"Created reading with ID: {reading.id}")
```

#### Using Session Directly

```python
from core.model import Model
from app.models.device import Device

async def create_device():
    session = await Model.get_session()
    
    try:
        device = Device(
            device_id="device_123",
            name="Temperature Sensor",
            device_type="sensor",
            status="online"
        )
        
        session.add(device)
        await session.commit()
        await session.refresh(device)  # Get generated ID
        
        return device
    finally:
        await session.close()
```

#### Bulk Create

```python
async def create_multiple_readings(readings_data):
    session = await Model.get_session()
    
    try:
        readings = [
            SensorReading(**data) for data in readings_data
        ]
        
        session.add_all(readings)
        await session.commit()
        
        return readings
    finally:
        await session.close()
```

### Read Operations

#### Using Model.find()

```python
# Find by ID
device = await Model.find(Device, 1)
if device:
    print(f"Found device: {device.name}")
```

#### Using Model.all()

```python
# Get all records
all_devices = await Model.all(Device)
for device in all_devices:
    print(f"Device: {device.device_id} - {device.status}")
```

#### Custom Queries with Sessions

```python
from sqlalchemy.future import select
from sqlalchemy import and_, or_, desc

async def get_online_devices():
    session = await Model.get_session()
    
    try:
        result = await session.execute(
            select(Device).where(Device.status == 'online')
        )
        return result.scalars().all()
    finally:
        await session.close()

async def get_recent_readings(sensor_id: str, hours: int = 24):
    session = await Model.get_session()
    
    cutoff_time = time.time() - (hours * 3600)
    
    try:
        result = await session.execute(
            select(SensorReading)
            .where(
                and_(
                    SensorReading.sensor_id == sensor_id,
                    SensorReading.timestamp >= cutoff_time
                )
            )
            .order_by(desc(SensorReading.timestamp))
        )
        return result.scalars().all()
    finally:
        await session.close()
```

#### Complex Queries

```python
async def get_device_statistics():
    session = await Model.get_session()
    
    try:
        # Count devices by status
        from sqlalchemy import func
        
        result = await session.execute(
            select(
                Device.status,
                func.count(Device.id).label('count')
            )
            .group_by(Device.status)
        )
        
        stats = {}
        for row in result:
            stats[row.status] = row.count
            
        return stats
    finally:
        await session.close()

async def get_sensor_averages(sensor_id: str, start_time: float, end_time: float):
    session = await Model.get_session()
    
    try:
        from sqlalchemy import func
        
        result = await session.execute(
            select(
                func.avg(SensorReading.value).label('avg_value'),
                func.min(SensorReading.value).label('min_value'),
                func.max(SensorReading.value).label('max_value'),
                func.count(SensorReading.id).label('reading_count')
            )
            .where(
                and_(
                    SensorReading.sensor_id == sensor_id,
                    SensorReading.timestamp >= start_time,
                    SensorReading.timestamp <= end_time
                )
            )
        )
        
        row = result.first()
        return {
            'average': float(row.avg_value) if row.avg_value else 0,
            'minimum': float(row.min_value) if row.min_value else 0,
            'maximum': float(row.max_value) if row.max_value else 0,
            'count': row.reading_count
        }
    finally:
        await session.close()
```

### Update Operations

#### Single Record Update

```python
async def update_device_status(device_id: str, new_status: str):
    session = await Model.get_session()
    
    try:
        # Find the device
        result = await session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalars().first()
        
        if device:
            device.status = new_status
            device.last_seen = time.time()
            await session.commit()
            return device
        else:
            return None
    finally:
        await session.close()
```

#### Bulk Update

```python
from sqlalchemy import update

async def mark_devices_offline(device_ids: list):
    session = await Model.get_session()
    
    try:
        await session.execute(
            update(Device)
            .where(Device.device_id.in_(device_ids))
            .values(status='offline', last_seen=time.time())
        )
        await session.commit()
    finally:
        await session.close()
```

#### Update with Conditions

```python
async def update_stale_devices():
    """Mark devices as offline if not seen in 10 minutes"""
    session = await Model.get_session()
    
    cutoff_time = time.time() - (10 * 60)  # 10 minutes ago
    
    try:
        result = await session.execute(
            update(Device)
            .where(
                and_(
                    Device.last_seen < cutoff_time,
                    Device.status == 'online'
                )
            )
            .values(status='offline')
        )
        
        await session.commit()
        return result.rowcount  # Number of updated rows
    finally:
        await session.close()
```

### Delete Operations

#### Single Record Delete

```python
async def delete_device(device_id: str):
    session = await Model.get_session()
    
    try:
        result = await session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalars().first()
        
        if device:
            await session.delete(device)
            await session.commit()
            return True
        return False
    finally:
        await session.close()
```

#### Bulk Delete

```python
from sqlalchemy import delete

async def delete_old_readings(days: int = 30):
    """Delete sensor readings older than specified days"""
    session = await Model.get_session()
    
    cutoff_time = time.time() - (days * 24 * 3600)
    
    try:
        result = await session.execute(
            delete(SensorReading)
            .where(SensorReading.timestamp < cutoff_time)
        )
        
        await session.commit()
        return result.rowcount  # Number of deleted rows
    finally:
        await session.close()
```

## Working with Relationships

### Loading Related Data

```python
from sqlalchemy.orm import selectinload, joinedload

async def get_device_with_readings(device_id: str):
    session = await Model.get_session()
    
    try:
        # Eager load readings with the device
        result = await session.execute(
            select(Device)
            .options(selectinload(Device.sensor_readings))
            .where(Device.device_id == device_id)
        )
        return result.scalars().first()
    finally:
        await session.close()

async def get_devices_with_users():
    session = await Model.get_session()
    
    try:
        # Join load users with devices
        result = await session.execute(
            select(Device)
            .options(joinedload(Device.user))
        )
        return result.scalars().all()
    finally:
        await session.close()
```

### Creating Related Records

```python
async def create_device_with_readings():
    session = await Model.get_session()
    
    try:
        # Create device
        device = Device(
            device_id="sensor_001",
            name="Multi Sensor",
            device_type="sensor"
        )
        session.add(device)
        await session.flush()  # Get the ID without committing
        
        # Create related readings
        readings = [
            SensorReading(
                device_id=device.id,
                sensor_type="temperature",
                value=25.0,
                timestamp=time.time()
            ),
            SensorReading(
                device_id=device.id,
                sensor_type="humidity", 
                value=60.0,
                timestamp=time.time()
            )
        ]
        
        session.add_all(readings)
        await session.commit()
        
        return device
    finally:
        await session.close()
```

## Transaction Management

### Manual Transaction Control

```python
async def transfer_device_ownership(device_id: str, from_user_id: str, to_user_id: str):
    session = await Model.get_session()
    
    try:
        # Start transaction (auto-started with session)
        
        # Find the device
        device_result = await session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = device_result.scalars().first()
        
        if not device or device.user_id != from_user_id:
            raise ValueError("Device not found or not owned by user")
        
        # Update ownership
        device.user_id = to_user_id
        device.updated_at = datetime.utcnow()
        
        # Log the transfer
        transfer_log = TransferLog(
            device_id=device_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            timestamp=time.time()
        )
        session.add(transfer_log)
        
        # Commit transaction
        await session.commit()
        
        return device
        
    except Exception as e:
        # Rollback on error
        await session.rollback()
        raise
    finally:
        await session.close()
```

### Using Context Managers

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_session():
    """Context manager for database sessions"""
    session = await Model.get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# Usage
async def update_multiple_devices():
    async with get_db_session() as session:
        # All operations in this block are in one transaction
        device1 = await session.get(Device, 1)
        device1.status = 'maintenance'
        
        device2 = await session.get(Device, 2) 
        device2.status = 'maintenance'
        
        # Automatically committed when exiting context
```

## Query Optimization

### Pagination

```python
async def get_readings_paginated(sensor_id: str, page: int = 1, per_page: int = 100):
    session = await Model.get_session()
    
    try:
        offset = (page - 1) * per_page
        
        # Get total count
        count_result = await session.execute(
            select(func.count(SensorReading.id))
            .where(SensorReading.sensor_id == sensor_id)
        )
        total = count_result.scalar()
        
        # Get paginated results
        result = await session.execute(
            select(SensorReading)
            .where(SensorReading.sensor_id == sensor_id)
            .order_by(desc(SensorReading.timestamp))
            .offset(offset)
            .limit(per_page)
        )
        readings = result.scalars().all()
        
        return {
            'readings': readings,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    finally:
        await session.close()
```

### Efficient Filtering

```python
async def search_devices(filters: dict):
    session = await Model.get_session()
    
    try:
        query = select(Device)
        
        # Dynamic filtering
        if filters.get('status'):
            query = query.where(Device.status == filters['status'])
        
        if filters.get('device_type'):
            query = query.where(Device.device_type == filters['device_type'])
        
        if filters.get('name_search'):
            query = query.where(Device.name.ilike(f"%{filters['name_search']}%"))
        
        if filters.get('created_after'):
            query = query.where(Device.created_at >= filters['created_after'])
        
        # Apply ordering
        order_by = filters.get('order_by', 'created_at')
        order_direction = filters.get('order_direction', 'desc')
        
        if hasattr(Device, order_by):
            column = getattr(Device, order_by)
            if order_direction == 'desc':
                query = query.order_by(desc(column))
            else:
                query = query.order_by(column)
        
        result = await session.execute(query)
        return result.scalars().all()
        
    finally:
        await session.close()
```

## Using in Controllers

### Controller Integration

```python
from core.controller import Controller
from core.model import Model
from app.models.sensor_reading import SensorReading
from app.models.device import Device

class SensorController(Controller):
    
    async def handle_sensor_data(self, context):
        """Handle incoming sensor data"""
        payload = context['payload']
        device_id = context['params']['device_id']
        
        try:
            # Update device last seen
            await self.update_device_status(device_id, 'online')
            
            # Store sensor reading
            reading = await Model.create(
                SensorReading,
                device_id=device_id,
                sensor_type=payload.get('type', 'unknown'),
                value=payload['value'],
                unit=payload.get('unit'),
                timestamp=payload.get('timestamp', time.time())
            )
            
            # Check for alerts
            await self.check_sensor_alerts(reading)
            
            return {"status": "success", "reading_id": reading.id}
            
        except Exception as e:
            self.logger.error(f"Error processing sensor data: {e}")
            return {"status": "error", "message": str(e)}
    
    async def update_device_status(self, device_id: str, status: str):
        """Update device status and last seen time"""
        session = await Model.get_session()
        
        try:
            result = await session.execute(
                select(Device).where(Device.device_id == device_id)
            )
            device = result.scalars().first()
            
            if device:
                device.status = status
                device.last_seen = time.time()
                await session.commit()
            else:
                # Create new device if not exists
                device = Device(
                    device_id=device_id,
                    name=f"Device {device_id}",
                    device_type="unknown",
                    status=status,
                    last_seen=time.time()
                )
                session.add(device)
                await session.commit()
                
        finally:
            await session.close()
    
    async def get_device_history(self, context):
        """Get device reading history"""
        device_id = context['params']['device_id']
        hours = int(context['payload'].get('hours', 24))
        
        try:
            session = await Model.get_session()
            
            cutoff_time = time.time() - (hours * 3600)
            
            result = await session.execute(
                select(SensorReading)
                .where(
                    and_(
                        SensorReading.device_id == device_id,
                        SensorReading.timestamp >= cutoff_time
                    )
                )
                .order_by(SensorReading.timestamp)
            )
            
            readings = result.scalars().all()
            
            return {
                "device_id": device_id,
                "hours": hours,
                "readings": [reading.to_dict() for reading in readings]
            }
            
        except Exception as e:
            self.logger.error(f"Error getting device history: {e}")
            return {"status": "error", "message": str(e)}
        
        finally:
            await session.close()
```

## Error Handling

### Database Connection Errors

```python
async def safe_database_operation():
    """Example of safe database operation with error handling"""
    if not Model._is_enabled:
        return {"status": "warning", "message": "Database disabled"}
    
    try:
        session = await Model.get_session()
        if not session:
            return {"status": "error", "message": "Could not get database session"}
        
        # Perform database operations
        result = await session.execute(select(Device))
        devices = result.scalars().all()
        
        return {"status": "success", "data": devices}
        
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        return {"status": "error", "message": "Database operation failed"}
    
    finally:
        if 'session' in locals():
            await session.close()
```

### Handling Constraint Violations

```python
from sqlalchemy.exc import IntegrityError

async def create_device_safe(device_data):
    """Create device with duplicate handling"""
    session = await Model.get_session()
    
    try:
        device = Device(**device_data)
        session.add(device)
        await session.commit()
        return {"status": "created", "device": device}
        
    except IntegrityError as e:
        await session.rollback()
        
        if "device_id" in str(e):
            return {"status": "error", "message": "Device ID already exists"}
        elif "email" in str(e):
            return {"status": "error", "message": "Email already registered"}
        else:
            return {"status": "error", "message": "Data integrity violation"}
            
    except Exception as e:
        await session.rollback()
        return {"status": "error", "message": str(e)}
        
    finally:
        await session.close()
```

## Performance Best Practices

### Connection Pooling

```python
# Configure connection pool in Model class
class Model:
    @classmethod
    def configure(cls, connection_string: str):
        cls._engine = create_async_engine(
            connection_string,
            pool_size=10,        # Keep 10 connections in pool
            max_overflow=20,     # Allow 20 additional connections
            pool_timeout=30,     # Wait 30 seconds for connection
            pool_recycle=3600    # Recreate connections every hour
        )
```

### Batch Operations

```python
async def batch_insert_readings(readings_data: list):
    """Efficiently insert many readings"""
    session = await Model.get_session()
    
    try:
        # Use bulk insert for better performance
        await session.execute(
            insert(SensorReading),
            readings_data
        )
        await session.commit()
        
    finally:
        await session.close()

async def batch_update_devices(updates: list):
    """Efficiently update many devices"""
    session = await Model.get_session()
    
    try:
        await session.execute(
            update(Device),
            updates  # List of {'device_id': ..., 'status': ...} dicts
        )
        await session.commit()
        
    finally:
        await session.close()
```

## Next Steps

- [Migrations](migrations.md) - Learn to manage schema changes
- [Best Practices](best-practices.md) - Optimize performance and organization
- [Controllers](../controllers/README.md) - Use database operations in your handlers
