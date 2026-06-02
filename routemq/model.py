import logging
from typing import Any, Optional, cast

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import declarative_base, sessionmaker

from .observability import start_span

Base = declarative_base()
logger = logging.getLogger('RouteMQ.Model')


class Model(Base):
    """Base model class that all models should extend."""

    __abstract__ = True

    # This will be set by the application bootstrap
    _engine: Any = None
    _session_factory: Any = None
    _is_enabled = False
    _db_system = 'mysql'
    _server_address: str | None = None
    _server_port: int | None = None

    @classmethod
    def configure(
        cls,
        connection_string: str,
        *,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
        pool_pre_ping: bool = True,
        pool_use_lifo: bool = False,
        pool_class: str = 'default',
    ) -> None:
        """Configure the database connection."""
        engine_kwargs: dict[str, object] = {
            'pool_size': pool_size,
            'max_overflow': max_overflow,
            'pool_timeout': pool_timeout,
            'pool_recycle': pool_recycle,
            'pool_pre_ping': pool_pre_ping,
            'pool_use_lifo': pool_use_lifo,
        }
        if pool_class == 'null':
            from sqlalchemy.pool import NullPool

            engine_kwargs.pop('pool_size')
            engine_kwargs.pop('max_overflow')
            engine_kwargs['poolclass'] = NullPool

        cls._engine = create_async_engine(connection_string, **engine_kwargs)
        cls._session_factory = sessionmaker(cls._engine, expire_on_commit=False, class_=AsyncSession)
        cls._is_enabled = True
        cls._set_connection_observability(connection_string)
        logger.info('Database connection configured')

    @classmethod
    async def cleanup(cls):
        """Cleanup database connections and close the engine."""
        if cls._engine is not None:
            await cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None
            cls._is_enabled = False
            cls._server_address = None
            cls._server_port = None
            logger.info('Database connections closed')

    @classmethod
    async def get_session(cls) -> Optional[AsyncSession]:
        """Get a new session for database operations."""
        if not cls._is_enabled:
            logger.warning('Database operations attempted while database integration is disabled')
            return None

        if cls._session_factory is None:
            raise RuntimeError('Database not configured. Call Model.configure() first.')
        return cast(AsyncSession, cls._session_factory())

    @classmethod
    async def create_tables(cls):
        """Create all tables defined in models."""
        if not cls._is_enabled:
            logger.info('Skipping table creation as database integration is disabled')
            return

        engine = cls._engine
        attrs = _db_span_attributes('create', None, 'CREATE TABLE <metadata>')
        with start_span(_db_span_name('create', None), attrs, kind='client'):
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                logger.info('Database tables created')

    @classmethod
    async def find(cls, model_class, id_value):
        """Find a record by ID."""
        if not cls._is_enabled:
            logger.warning(f'Find operation on {model_class.__name__} skipped - database integration disabled')
            return None

        session = await cls.get_session()
        if session is None:
            return None

        table_name = _model_table_name(model_class)
        attrs = _db_span_attributes('select', table_name, _select_by_id_query(table_name))
        with start_span(_db_span_name('select', table_name), attrs, kind='client'):
            async with session:
                result = await session.execute(select(model_class).where(model_class.id == id_value))
                return result.scalars().first()

    @classmethod
    async def all(cls, model_class):
        """Get all records of a model."""
        if not cls._is_enabled:
            logger.warning(f'All records query on {model_class.__name__} skipped - database integration disabled')
            return []

        session = await cls.get_session()
        if session is None:
            return []

        table_name = _model_table_name(model_class)
        attrs = _db_span_attributes('select', table_name, _select_all_query(table_name))
        with start_span(_db_span_name('select', table_name), attrs, kind='client'):
            async with session:
                result = await session.execute(select(model_class))
                return result.scalars().all()

    @classmethod
    async def create(cls, model_class, **kwargs):
        """Create a new record."""
        if not cls._is_enabled:
            logger.warning(f'Create operation on {model_class.__name__} skipped - database integration disabled')
            return None

        session = await cls.get_session()
        if session is None:
            return None

        table_name = _model_table_name(model_class)
        attrs = _db_span_attributes('insert', table_name, _insert_query(table_name))
        with start_span(_db_span_name('insert', table_name), attrs, kind='client'):
            async with session:
                obj = model_class(**kwargs)
                session.add(obj)
                await session.commit()
                await session.refresh(obj)
                return obj

    @classmethod
    def _set_connection_observability(cls, connection_string: str) -> None:
        try:
            url = make_url(connection_string)
        except Exception:
            cls._db_system = _db_system_from_driver(connection_string.partition('://')[0])
            cls._server_address = None
            cls._server_port = None
            return

        cls._db_system = _db_system_from_driver(url.drivername)
        cls._server_address = url.host
        cls._server_port = url.port


def _db_span_attributes(operation: str, target: str | None, query_text: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        'db.system': Model._db_system,
        'db.operation': operation,
        'db.query.text': query_text,
    }
    if target:
        attrs['db.collection.name'] = target
    if Model._server_address:
        attrs['server.address'] = Model._server_address
    if Model._server_port is not None:
        attrs['server.port'] = Model._server_port
    return attrs


def _db_span_name(operation: str, target: str | None) -> str:
    return f'{operation} {target}' if target else Model._db_system


def _db_system_from_driver(drivername: str) -> str:
    driver = drivername.split('+', 1)[0].lower()
    if driver in {'postgres', 'postgresql'}:
        return 'postgresql'
    if driver == 'mysql':
        return 'mysql'
    return driver or 'database'


def _model_table_name(model_class: Any) -> str | None:
    table_name = getattr(model_class, '__tablename__', None)
    if isinstance(table_name, str) and table_name:
        return table_name
    table = getattr(model_class, '__table__', None)
    name = getattr(table, 'name', None)
    return name if isinstance(name, str) and name else None


def _select_by_id_query(table_name: str | None) -> str:
    target = table_name or '<unknown>'
    return _query_text('SELECT', '*', 'FROM', target, 'WHERE', 'id', '=', ':id')


def _select_all_query(table_name: str | None) -> str:
    target = table_name or '<unknown>'
    return _query_text('SELECT', '*', 'FROM', target)


def _insert_query(table_name: str | None) -> str:
    target = table_name or '<unknown>'
    return _query_text('INSERT', 'INTO', target, 'VALUES', '(:redacted)')


def _query_text(*parts: str) -> str:
    return ' '.join(parts)
