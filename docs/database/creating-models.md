# Creating Models

Models in RouteMQ define your database structure using SQLAlchemy's declarative syntax with async support.

## Model Basics

### Base Model Class

All models inherit from the SQLAlchemy `Base` class:

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from core.model import Base
import time

class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(String(50), nullable=False, index=True)
    sensor_type = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(10))
    timestamp = Column(Float, nullable=False, default=time.time)
    
    def __repr__(self):
        return f"<SensorReading(sensor_id='{self.sensor_id}', value={self.value})>"
```

### Model Directory Structure

Organize models in the `app/models/` directory:

```
app/models/
├── __init__.py
├── sensor_reading.py      # SensorReading model
├── device_status.py       # DeviceStatus model
├── user.py               # User model
└── alert.py              # Alert model
```

## Column Types

### Common Column Types

```python
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, 
    DateTime, Text, JSON, DECIMAL, TIMESTAMP
)

class ExampleModel(Base):
    __tablename__ = "examples"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # String fields
    name = Column(String(100), nullable=False)          # VARCHAR(100)
    description = Column(Text)                          # TEXT
    code = Column(String(10), unique=True)              # Unique constraint
    
    # Numeric fields
    value = Column(Float)                               # FLOAT
    price = Column(DECIMAL(10, 2))                      # DECIMAL(10,2)
    count = Column(Integer, default=0)                  # INT with default
    
    # Boolean field
    is_active = Column(Boolean, default=True)           # BOOLEAN
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # JSON field (MySQL 5.7+)
    metadata = Column(JSON)
    
    # Custom timestamp (Unix timestamp)
    timestamp = Column(Float, default=time.time)
```

### String Lengths

Choose appropriate string lengths for your use case:

```python
class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50))      # Device identifiers
    name = Column(String(100))          # Human-readable names
    description = Column(String(255))   # Short descriptions
    notes = Column(Text)                # Long text content
    mac_address = Column(String(17))    # Fixed format (XX:XX:XX:XX:XX:XX)
    ip_address = Column(String(45))     # IPv4 (15) or IPv6 (45)
```

## Indexes and Constraints

### Database Indexes

Add indexes for frequently queried columns:

```python
class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(50), nullable=False, index=True)  # Single index
    timestamp = Column(Float, nullable=False, index=True)       # Time-based queries
    value = Column(Float, nullable=False)
    
    # Composite index for common query patterns
    __table_args__ = (
        Index('idx_sensor_timestamp', 'sensor_id', 'timestamp'),
        Index('idx_timestamp_value', 'timestamp', 'value'),
    )
```

### Unique Constraints

```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)  # Unique username
    email = Column(String(100), unique=True, nullable=False)    # Unique email
    device_id = Column(String(50))
    
    # Composite unique constraint
    __table_args__ = (
        UniqueConstraint('device_id', 'username', name='uq_device_user'),
    )
```

### Check Constraints

```python
class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    temperature = Column(Float)
    humidity = Column(Float)
    
    # Ensure valid ranges
    __table_args__ = (
        CheckConstraint('temperature >= -50 AND temperature <= 150', name='check_temp_range'),
        CheckConstraint('humidity >= 0 AND humidity <= 100', name='check_humidity_range'),
    )
```

## Relationships

### Foreign Keys

```python
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    
    # Relationship to User
    user = relationship("User", back_populates="devices")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True)
    
    # Relationship to Device
    devices = relationship("Device", back_populates="user")
```

### One-to-Many Relationships

```python
class Sensor(Base):
    __tablename__ = "sensors"
    
    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(50), unique=True)
    device_id = Column(Integer, ForeignKey('devices.id'))
    
    # Back reference to device
    device = relationship("Device", back_populates="sensors")
    
    # Forward reference to readings
    readings = relationship("SensorReading", back_populates="sensor", cascade="all, delete-orphan")

class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    sensor_id = Column(Integer, ForeignKey('sensors.id'))
    value = Column(Float)
    timestamp = Column(Float)
    
    # Back reference to sensor
    sensor = relationship("Sensor", back_populates="readings")
