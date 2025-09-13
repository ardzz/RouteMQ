# Database Operations

RouteMQ provides built-in database integration using SQLAlchemy for async database operations. This guide shows how to work with database models in your controllers.

## Database Configuration

Database operations are configured through environment variables:

```bash
# Enable MySQL
ENABLE_MYSQL=true

# Database connection
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=your_username
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=routemq
```

## Model Structure

### Base Model

All models extend the base `Model` class:

```python
from core.model import Model, Base
from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.sql import func

class DeviceModel(Base, Model):
    __tablename__ = 'devices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default='offline')
    last_seen = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

### Creating Models

Create model files in the `app/models/` directory:

```python
# app/models/device_model.py
from core.model import Model, Base
from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from sqlalchemy.sql import func
import json

class DeviceModel(Base, Model):
    __tablename__ = 'devices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    device_type = Column(String(100), nullable=False)
    status = Column(String(50), default='offline')
    configuration = Column(Text)  # JSON configuration
    last_seen = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def set_config(self, config_dict):
        """Set configuration as JSON string"""
        self.configuration = json.dumps(config_dict)
    
    def get_config(self):
        """Get configuration as dictionary"""
        if self.configuration:
            return json.loads(self.configuration)
        return {}

class SensorDataModel(Base, Model):
    __tablename__ = 'sensor_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), nullable=False, index=True)
    sensor_type = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(50))
    timestamp = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
```

## Database Operations in Controllers

### Basic CRUD Operations

```python
from core.controller import Controller
from app.models.device_model import DeviceModel
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
import json

