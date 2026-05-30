# Database Configuration

RouteMQ configures relational database access through SQLAlchemy's async engine. The public database layer supports MySQL and PostgreSQL.

## Supported backends

| `DB_CONNECTION` | SQLAlchemy driver | Default port | Python dependency |
|---|---|---:|---|
| `mysql` | `mysql+aiomysql` | `3306` | `aiomysql` |
| `postgres` or `postgresql` | `postgresql+asyncpg` | `5432` | `asyncpg` |

`SQLAlchemy` and `aiomysql` are base dependencies. PostgreSQL support needs the `postgres` extra or an explicit `asyncpg` dependency:

```bash
uv add "routemq[postgres]"
# or
uv add asyncpg
```

## Enabling and disabling

The legacy flag is still named `ENABLE_MYSQL`, but it gates the backend-neutral SQLAlchemy database layer.

```env
ENABLE_MYSQL=true
```

RouteMQ keeps the old default: if no database env vars are set, it builds an enabled MySQL connection from defaults. Set `ENABLE_MYSQL=false` for apps that don't use relational models.

```env
ENABLE_MYSQL=false
```

An explicit `DATABASE_URL` or `DB_CONNECTION` enables the database path even when `ENABLE_MYSQL=false` is present.

## Configuration precedence

`DATABASE_URL` has the highest precedence. When it is set, RouteMQ ignores the composed `DB_CONNECTION`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and password settings for the connection URL.

RouteMQ normalizes common URL schemes to async SQLAlchemy drivers:

| Input scheme | Runtime scheme |
|---|---|
| `postgres://` | `postgresql+asyncpg://` |
| `postgresql://` | `postgresql+asyncpg://` |
| `mysql://` | `mysql+aiomysql://` |
| `postgresql+asyncpg://` | unchanged |
| `mysql+aiomysql://` | unchanged |

Example:

```env
DATABASE_URL=postgres://mqtt_user:secret@localhost:5432/mqtt_framework
```

RouteMQ uses this at runtime as:

```text
postgresql+asyncpg://mqtt_user:secret@localhost:5432/mqtt_framework
```

## Composed connection settings

When `DATABASE_URL` is not set, RouteMQ builds the SQLAlchemy URL from these settings:

| Variable | Default | Behavior |
|---|---|---|
| `DB_CONNECTION` | `mysql` | Accepts `mysql`, `postgres`, or `postgresql`. Unknown values fall back to `mysql`. |
| `DB_HOST` | `localhost` | Database host. |
| `DB_PORT` | `3306` for MySQL, `5432` for PostgreSQL | Database port. |
| `DB_NAME` | `mqtt_framework` | Database name. |
| `DB_USER` | `root` | Database user. |
| `DB_PASSWORD` | empty string | Preferred password variable. |
| `DB_PASS` | empty string | Legacy fallback used only when `DB_PASSWORD` is absent. |

MySQL example:

```env
ENABLE_MYSQL=true
DB_CONNECTION=mysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=mqtt_user
DB_PASSWORD=mqtt_password
```

PostgreSQL example:

```env
ENABLE_MYSQL=true
DB_CONNECTION=postgres
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mqtt_framework
DB_USER=mqtt_user
DB_PASSWORD=mqtt_password
```

Full URL examples:

```env
# MySQL
DATABASE_URL=mysql://mqtt_user:mqtt_password@localhost:3306/mqtt_framework

# PostgreSQL
DATABASE_URL=postgresql://mqtt_user:mqtt_password@localhost:5432/mqtt_framework
```

## Table creation

RouteMQ does not create or change tables by default. Startup calls SQLAlchemy `create_all()` only when `DB_AUTO_CREATE_TABLES=true` and the database layer is enabled.

```env
DB_AUTO_CREATE_TABLES=true
```

Leave this unset or set it to `false` when you manage schema changes outside RouteMQ.

## Database setup examples

Create the database and user before starting RouteMQ.

MySQL:

```sql
CREATE DATABASE mqtt_framework CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mqtt_user'@'%' IDENTIFIED BY 'mqtt_password';
GRANT ALL PRIVILEGES ON mqtt_framework.* TO 'mqtt_user'@'%';
FLUSH PRIVILEGES;
```

PostgreSQL:

```sql
CREATE USER mqtt_user WITH PASSWORD 'mqtt_password';
CREATE DATABASE mqtt_framework OWNER mqtt_user;
```

## Manual configuration

Applications can configure the model layer directly with an async SQLAlchemy URL:

```python
from routemq.model import Model

Model.configure("postgresql+asyncpg://mqtt_user:mqtt_password@localhost:5432/mqtt_framework")
```

Create tables manually only when that behavior is intentional:

```python
await Model.create_tables()
```

## Connection pool settings

RouteMQ passes pool options to SQLAlchemy when it configures the engine.

| Variable | Default |
|---|---:|
| `DB_POOL_SIZE` | `5` |
| `DB_POOL_MAX_OVERFLOW` | `10` |
| `DB_POOL_TIMEOUT` | `30` |
| `DB_POOL_RECYCLE` | `1800` |
| `DB_POOL_PRE_PING` | `true` |
| `DB_POOL_USE_LIFO` | `false` |
| `DB_POOL_CLASS` | `default` |

Set `DB_POOL_CLASS=null` to use SQLAlchemy `NullPool`. Any other value uses the default pool class.

## SSL and driver options

Pass driver-specific options in `DATABASE_URL` query parameters. RouteMQ preserves query parameters during scheme normalization.

```env
DATABASE_URL=postgresql://mqtt_user:mqtt_password@db.example.com:5432/mqtt_framework?ssl=require
```

## Docker Compose examples

MySQL service:

```yaml
services:
  app:
    build: .
    environment:
      ENABLE_MYSQL: "true"
      DB_CONNECTION: mysql
      DB_HOST: mysql
      DB_PORT: "3306"
      DB_NAME: mqtt_framework
      DB_USER: mqtt_user
      DB_PASSWORD: mqtt_password
    depends_on:
      - mysql

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root_password
      MYSQL_DATABASE: mqtt_framework
      MYSQL_USER: mqtt_user
      MYSQL_PASSWORD: mqtt_password
```

PostgreSQL service:

```yaml
services:
  app:
    build: .
    environment:
      ENABLE_MYSQL: "true"
      DB_CONNECTION: postgres
      DB_HOST: postgres
      DB_PORT: "5432"
      DB_NAME: mqtt_framework
      DB_USER: mqtt_user
      DB_PASSWORD: mqtt_password
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: mqtt_framework
      POSTGRES_USER: mqtt_user
      POSTGRES_PASSWORD: mqtt_password
```

## Troubleshooting

**Missing MySQL driver**

```bash
uv add aiomysql
```

**Missing PostgreSQL driver**

```bash
uv add "routemq[postgres]"
```

**Tables are not created at startup**

Set `DB_AUTO_CREATE_TABLES=true`, or create tables with your own schema workflow.

**Access denied or authentication failed**

Check `DB_USER`, `DB_PASSWORD`, host permissions, and grants for the selected database.

**Unknown database**

Create the database named by `DB_NAME` or by the path segment in `DATABASE_URL`.

## Next steps

- [Creating Models](creating-models.md) - Define your database models
- [Database Operations](operations.md) - Perform CRUD operations
- [Queue Drivers](../queue/drivers.md) - Use the database queue backend
