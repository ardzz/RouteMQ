# Database Integration

RouteMQ supports optional MySQL integration for persistent data storage.

## Topics

- [Configuration](configuration.md) - Database setup and connection
- [Creating Models](creating-models.md) - Define database models
- [Database Operations](operations.md) - CRUD operations
- [Migrations](migrations.md) - Database schema management
- [Best Practices](best-practices.md) - Performance and organization tips

## Quick Setup

Enable database support in your `.env` file:

```env
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password
```

## Creating Models

Create your models in `app/models/`:

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from core.model import Base
import time

class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(50), nullable=False)
    sensor_type = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(10))
    timestamp = Column(Float, nullable=False)
    
    def __repr__(self):
        return f"<SensorReading(sensor_id='{self.sensor_id}', value={self.value})>"

class DeviceStatus(Base):
    __tablename__ = "device_status"
    
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    timestamp = Column(Float, nullable=False)
    metadata = Column(Text)  # JSON string for additional data
```

## Using Models in Controllers

```python
from core.controller import Controller
from app.models.sensor_reading import SensorReading

class SensorController(Controller):
    @staticmethod
    async def handle_temperature(sensor_id, payload, client):
        temperature = payload.get('value')
        unit = payload.get('unit', 'celsius')
        
        # Store in database
        reading = SensorReading(
            sensor_id=sensor_id,
            sensor_type='temperature',
            value=temperature,
            unit=unit,
            timestamp=time.time()
        )
        await reading.save()
        
        return {"status": "stored", "id": reading.id}
```

## Benefits

- **Persistent Storage**: Data survives application restarts
- **Complex Queries**: SQL support for advanced data retrieval
- **Relationships**: Define relationships between entities
- **Transactions**: ACID compliance for data integrity

## Next Steps

- [Configuration](configuration.md) - Set up your database
- [Creating Models](creating-models.md) - Define your data structure
- [Controllers](../controllers/README.md) - Use models in controllers