class DeviceController(Controller):
    @staticmethod
    async def handle_device_registration(device_id: str, payload, client):
        """Register a new device"""
        session = await DeviceModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            # Check if device already exists
            stmt = select(DeviceModel).where(DeviceModel.device_id == device_id)
            result = await session.execute(stmt)
            existing_device = result.scalar_one_or_none()
            
            if existing_device:
                return {"error": "Device already registered"}
            
            # Create new device
            new_device = DeviceModel(
                device_id=device_id,
                name=payload.get('name', device_id),
                device_type=payload.get('type', 'unknown'),
                status='online'
            )
            
            # Set configuration if provided
            if 'config' in payload:
                new_device.set_config(payload['config'])
            
            session.add(new_device)
            await session.commit()
            
            # Send confirmation
            response_topic = f"devices/{device_id}/registration/response"
            client.publish(response_topic, json.dumps({
                "status": "registered",
                "device_id": device_id
            }))
            
            return {"registered": True, "device_id": device_id}
            
        except IntegrityError:
            await session.rollback()
            return {"error": "Device ID already exists"}
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Database error: {e}")
            return {"error": "Database operation failed"}
        finally:
            await session.close()
    
    @staticmethod
    async def handle_device_status_update(device_id: str, payload, client):
        """Update device status"""
        session = await DeviceModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            # Find device
            stmt = select(DeviceModel).where(DeviceModel.device_id == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()
            
            if not device:
                return {"error": "Device not found"}
            
            # Update status
            device.status = payload.get('status', device.status)
            device.last_seen = func.now()
            
            await session.commit()
            
            return {"updated": True, "status": device.status}
            
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Database error: {e}")
            return {"error": "Database operation failed"}
        finally:
            await session.close()
```

### Sensor Data Storage

```python
from core.controller import Controller
from app.models.device_model import SensorDataModel
from sqlalchemy.future import select
from sqlalchemy import desc
import time

class SensorController(Controller):
    @staticmethod
    async def handle_sensor_data(device_id: str, sensor_type: str, payload, client):
        """Store sensor data"""
        session = await SensorDataModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            # Create sensor data record
            sensor_data = SensorDataModel(
                device_id=device_id,
                sensor_type=sensor_type,
                value=payload.get('value'),
                unit=payload.get('unit', ''),
                timestamp=payload.get('timestamp', func.now())
            )
            
            session.add(sensor_data)
            await session.commit()
            
            # Get recent readings for analysis
            recent_data = await SensorController.get_recent_readings(
                device_id, sensor_type, limit=10
            )
            
            # Publish processed data
            analysis_topic = f"devices/{device_id}/sensors/{sensor_type}/analysis"
            client.publish(analysis_topic, json.dumps({
                "latest_value": payload.get('value'),
                "recent_count": len(recent_data),
                "stored_at": time.time()
            }))
            
            return {"stored": True, "id": sensor_data.id}
            
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Database error: {e}")
            return {"error": "Failed to store sensor data"}
        finally:
            await session.close()
    
    @staticmethod
    async def get_recent_readings(device_id: str, sensor_type: str, limit: int = 10):
        """Get recent sensor readings"""
        session = await SensorDataModel.get_session()
        if not session:
            return []
        
        try:
            stmt = select(SensorDataModel).where(
                SensorDataModel.device_id == device_id,
                SensorDataModel.sensor_type == sensor_type
            ).order_by(desc(SensorDataModel.timestamp)).limit(limit)
            
            result = await session.execute(stmt)
            readings = result.scalars().all()
            
            return [
                {
                    "value": reading.value,
                    "unit": reading.unit,
                    "timestamp": reading.timestamp.isoformat()
                }
                for reading in readings
            ]
            
        except Exception as e:
            self.logger.error(f"Database query error: {e}")
            return []
        finally:
            await session.close()
```

### Complex Queries and Aggregations

```python
from core.controller import Controller
from app.models.device_model import DeviceModel, SensorDataModel
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta

class AnalyticsController(Controller):
    @staticmethod
    async def handle_device_analytics(device_id: str, payload, client):
        """Generate device analytics"""
        session = await DeviceModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            # Get device info
            device_stmt = select(DeviceModel).where(DeviceModel.device_id == device_id)
            device_result = await session.execute(device_stmt)
            device = device_result.scalar_one_or_none()
            
            if not device:
                return {"error": "Device not found"}
            
            # Calculate analytics for the last 24 hours
            since = datetime.now() - timedelta(hours=24)
            
            # Count readings by sensor type
            readings_stmt = select(
                SensorDataModel.sensor_type,
                func.count(SensorDataModel.id).label('count'),
                func.avg(SensorDataModel.value).label('avg_value'),
                func.min(SensorDataModel.value).label('min_value'),
                func.max(SensorDataModel.value).label('max_value')
            ).where(
                and_(
                    SensorDataModel.device_id == device_id,
                    SensorDataModel.timestamp >= since
                )
            ).group_by(SensorDataModel.sensor_type)
            
            readings_result = await session.execute(readings_stmt)
            sensor_stats = readings_result.all()
            
            analytics = {
                "device_id": device_id,
                "device_name": device.name,
                "status": device.status,
                "last_seen": device.last_seen.isoformat(),
                "period": "24_hours",
                "sensor_statistics": [
                    {
                        "sensor_type": stat.sensor_type,
                        "reading_count": stat.count,
                        "average_value": float(stat.avg_value) if stat.avg_value else 0,
                        "min_value": float(stat.min_value) if stat.min_value else 0,
                        "max_value": float(stat.max_value) if stat.max_value else 0
                    }
                    for stat in sensor_stats
                ]
            }
            
            # Publish analytics
            analytics_topic = f"devices/{device_id}/analytics"
            client.publish(analytics_topic, json.dumps(analytics))
            
            return analytics
            
        except Exception as e:
            self.logger.error(f"Analytics query error: {e}")
            return {"error": "Failed to generate analytics"}
        finally:
            await session.close()
    
    @staticmethod
    async def handle_system_summary(payload, client):
        """Generate system-wide summary"""
        session = await DeviceModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            # Device counts by status
            device_stats_stmt = select(
                DeviceModel.status,
                func.count(DeviceModel.id).label('count')
            ).group_by(DeviceModel.status)
            
            device_stats_result = await session.execute(device_stats_stmt)
            device_stats = device_stats_result.all()
            
            # Recent activity (last hour)
            since = datetime.now() - timedelta(hours=1)
            recent_readings_stmt = select(
                func.count(SensorDataModel.id).label('recent_readings')
            ).where(SensorDataModel.timestamp >= since)
            
            recent_result = await session.execute(recent_readings_stmt)
            recent_readings = recent_result.scalar()
            
            summary = {
                "timestamp": datetime.now().isoformat(),
                "device_counts": {
                    stat.status: stat.count for stat in device_stats
                },
                "recent_activity": {
                    "readings_last_hour": recent_readings
                }
            }
            
            # Publish summary
            client.publish("system/summary", json.dumps(summary))
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Summary query error: {e}")
            return {"error": "Failed to generate summary"}
        finally:
            await session.close()
```

### Batch Operations

```python
from core.controller import Controller
from app.models.device_model import SensorDataModel
from sqlalchemy.dialects.mysql import insert

class BatchController(Controller):
    @staticmethod
    async def handle_batch_sensor_data(device_id: str, payload, client):
        """Handle batch sensor data insertion"""
        session = await SensorDataModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            readings = payload.get('readings', [])
            if not readings:
                return {"error": "No readings provided"}
            
            # Prepare batch data
            sensor_records = []
            for reading in readings:
                sensor_records.append({
                    'device_id': device_id,
                    'sensor_type': reading.get('sensor_type'),
                    'value': reading.get('value'),
                    'unit': reading.get('unit', ''),
                    'timestamp': reading.get('timestamp', func.now())
                })
            
            # Bulk insert
            if sensor_records:
                stmt = insert(SensorDataModel.__table__).values(sensor_records)
                await session.execute(stmt)
                await session.commit()
            
            response = {
                "batch_processed": True,
                "records_inserted": len(sensor_records),
                "device_id": device_id
            }
            
            # Publish batch completion
            batch_topic = f"devices/{device_id}/batch/complete"
            client.publish(batch_topic, json.dumps(response))
            
            return response
            
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Batch insert error: {e}")
            return {"error": "Batch operation failed"}
        finally:
            await session.close()
```

### Transaction Management

```python
from core.controller import Controller
from app.models.device_model import DeviceModel, SensorDataModel
from sqlalchemy.future import select

class TransactionController(Controller):
    @staticmethod
    async def handle_device_update_with_data(device_id: str, payload, client):
        """Update device and add sensor data in a single transaction"""
        session = await DeviceModel.get_session()
        if not session:
            return {"error": "Database not available"}
        
        try:
            # Start transaction
            async with session.begin():
                # Update device status
                device_stmt = select(DeviceModel).where(DeviceModel.device_id == device_id)
                device_result = await session.execute(device_stmt)
                device = device_result.scalar_one_or_none()
                
                if not device:
                    raise ValueError("Device not found")
                
                # Update device
                device.status = payload.get('status', device.status)
                device.last_seen = func.now()
                
                # Add sensor readings
                sensor_readings = payload.get('sensor_data', [])
                for reading in sensor_readings:
                    sensor_data = SensorDataModel(
                        device_id=device_id,
                        sensor_type=reading.get('sensor_type'),
                        value=reading.get('value'),
                        unit=reading.get('unit', '')
                    )
                    session.add(sensor_data)
                
                # Transaction commits automatically when exiting the block
            
            return {
                "updated": True,
                "device_status": device.status,
                "sensor_readings_added": len(sensor_readings)
            }
            
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            self.logger.error(f"Transaction error: {e}")
            return {"error": "Transaction failed"}
        finally:
            await session.close()
```

## Database Best Practices

### 1. Always Use Session Management

```python
# Good: Proper session management
session = await Model.get_session()
if not session:
    return {"error": "Database not available"}

try:
    # Database operations
    pass
except Exception as e:
    await session.rollback()
    return {"error": "Operation failed"}
finally:
    await session.close()
```

### 2. Handle Database Unavailability

```python
@staticmethod
async def handle_with_fallback(device_id: str, payload, client):
    """Handle operations with database fallback"""
    session = await DeviceModel.get_session()
    
    if not session:
        # Database not available - use alternative storage
        from core.redis_manager import redis_manager
        
        if redis_manager.is_enabled():
            # Fallback to Redis
            await redis_manager.set_json(f"fallback:{device_id}", payload)
            return {"stored_in_cache": True}
        
        # No storage available
        return {"error": "No storage available"}
    
    # Normal database flow
    try:
        # Database operations...
        pass
    finally:
        await session.close()
```

### 3. Use Indexes for Performance

```python
# Add indexes to frequently queried columns
class DeviceModel(Base, Model):
    __tablename__ = 'devices'
    
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(String(50), default='offline', index=True)
    last_seen = Column(DateTime, default=func.now(), index=True)
```

### 4. Validate Data Before Database Operations

```python
@staticmethod
async def handle_validated_insert(device_id: str, payload, client):
    """Insert with validation"""
    # Validate data first
    if not device_id or len(device_id) > 255:
        return {"error": "Invalid device_id"}
    
    value = payload.get('value')
    if not isinstance(value, (int, float)):
        return {"error": "Value must be numeric"}
    
    # Proceed with database operation
    session = await SensorDataModel.get_session()
    # ... rest of the operation
```

## Migration and Schema Management

For production deployments, consider using Alembic for database migrations:

```python
# Initialize migrations
# alembic init migrations

# Create migration
# alembic revision --autogenerate -m "Add device table"

# Apply migrations
# alembic upgrade head
```

## Next Steps

- [Best Practices](best-practices.md) - Follow controller organization guidelines
- [Creating Controllers](creating-controllers.md) - Review controller basics