```

### Many-to-Many Relationships

```python
# Association table
device_user_association = Table(
    'device_user_association',
    Base.metadata,
    Column('device_id', Integer, ForeignKey('devices.id')),
    Column('user_id', Integer, ForeignKey('users.id'))
)

class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    
    # Many-to-many with users
    users = relationship("User", secondary=device_user_association, back_populates="devices")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50))
    
    # Many-to-many with devices
    devices = relationship("Device", secondary=device_user_association, back_populates="users")
```

## Model Methods

### Instance Methods

Add custom methods to your models:

```python
class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(50))
    temperature = Column(Float)
    humidity = Column(Float)
    timestamp = Column(Float, default=time.time)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'sensor_id': self.sensor_id,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'timestamp': self.timestamp
        }
    
    def is_recent(self, minutes=60):
        """Check if reading is within the last N minutes"""
        return time.time() - self.timestamp < (minutes * 60)
    
    def fahrenheit_temperature(self):
        """Convert temperature to Fahrenheit"""
        if self.temperature is not None:
            return (self.temperature * 9/5) + 32
        return None
    
    @property
    def age_seconds(self):
        """Get age of reading in seconds"""
        return time.time() - self.timestamp
```

### Class Methods

Add class-level query methods:

```python
class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    # ... columns ...
    
    @classmethod
    async def get_latest_by_sensor(cls, sensor_id: str):
        """Get the most recent reading for a sensor"""
        from core.model import Model
        session = await Model.get_session()
        
        result = await session.execute(
            select(cls)
            .where(cls.sensor_id == sensor_id)
            .order_by(cls.timestamp.desc())
            .limit(1)
        )
        return result.scalars().first()
    
    @classmethod
    async def get_readings_in_range(cls, sensor_id: str, start_time: float, end_time: float):
        """Get readings within a time range"""
        from core.model import Model
        session = await Model.get_session()
        
        result = await session.execute(
            select(cls)
            .where(
                cls.sensor_id == sensor_id,
                cls.timestamp >= start_time,
                cls.timestamp <= end_time
            )
            .order_by(cls.timestamp)
        )
        return result.scalars().all()
```

## Model Examples

### IoT Device Model

```python
class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    device_type = Column(String(30), nullable=False)  # 'sensor', 'actuator', 'gateway'
    manufacturer = Column(String(50))
    model = Column(String(50))
    firmware_version = Column(String(20))
    
    # Status tracking
    status = Column(String(20), default='offline')  # 'online', 'offline', 'maintenance'
    last_seen = Column(Float)
    
    # Location and grouping
    location = Column(String(100))
    group_name = Column(String(50))
    tags = Column(JSON)  # Array of tags
    
    # Configuration
    config = Column(JSON)  # Device-specific configuration
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Device(device_id='{self.device_id}', status='{self.status}')>"
    
    def is_online(self, timeout_minutes=5):
        """Check if device is considered online"""
        if not self.last_seen:
            return False
        return time.time() - self.last_seen < (timeout_minutes * 60)
    
    def update_last_seen(self):
        """Update the last seen timestamp"""
        self.last_seen = time.time()
```

### Alert Model

```python
class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True)
    alert_id = Column(String(50), unique=True, default=lambda: str(uuid.uuid4()))
    
    # Alert details
    title = Column(String(200), nullable=False)
    message = Column(Text)
    severity = Column(String(20), nullable=False)  # 'low', 'medium', 'high', 'critical'
    category = Column(String(50))  # 'temperature', 'connectivity', 'battery', etc.
    
    # Source information
    device_id = Column(String(50), index=True)
    sensor_id = Column(String(50))
    source_topic = Column(String(255))
    
    # Alert state
    status = Column(String(20), default='active')  # 'active', 'acknowledged', 'resolved'
    acknowledged_by = Column(String(50))
    acknowledged_at = Column(Float)
    resolved_at = Column(Float)
    
    # Timestamps
    created_at = Column(Float, default=time.time, index=True)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    
    # Alert data
    alert_data = Column(JSON)  # Original data that triggered alert
    
    def __repr__(self):
        return f"<Alert(severity='{self.severity}', status='{self.status}')>"
    
    def acknowledge(self, user_id: str):
        """Acknowledge the alert"""
        self.status = 'acknowledged'
        self.acknowledged_by = user_id
        self.acknowledged_at = time.time()
    
    def resolve(self):
        """Mark alert as resolved"""
        self.status = 'resolved'
        self.resolved_at = time.time()
