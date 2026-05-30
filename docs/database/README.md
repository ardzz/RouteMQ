# Database Integration

RouteMQ supports optional relational database storage through SQLAlchemy's async engine. MySQL and PostgreSQL are supported.

## Topics

- [Configuration](configuration.md) - Database setup and connection
- [Creating Models](creating-models.md) - Define database models
- [Database Operations](operations.md) - CRUD operations

## Quick Setup

Configure a relational database in your `.env` file. The enable flag is still named `ENABLE_MYSQL` for compatibility, but it applies to the SQLAlchemy database layer for both MySQL and PostgreSQL.

MySQL:

```env
ENABLE_MYSQL=true
DB_CONNECTION=mysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASSWORD=your_password
```

PostgreSQL:

```env
ENABLE_MYSQL=true
DB_CONNECTION=postgres
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mqtt_framework
DB_USER=postgres
DB_PASSWORD=your_password
```

You can also provide a full connection URL. When `DATABASE_URL` is set, RouteMQ ignores the composed `DB_*` connection settings and normalizes `postgres://`, `postgresql://`, and `mysql://` URLs to async SQLAlchemy drivers.

```env
DATABASE_URL=postgres://postgres:your_password@localhost:5432/mqtt_framework
```

RouteMQ does not create or change tables by default. Set `DB_AUTO_CREATE_TABLES=true` only when you want startup to call SQLAlchemy `create_all()` for registered models.

## Creating Models

Create your models in `app/models/`:

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from routemq.model import Model
import time

class SensorReading(Model):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(50), nullable=False)
    sensor_type = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(10))
    timestamp = Column(Float, nullable=False)
    
    def __repr__(self):
        return f"<SensorReading(sensor_id='{self.sensor_id}', value={self.value})>"

class DeviceStatus(Model):
    __tablename__ = "device_status"
    
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    timestamp = Column(Float, nullable=False)
    metadata = Column(Text)  # JSON string for additional data
```

## Using Models in Controllers

```python
import time

from routemq.controller import Controller
from routemq.model import Model
from app.models.sensor_reading import SensorReading

class SensorController(Controller):
    @staticmethod
    async def handle_temperature(sensor_id, payload, client):
        temperature = payload.get('value')
        unit = payload.get('unit', 'celsius')
        
        reading = await Model.create(
            SensorReading,
            sensor_id=sensor_id,
            sensor_type='temperature',
            value=temperature,
            unit=unit,
            timestamp=time.time()
        )
        
        return {"status": "stored", "id": reading.id}
```

## Database layer

- **Persistent storage**: Data survives application restarts
- **Backend selection**: Choose MySQL or PostgreSQL with `DB_CONNECTION` or `DATABASE_URL`
- **Async sessions**: SQLAlchemy async sessions are configured during application boot
- **Schema control**: Table creation is explicit through `DB_AUTO_CREATE_TABLES=true` or your own migration flow

## Next Steps

- [Configuration](configuration.md) - Set up your database
- [Creating Models](creating-models.md) - Define your data structure
- [Controllers](../controllers/README.md) - Use models in controllers
