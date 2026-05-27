import logging
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from routemq.model import Model


class _StubModel:
    id = MagicMock()


class ModelStateGuard(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._saved = (Model._engine, Model._session_factory, Model._is_enabled)
        logger = logging.getLogger('RouteMQ.Model')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def tearDown(self) -> None:
        Model._engine, Model._session_factory, Model._is_enabled = self._saved


class ModelGetSessionTests(ModelStateGuard):
    async def test_returns_none_when_disabled(self) -> None:
        Model._is_enabled = False
        self.assertIsNone(await Model.get_session())

    async def test_raises_when_enabled_but_factory_missing(self) -> None:
        Model._is_enabled = True
        Model._session_factory = None
        with self.assertRaises(RuntimeError):
            await Model.get_session()

    async def test_returns_session_from_factory(self) -> None:
        Model._is_enabled = True
        sentinel = MagicMock()
        Model._session_factory = MagicMock(return_value=sentinel)
        result = await Model.get_session()
        self.assertIs(result, sentinel)


class ModelFindTests(ModelStateGuard):
    async def test_returns_none_when_disabled(self) -> None:
        Model._is_enabled = False
        result = await Model.find(_StubModel, 1)
        self.assertIsNone(result)

    async def test_returns_first_scalar_when_enabled(self) -> None:
        Model._is_enabled = True
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        scalars = MagicMock()
        scalars.first.return_value = 'found-row'
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars
        session.execute = AsyncMock(return_value=execute_result)

        with (
            patch.object(Model, 'get_session', AsyncMock(return_value=session)),
            patch('routemq.model.select', return_value=MagicMock()),
        ):
            result = await Model.find(_StubModel, 42)

        self.assertEqual(result, 'found-row')


class ModelAllTests(ModelStateGuard):
    async def test_returns_empty_list_when_disabled(self) -> None:
        Model._is_enabled = False
        result = await Model.all(_StubModel)
        self.assertEqual(result, [])

    async def test_returns_all_scalars_when_enabled(self) -> None:
        Model._is_enabled = True
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        scalars = MagicMock()
        scalars.all.return_value = ['row1', 'row2']
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars
        session.execute = AsyncMock(return_value=execute_result)

        with (
            patch.object(Model, 'get_session', AsyncMock(return_value=session)),
            patch('routemq.model.select', return_value=MagicMock()),
        ):
            result = await Model.all(_StubModel)

        self.assertEqual(result, ['row1', 'row2'])


class ModelCreateTests(ModelStateGuard):
    async def test_returns_none_when_disabled(self) -> None:
        Model._is_enabled = False
        result = await Model.create(_StubModel, name='x')
        self.assertIsNone(result)

    async def test_creates_commits_and_refreshes_when_enabled(self) -> None:
        Model._is_enabled = True
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        class _Created:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

        with patch.object(Model, 'get_session', AsyncMock(return_value=session)):
            result = await Model.create(_Created, name='value')

        self.assertIsInstance(result, _Created)
        self.assertEqual(result.kwargs, {'name': 'value'})
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
