import logging
from typing import Any, Optional, cast

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
logger = logging.getLogger('RouteMQ.Model')


class Model(Base):
    """Base model class that all models should extend."""

    __abstract__ = True

    # This will be set by the application bootstrap
    _engine: Any = None
    _session_factory: Any = None
    _is_enabled = False

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
        logger.info('Database connection configured')

    @classmethod
    async def cleanup(cls):
        """Cleanup database connections and close the engine."""
        if cls._engine is not None:
            await cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None
            cls._is_enabled = False
            logger.info('Database connections closed')

    @classmethod
    async def get_session(cls) -> Optional[AsyncSession]:
        """Get a new session for database operations."""
        if not cls._is_enabled:
            logger.warning('Database operations attempted while MySQL is disabled')
            return None

        if cls._session_factory is None:
            raise RuntimeError('Database not configured. Call Model.configure() first.')
        return cast(AsyncSession, cls._session_factory())

    @classmethod
    async def create_tables(cls):
        """Create all tables defined in models."""
        if not cls._is_enabled:
            logger.info('Skipping table creation as MySQL is disabled')
            return

        engine = cls._engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info('Database tables created')

    @classmethod
    async def find(cls, model_class, id_value):
        """Find a record by ID."""
        if not cls._is_enabled:
            logger.warning(f'Find operation on {model_class.__name__} skipped - MySQL disabled')
            return None

        session = await cls.get_session()
        if session is None:
            return None

        async with session:
            result = await session.execute(select(model_class).where(model_class.id == id_value))
            return result.scalars().first()

    @classmethod
    async def all(cls, model_class):
        """Get all records of a model."""
        if not cls._is_enabled:
            logger.warning(f'All records query on {model_class.__name__} skipped - MySQL disabled')
            return []

        session = await cls.get_session()
        if session is None:
            return []

        async with session:
            result = await session.execute(select(model_class))
            return result.scalars().all()

    @classmethod
    async def create(cls, model_class, **kwargs):
        """Create a new record."""
        if not cls._is_enabled:
            logger.warning(f'Create operation on {model_class.__name__} skipped - MySQL disabled')
            return None

        session = await cls.get_session()
        if session is None:
            return None

        async with session:
            obj = model_class(**kwargs)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj
