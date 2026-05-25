import os
import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession

from core.model import Base, Model


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
            patch('core.model.create_async_engine', return_value=engine) as create_async_engine,
            patch('core.model.sessionmaker', return_value=session_factory) as sessionmaker,
        ):
            Model.configure('mysql+aiomysql://user:pass@db:3306/app')

        create_async_engine.assert_called_once_with('mysql+aiomysql://user:pass@db:3306/app')
        sessionmaker.assert_called_once_with(engine, expire_on_commit=False, class_=AsyncSession)
        self.assertIs(Model._engine, engine)
        self.assertIs(Model._session_factory, session_factory)
        self.assertTrue(Model._is_enabled)

    def test_configure_called_twice_replaces_existing_state(self) -> None:
        first_engine = MagicMock(name='first_engine')
        second_engine = MagicMock(name='second_engine')
        first_factory = MagicMock(name='first_factory')
        second_factory = MagicMock(name='second_factory')

        with (
            patch('core.model.create_async_engine', side_effect=[first_engine, second_engine]) as create_async_engine,
            patch('core.model.sessionmaker', side_effect=[first_factory, second_factory]) as sessionmaker,
        ):
            Model.configure('mysql+aiomysql://first')
            Model.configure('mysql+aiomysql://second')

        self.assertEqual(create_async_engine.call_count, 2)
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

    def test_enable_mysql_false_does_not_change_configure_contract(self) -> None:
        engine = MagicMock(name='engine')
        session_factory = MagicMock(name='session_factory')

        with (
            patch.dict(os.environ, {'ENABLE_MYSQL': 'false'}),
            patch('core.model.create_async_engine', return_value=engine) as create_async_engine,
            patch('core.model.sessionmaker', return_value=session_factory),
        ):
            Model.configure('mysql+aiomysql://user:pass@db:3306/app')

        create_async_engine.assert_called_once_with('mysql+aiomysql://user:pass@db:3306/app')
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


if __name__ == '__main__':
    unittest.main()
