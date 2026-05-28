import os
from typing import Any, cast
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from routemq.model import Base, Model


DEFAULT_ENGINE_KWARGS = {
    'pool_size': 5,
    'max_overflow': 10,
    'pool_timeout': 30,
    'pool_recycle': 1800,
    'pool_pre_ping': True,
    'pool_use_lifo': False,
}


class TestModelLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_engine = Model._engine
        self._original_session_factory = Model._session_factory
        self._original_is_enabled = Model._is_enabled
        Model._engine = None
        Model._session_factory = None
        Model._is_enabled = False

    def tearDown(self) -> None:
        Model._engine = self._original_engine
        Model._session_factory = self._original_session_factory
        Model._is_enabled = self._original_is_enabled

    def test_configure_creates_engine_and_session_factory(self) -> None:
        engine = MagicMock(name='engine')
        session_factory = MagicMock(name='session_factory')

        with (
            patch('routemq.model.create_async_engine', return_value=engine) as create_async_engine,
            patch('routemq.model.sessionmaker', return_value=session_factory) as sessionmaker,
        ):
            Model.configure('mysql+aiomysql://user:pass@db:3306/app')

        create_async_engine.assert_called_once_with('mysql+aiomysql://user:pass@db:3306/app', **DEFAULT_ENGINE_KWARGS)
        sessionmaker.assert_called_once_with(engine, expire_on_commit=False, class_=AsyncSession)
        self.assertIs(Model._engine, engine)
        self.assertIs(Model._session_factory, session_factory)
        self.assertTrue(Model._is_enabled)

    def test_configure_passes_pool_kwargs_to_engine(self) -> None:
        cases = {
            'pool_size': {'pool_size': 8},
            'max_overflow': {'max_overflow': 4},
            'pool_timeout': {'pool_timeout': 12},
            'pool_recycle': {'pool_recycle': 900},
            'pool_pre_ping': {'pool_pre_ping': False},
            'pool_use_lifo': {'pool_use_lifo': True},
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                engine = MagicMock(name=f'{name}_engine')
                with (
                    patch('routemq.model.create_async_engine', return_value=engine) as create_async_engine,
                    patch('routemq.model.sessionmaker'),
                ):
                    Model.configure('mysql+aiomysql://user:pass@db:3306/app', **overrides)

                _, kwargs = create_async_engine.call_args
                self.assertEqual(kwargs, DEFAULT_ENGINE_KWARGS | overrides)

    def test_configure_uses_null_pool_without_queue_pool_size_kwargs(self) -> None:
        engine = MagicMock(name='engine')
        with (
            patch('routemq.model.create_async_engine', return_value=engine) as create_async_engine,
            patch('routemq.model.sessionmaker'),
        ):
            Model.configure(
                'mysql+aiomysql://user:pass@db:3306/app',
                pool_size=0,
                max_overflow=0,
                pool_timeout=12,
                pool_recycle=300,
                pool_pre_ping=False,
                pool_use_lifo=True,
                pool_class='null',
            )

        create_async_engine.assert_called_once_with(
            'mysql+aiomysql://user:pass@db:3306/app',
            pool_timeout=12,
            pool_recycle=300,
            pool_pre_ping=False,
            pool_use_lifo=True,
            poolclass=NullPool,
        )

    def test_configure_called_twice_replaces_existing_state(self) -> None:
        first_engine = MagicMock(name='first_engine')
        second_engine = MagicMock(name='second_engine')
        first_factory = MagicMock(name='first_factory')
        second_factory = MagicMock(name='second_factory')

        with (
            patch(
                'routemq.model.create_async_engine', side_effect=[first_engine, second_engine]
            ) as create_async_engine,
            patch('routemq.model.sessionmaker', side_effect=[first_factory, second_factory]) as sessionmaker,
        ):
            Model.configure('mysql+aiomysql://first')
            Model.configure('mysql+aiomysql://second')

        expected_calls = [
            call('mysql+aiomysql://first', **DEFAULT_ENGINE_KWARGS),
            call('mysql+aiomysql://second', **DEFAULT_ENGINE_KWARGS),
        ]
        self.assertEqual(create_async_engine.call_args_list, expected_calls)
        self.assertEqual(sessionmaker.call_count, 2)
        self.assertIs(Model._engine, second_engine)
        self.assertIs(Model._session_factory, second_factory)
        self.assertTrue(Model._is_enabled)

    async def test_create_tables_runs_metadata_create_all_on_configured_engine(self) -> None:
        connection = MagicMock(name='connection')
        connection.run_sync = AsyncMock()
        begin_context = MagicMock(name='begin_context')
        begin_context.__aenter__ = AsyncMock(return_value=connection)
        begin_context.__aexit__ = AsyncMock(return_value=None)
        engine = MagicMock(name='engine')
        engine.begin.return_value = begin_context
        Model._engine = engine
        Model._is_enabled = True

        await Model.create_tables()

        engine.begin.assert_called_once_with()
        connection.run_sync.assert_awaited_once_with(Base.metadata.create_all)

    async def test_create_tables_is_noop_when_disabled(self) -> None:
        engine = MagicMock(name='engine')
        Model._engine = engine
        Model._is_enabled = False

        await Model.create_tables()

        engine.begin.assert_not_called()

    async def test_cleanup_disposes_engine_and_resets_state(self) -> None:
        engine = MagicMock(name='engine')
        engine.dispose = AsyncMock()
        Model._engine = engine
        Model._session_factory = MagicMock(name='session_factory')
        Model._is_enabled = True

        await Model.cleanup()

        engine.dispose.assert_awaited_once_with()
        self.assertIsNone(Model._engine)
        self.assertIsNone(Model._session_factory)
        self.assertFalse(Model._is_enabled)

    async def test_cleanup_is_noop_without_engine(self) -> None:
        Model._engine = None
        Model._session_factory = MagicMock(name='session_factory')
        Model._is_enabled = True

        await Model.cleanup()

        self.assertIsNotNone(Model._session_factory)
        self.assertTrue(Model._is_enabled)

    def test_enable_mysql_false_does_not_change_configure_contract(self) -> None:
        engine = MagicMock(name='engine')
        session_factory = MagicMock(name='session_factory')

        with (
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false'}),
            patch('routemq.model.create_async_engine', return_value=engine) as create_async_engine,
            patch('routemq.model.sessionmaker', return_value=session_factory),
        ):
            Model.configure('mysql+aiomysql://user:pass@db:3306/app')

        create_async_engine.assert_called_once_with('mysql+aiomysql://user:pass@db:3306/app', **DEFAULT_ENGINE_KWARGS)
        self.assertIs(Model._engine, engine)
        self.assertTrue(Model._is_enabled)

    def test_subclass_inherits_declarative_metadata_and_registers_columns(self) -> None:
        class RegressionModel(Model):
            __tablename__ = 'regression_model_lifecycle'

            id = Column(Integer, primary_key=True)
            name = Column(String(64))

        try:
            self.assertIn('regression_model_lifecycle', Base.metadata.tables)
            table = Base.metadata.tables['regression_model_lifecycle']
            self.assertIs(RegressionModel.__table__, table)
            self.assertIn('id', table.columns)
            self.assertIn('name', table.columns)
        finally:
            Base.metadata.remove(RegressionModel.__table__)

    async def test_get_session_returns_usable_async_context_manager(self) -> None:
        session = MagicMock(name='session')
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session_factory = MagicMock(name='session_factory', return_value=session)
        Model._session_factory = session_factory
        Model._is_enabled = True

        returned = await Model.get_session()

        self.assertIs(returned, session)
        session_factory.assert_called_once_with()
        async with cast(Any, returned) as active_session:
            self.assertIs(active_session, session)
        session.__aenter__.assert_awaited_once_with()
        session.__aexit__.assert_awaited_once()

    async def test_get_session_returns_none_when_disabled(self) -> None:
        Model._session_factory = MagicMock(name='session_factory')
        Model._is_enabled = False

        session = await Model.get_session()

        self.assertIsNone(session)
        Model._session_factory.assert_not_called()

    async def test_get_session_raises_when_enabled_without_factory(self) -> None:
        Model._session_factory = None
        Model._is_enabled = True

        with self.assertRaises(RuntimeError):
            await Model.get_session()

    async def test_find_returns_first_record(self) -> None:
        class LookupModel(Model):
            __tablename__ = 'lookup_model_lifecycle'

            id = Column(Integer, primary_key=True)

        record = object()
        result = MagicMock(name='result')
        result.scalars.return_value.first.return_value = record
        session = MagicMock(name='session')
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock(return_value=result)
        Model._is_enabled = True

        try:
            with patch.object(Model, 'get_session', AsyncMock(return_value=session)):
                found = await Model.find(LookupModel, 123)
        finally:
            Base.metadata.remove(LookupModel.__table__)

        self.assertIs(found, record)
        session.execute.assert_awaited_once()

    async def test_all_returns_records(self) -> None:
        class ListedModel(Model):
            __tablename__ = 'listed_model_lifecycle'

            id = Column(Integer, primary_key=True)

        records = [object(), object()]
        result = MagicMock(name='result')
        result.scalars.return_value.all.return_value = records
        session = MagicMock(name='session')
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock(return_value=result)
        Model._is_enabled = True

        try:
            with patch.object(Model, 'get_session', AsyncMock(return_value=session)):
                found = await Model.all(ListedModel)
        finally:
            Base.metadata.remove(ListedModel.__table__)

        self.assertEqual(found, records)
        session.execute.assert_awaited_once()

    async def test_create_persists_and_refreshes_object(self) -> None:
        class CreatedModel:
            def __init__(self, **kwargs: Any):
                self.values = kwargs

        session = MagicMock(name='session')
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        Model._is_enabled = True

        with patch.object(Model, 'get_session', AsyncMock(return_value=session)):
            created = await Model.create(CreatedModel, name='demo')

        self.assertIsNotNone(created)
        self.assertIsInstance(created, CreatedModel)
        assert created is not None
        self.assertEqual(created.values, {'name': 'demo'})
        session.add.assert_called_once_with(created)
        session.commit.assert_awaited_once_with()
        session.refresh.assert_awaited_once_with(created)

    async def test_find_all_create_return_disabled_defaults(self) -> None:
        class DisabledModel:
            pass

        Model._is_enabled = False

        self.assertIsNone(await Model.find(DisabledModel, 1))
        self.assertEqual(await Model.all(DisabledModel), [])
        self.assertIsNone(await Model.create(DisabledModel))

    async def test_find_all_create_handle_missing_session(self) -> None:
        class MissingSessionModel:
            pass

        Model._is_enabled = True

        with patch.object(Model, 'get_session', AsyncMock(return_value=None)):
            self.assertIsNone(await Model.find(MissingSessionModel, 1))
            self.assertEqual(await Model.all(MissingSessionModel), [])
            self.assertIsNone(await Model.create(MissingSessionModel))


if __name__ == '__main__':
    unittest.main()
