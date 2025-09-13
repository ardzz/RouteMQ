# Database Configuration

RouteMQ supports MySQL integration for persistent data storage using SQLAlchemy with async support.

## Environment Setup

Configure your database connection in the `.env` file:

```env
# Enable/disable database integration
ENABLE_MYSQL=true

# Database connection settings
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=your_password
```

## Database Dependencies

The framework uses these database-related packages:

- **SQLAlchemy 2.0+**: Modern async ORM
- **aiomysql**: Async MySQL driver
- **python-dotenv**: Environment variable management

These are included in `requirements.txt`:

```txt
SQLAlchemy==2.0.23
aiomysql==0.2.0
python-dotenv==1.0.0
```

## Connection Configuration

### Automatic Configuration

The framework automatically configures the database connection on startup:

```python
# bootstrap/app.py
def _setup_database(self):
    """Configure database connection from environment variables"""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "mqtt_framework")
    db_user = os.getenv("DB_USER", "root")
    db_pass = os.getenv("DB_PASS", "")
    
    # Build connection string for MySQL with async support
    conn_str = f"mysql+aiomysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    Model.configure(conn_str)
```

### Manual Configuration

You can also configure the database manually:

```python
from core.model import Model

# Configure with custom connection string
Model.configure("mysql+aiomysql://user:pass@localhost:3306/mydb")

# Create tables
await Model.create_tables()
```

## Connection String Format

The connection string follows SQLAlchemy's format for async MySQL:

```
mysql+aiomysql://username:password@host:port/database_name
```

### Connection String Examples

```python
# Local development
"mysql+aiomysql://root:password@localhost:3306/mqtt_dev"

# Production with remote database
"mysql+aiomysql://app_user:secure_pass@db.example.com:3306/mqtt_prod"

# With special characters in password (URL encoded)
"mysql+aiomysql://user:p%40ssw0rd@localhost:3306/mqtt_db"

# Custom port
"mysql+aiomysql://user:pass@localhost:3307/mqtt_db"
```

## Database Setup

### Creating the Database

Before running your application, create the database:

```sql
-- Connect to MySQL as admin user
CREATE DATABASE mqtt_framework CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create application user (recommended for production)
CREATE USER 'mqtt_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON mqtt_framework.* TO 'mqtt_user'@'localhost';
FLUSH PRIVILEGES;
```

### Table Creation

The framework automatically creates tables when the application starts:

```python
# Application initialization
app = Application()
await app.initialize_database()  # Creates all tables defined in models
```

## Configuration Options

### Development Settings

```env
# Development configuration
ENABLE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_dev
DB_USER=root
DB_PASS=dev_password
```

### Production Settings

```env
# Production configuration
ENABLE_MYSQL=true
DB_HOST=prod-db.example.com
DB_PORT=3306
DB_NAME=mqtt_production
DB_USER=mqtt_app
DB_PASS=complex_secure_password
```

### Docker Configuration

```env
# Docker Compose configuration
ENABLE_MYSQL=true
DB_HOST=mysql
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=mqtt_user
DB_PASS=mqtt_password
```

## Connection Pool Settings

SQLAlchemy's async engine provides connection pooling by default. You can customize pool settings:

```python
from sqlalchemy.ext.asyncio import create_async_engine

class Model:
    @classmethod
    def configure(cls, connection_string: str, **engine_kwargs):
        """Configure with custom engine options"""
        cls._engine = create_async_engine(
            connection_string,
            pool_size=10,          # Number of connections to maintain
            max_overflow=20,       # Additional connections when pool is full
            pool_timeout=30,       # Seconds to wait for connection
            pool_recycle=3600,     # Seconds before recreating connection
            echo=False,            # Set to True for SQL query logging
            **engine_kwargs
        )
```

## SSL Configuration

For secure connections, configure SSL in the connection string:

```python
# SSL connection string
conn_str = "mysql+aiomysql://user:pass@host:port/db?ssl_ca=/path/to/ca.pem&ssl_cert=/path/to/cert.pem&ssl_key=/path/to/key.pem"

# Or with SSL verification disabled (not recommended for production)
conn_str = "mysql+aiomysql://user:pass@host:port/db?ssl_disabled=true"
```

## Disabling Database Integration

To run without database support:

```env
ENABLE_MYSQL=false
```

When disabled:
- Database operations return `None` or empty results
- No database connections are created
- Models can still be defined but won't persist data
- Warnings are logged when database operations are attempted

## Troubleshooting

### Common Connection Issues

**Error: `aiomysql` not installed**
```bash
pip install aiomysql
```

**Error: Access denied for user**
```sql
-- Check user permissions
SHOW GRANTS FOR 'your_user'@'localhost';

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON your_database.* TO 'your_user'@'localhost';
```

**Error: Unknown database**
```sql
-- Create the database
CREATE DATABASE your_database_name;
```

**Error: Connection timeout**
- Check if MySQL server is running
- Verify host and port settings
- Check firewall settings

### Debug Connection Issues

Enable SQL query logging:

```python
Model.configure(connection_string, echo=True)
```

Check connection in logs:

```python
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### Testing Database Connection

```python
async def test_connection():
    """Test database connection"""
    try:
        session = await Model.get_session()
        if session:
            print("Database connection successful")
            await session.close()
        else:
            print("Database is disabled")
    except Exception as e:
        print(f"Database connection failed: {e}")

# Run the test
import asyncio
asyncio.run(test_connection())
```

## Configuration Best Practices

### Security

1. **Use environment variables** for sensitive data
2. **Create dedicated database users** with minimal privileges
3. **Use SSL connections** in production
4. **Regularly rotate passwords**

### Performance

1. **Configure appropriate pool sizes** based on expected load
2. **Use connection recycling** to prevent stale connections
3. **Monitor connection usage** in production
4. **Consider read replicas** for high-read workloads

### Development

1. **Use separate databases** for development, testing, and production
2. **Keep connection strings** in version-controlled `.env.example` files
3. **Document required database setup** for new developers

## Docker Setup

### Docker Compose Example

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    environment:
      - ENABLE_MYSQL=true
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=mqtt_framework
      - DB_USER=mqtt_user
      - DB_PASS=mqtt_password
    depends_on:
      - mysql

  mysql:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=root_password
      - MYSQL_DATABASE=mqtt_framework
      - MYSQL_USER=mqtt_user
      - MYSQL_PASSWORD=mqtt_password
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

volumes:
  mysql_data:
```

### Initialization Script

```sql
-- init.sql (mounted to /docker-entrypoint-initdb.d/)
CREATE DATABASE IF NOT EXISTS mqtt_framework CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'mqtt_user'@'%' IDENTIFIED BY 'mqtt_password';
GRANT ALL PRIVILEGES ON mqtt_framework.* TO 'mqtt_user'@'%';
FLUSH PRIVILEGES;
```

## Next Steps

- [Creating Models](creating-models.md) - Define your database models
- [Database Operations](operations.md) - Perform CRUD operations
- [Migrations](migrations.md) - Manage schema changes
- [Best Practices](best-practices.md) - Optimize performance and organization