```

### User Session Model

```python
class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    
    # Session data
    user_agent = Column(String(255))
    ip_address = Column(String(45))
    login_method = Column(String(20))  # 'password', 'token', 'api_key'
    
    # Session state
    is_active = Column(Boolean, default=True)
    last_activity = Column(Float, default=time.time)
    
    # Timestamps
    created_at = Column(Float, default=time.time)
    expires_at = Column(Float)
    
    def __repr__(self):
        return f"<UserSession(user_id='{self.user_id}', active={self.is_active})>"
    
    def is_expired(self):
        """Check if session has expired"""
        return self.expires_at and time.time() > self.expires_at
    
    def extend_session(self, hours=24):
        """Extend session expiry"""
        self.expires_at = time.time() + (hours * 3600)
        self.last_activity = time.time()
```

## Model Registration

### Importing Models

Models must be imported to be registered with SQLAlchemy:

```python
# app/models/__init__.py
from .sensor_reading import SensorReading
from .device import Device
from .alert import Alert
from .user_session import UserSession

# Export all models
__all__ = [
    'SensorReading',
    'Device', 
    'Alert',
    'UserSession'
]
```

### Auto-discovery (Optional)

Create a model registry for automatic discovery:

```python
# app/models/__init__.py
import importlib
import pkgutil
from pathlib import Path

# Get the current directory
models_dir = Path(__file__).parent

# Import all model modules
for finder, name, ispkg in pkgutil.iter_modules([str(models_dir)]):
    if not name.startswith('_') and not ispkg:
        importlib.import_module(f'app.models.{name}')
```

## Validation

### SQLAlchemy Validators

```python
from sqlalchemy.orm import validates

class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), nullable=False)
    status = Column(String(20), default='offline')
    
    @validates('status')
    def validate_status(self, key, status):
        """Validate device status values"""
        valid_statuses = ['online', 'offline', 'maintenance', 'error']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")
        return status
    
    @validates('device_id')
    def validate_device_id(self, key, device_id):
        """Validate device ID format"""
        if not device_id or len(device_id) < 3:
            raise ValueError("Device ID must be at least 3 characters")
        return device_id
```

### Custom Validation Methods

```python
class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id = Column(Integer, primary_key=True)
    temperature = Column(Float)
    humidity = Column(Float)
    
    def validate(self):
        """Custom validation method"""
        errors = []
        
        if self.temperature is not None:
            if self.temperature < -50 or self.temperature > 150:
                errors.append("Temperature must be between -50 and 150")
        
        if self.humidity is not None:
            if self.humidity < 0 or self.humidity > 100:
                errors.append("Humidity must be between 0 and 100")
        
        if errors:
            raise ValueError("; ".join(errors))
        
        return True
```

## Best Practices

### Naming Conventions

1. **Table names**: Use snake_case plural nouns (`sensor_readings`, `device_statuses`)
2. **Column names**: Use snake_case (`device_id`, `created_at`)
3. **Model classes**: Use PascalCase singular nouns (`SensorReading`, `DeviceStatus`)

### Performance Tips

1. **Add indexes** on frequently queried columns
2. **Use appropriate column types** and sizes
3. **Define relationships** carefully to avoid N+1 queries
4. **Use lazy loading** for large datasets

### Organization Tips

1. **One model per file** for better maintainability
2. **Group related models** in the same module if small
3. **Use consistent patterns** across all models
4. **Document complex relationships** and constraints

## Next Steps

- [Database Operations](operations.md) - Learn CRUD operations with your models
- [Migrations](migrations.md) - Manage schema changes as your models evolve
- [Best Practices](best-practices.md) - Optimize performance and organization
