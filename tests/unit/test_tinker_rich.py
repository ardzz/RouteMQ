import unittest
from collections import namedtuple
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


def _rich_available():
    try:
        import rich  # noqa: F401

        return True
    except ImportError:
        return False


@unittest.skipUnless(_rich_available(), 'rich not installed; install with [cli] extra')
class TestRichHelpers(unittest.TestCase):
    def setUp(self):
        from routemq.tinker import _make_repl_helpers

        self.console = MagicMock()
        self.helpers = _make_repl_helpers(self.console)

    def _printed_table(self):
        from rich.table import Table

        args, _ = self.console.print.call_args
        self.assertIsInstance(args[0], Table)
        return args[0]

    def _table_cells(self, table):
        return [list(column.cells) for column in table.columns]

    def test_helpers_dict_has_four_callables(self):
        self.assertEqual(set(self.helpers), {'print_rich', 'print_sql', 'print_json', 'print_rows'})
        for value in self.helpers.values():
            self.assertTrue(callable(value))

    def test_print_rich_delegates_to_console(self):
        obj = {'foo': 'bar'}
        self.helpers['print_rich'](obj)
        self.console.print.assert_called_once_with(obj)

    def test_print_sql_wraps_in_syntax(self):
        from rich.syntax import Syntax

        self.helpers['print_sql']('SELECT 1')
        args, _ = self.console.print.call_args
        self.assertIsInstance(args[0], Syntax)

    def test_print_json_serializes_dict(self):
        from rich.syntax import Syntax

        self.helpers['print_json']({'a': 1, 'b': datetime(2026, 5, 27)})
        args, _ = self.console.print.call_args
        self.assertIsInstance(args[0], Syntax)

    def test_print_rows_empty_prints_no_rows_message(self):
        self.helpers['print_rows']([], title='Empty Test')
        args, _ = self.console.print.call_args
        self.assertIn('No rows in Empty Test', args[0])

    def test_print_rows_with_dicts_renders_table(self):
        rows = [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}]
        self.helpers['print_rows'](rows, title='Test Table')
        self._printed_table()

    def test_print_rows_with_objects_renders_table(self):
        class Row:
            def __init__(self, row_id, name):
                self.id = row_id
                self.name = name

        self.helpers['print_rows']([Row(1, 'alpha')], title='Object Rows')
        self._printed_table()

    def test_print_rows_with_mapping_rows_uses_mapping_keys_and_values(self):
        class Row:
            def __init__(self, mapping):
                self._mapping = mapping

        self.helpers['print_rows']([Row({'id': 1, 'name': 'alpha'})], title='Mapping Rows')

        table = self._printed_table()
        self.assertEqual([column.header for column in table.columns], ['id', 'name'])
        self.assertEqual(self._table_cells(table), [['1'], ['alpha']])

    def test_print_rows_with_namedtuple_rows_uses_asdict_keys_and_values(self):
        Row = namedtuple('Row', ['id', 'name'])

        self.helpers['print_rows']([Row(1, 'alpha')], title='Namedtuple Rows')

        table = self._printed_table()
        self.assertEqual([column.header for column in table.columns], ['id', 'name'])
        self.assertEqual(self._table_cells(table), [['1'], ['alpha']])

    def test_print_rows_with_sequence_rows_uses_index_columns_and_values(self):
        self.helpers['print_rows']([(1, 'alpha')], title='Sequence Rows')

        table = self._printed_table()
        self.assertEqual([column.header for column in table.columns], ['0', '1'])
        self.assertEqual(self._table_cells(table), [['1'], ['alpha']])

    def test_print_rows_with_scalar_rows_uses_value_column(self):
        self.helpers['print_rows']([42], title='Scalar Rows')

        table = self._printed_table()
        self.assertEqual([column.header for column in table.columns], ['value'])
        self.assertEqual(self._table_cells(table), [['42']])


@unittest.skipUnless(_rich_available(), 'rich not installed')
class TestBannerHelpers(unittest.TestCase):
    def test_print_banner_rich_calls_console(self):
        from routemq.tinker import _print_banner_rich

        console = MagicMock()
        app = MagicMock()
        app.mysql_enabled = True
        app.redis_enabled = False
        _print_banner_rich(console, app)
        console.print.assert_called_once()

    def test_print_helpers_table_rich_calls_console_for_enabled_db(self):
        from routemq.tinker import _print_helpers_table_rich

        console = MagicMock()
        _print_helpers_table_rich(console, db_enabled=True)
        self.assertGreaterEqual(console.print.call_count, 3)

    def test_print_helpers_table_rich_calls_console_for_disabled_db(self):
        from routemq.tinker import _print_helpers_table_rich

        console = MagicMock()
        _print_helpers_table_rich(console, db_enabled=False)
        self.assertEqual(console.print.call_count, 3)

    def test_install_tracebacks_calls_rich_install(self):
        from routemq.tinker import _install_tracebacks

        with (
            patch('routemq.tinker._load_rich', return_value=True),
            patch('routemq.tinker._rich_install_traceback') as mock_install,
        ):
            _install_tracebacks()

        mock_install.assert_called_once_with(show_locals=True)

    def test_load_rich_initializes_cached_console(self):
        import routemq.tinker as tinker

        with (
            patch('routemq.tinker._console', None),
            patch('routemq.tinker.Console', None),
            patch('routemq.tinker.Panel', None),
            patch('routemq.tinker.Table', None),
            patch('routemq.tinker.Syntax', None),
            patch('routemq.tinker._rich_install_traceback', None),
            patch('routemq.tinker.box', None),
            patch('routemq.tinker._RICH_AVAILABLE', False),
        ):
            self.assertTrue(tinker._load_rich())
            self.assertTrue(tinker._RICH_AVAILABLE)
            self.assertIsNotNone(tinker._console)


@unittest.skipUnless(_rich_available(), 'rich not installed')
class TestTinkerEnvironmentRichGlobals(unittest.TestCase):
    def test_setup_globals_injects_rich_helpers(self):
        from routemq.tinker import TinkerEnvironment

        app = MagicMock()
        app.redis_enabled = False
        with patch.object(TinkerEnvironment, '_import_models'):
            env = TinkerEnvironment(app)

        self.assertIn('print_rich', env.globals)
        self.assertIn('print_sql', env.globals)
        self.assertIn('print_json', env.globals)
        self.assertIn('print_rows', env.globals)


class TestTinkerEnvironmentSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup_database_session_disabled_prints_warning(self):
        from routemq.model import Model
        from routemq.tinker import TinkerEnvironment

        app = MagicMock()
        app.redis_enabled = False
        with patch.object(TinkerEnvironment, '_import_models'):
            env = TinkerEnvironment(app)

        with patch.object(Model, '_is_enabled', False), patch('builtins.print') as mock_print:
            await env._setup_database_session()

        self.assertIsNone(env.session)
        mock_print.assert_called_with('⚠ Database is disabled in configuration')

    async def test_setup_database_session_enabled_sets_session(self):
        from routemq.model import Model
        from routemq.tinker import TinkerEnvironment

        app = MagicMock()
        app.redis_enabled = False
        session = MagicMock()
        with patch.object(TinkerEnvironment, '_import_models'):
            env = TinkerEnvironment(app)

        with (
            patch.object(Model, '_is_enabled', True),
            patch.object(Model, 'get_session', new=AsyncMock(return_value=session)),
            patch('builtins.print') as mock_print,
        ):
            await env._setup_database_session()

        self.assertIs(env.session, session)
        mock_print.assert_called_with('✓ Database session established')

    @unittest.skipUnless(_rich_available(), 'rich not installed')
    async def test_setup_uses_rich_banner_when_available(self):
        from routemq.model import Model
        from routemq.tinker import TinkerEnvironment

        app = MagicMock()
        app.redis_enabled = True
        with patch.object(TinkerEnvironment, '_import_models'):
            env = TinkerEnvironment(app)

        with (
            patch.object(env, '_setup_database_session', new=AsyncMock()),
            patch('routemq.tinker._install_tracebacks') as mock_tracebacks,
            patch('routemq.tinker._print_banner_rich') as mock_banner,
            patch('routemq.tinker._print_helpers_table_rich') as mock_helpers,
            patch.object(Model, '_is_enabled', False),
            patch('builtins.print'),
        ):
            await env.setup()

        mock_tracebacks.assert_called_once()
        mock_banner.assert_called_once()
        mock_helpers.assert_called_once()

    async def test_setup_uses_plain_banner_when_rich_unavailable(self):
        from routemq.tinker import TinkerEnvironment

        app = MagicMock()
        app.redis_enabled = False
        with patch.object(TinkerEnvironment, '_import_models'):
            env = TinkerEnvironment(app)

        with (
            patch('routemq.tinker._load_rich', return_value=False),
            patch.object(env, '_setup_database_session', new=AsyncMock()),
            patch.object(env, '_print_banner_plain') as mock_plain,
        ):
            await env.setup()

        mock_plain.assert_called_once()


class TestAsyncMagics(unittest.TestCase):
    def test_arun_wraps_line_in_await(self):
        from routemq.tinker import AsyncMagics

        shell = MagicMock()
        magics = AsyncMagics()
        magics.shell = shell

        result = magics.arun('do_work()')

        shell.run_cell_async.assert_called_once_with('await do_work()')
        self.assertIs(result, shell.run_cell_async.return_value)


class TestRichFallback(unittest.TestCase):
    def test_module_imports_when_rich_present_or_absent(self):
        import routemq.tinker

        self.assertTrue(hasattr(routemq.tinker, '_RICH_AVAILABLE'))

    def test_plain_banner_is_available_for_rich_fallback(self):
        from routemq.model import Model
        from routemq.tinker import TinkerEnvironment

        app = MagicMock()
        app.redis_enabled = False
        with patch.object(TinkerEnvironment, '_import_models'):
            env = TinkerEnvironment(app)

        with patch.object(Model, '_is_enabled', False), patch('builtins.print') as mock_print:
            env._print_banner_plain()

        printed = '\n'.join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn('RouteMQ Tinker', printed)
        self.assertIn('ENABLE_MYSQL=true', printed)

    def test_plain_banner_enabled_database_examples_are_available(self):
        from routemq.model import Model
        from routemq.tinker import TinkerEnvironment

        app = MagicMock()
        app.redis_enabled = False
        with patch.object(TinkerEnvironment, '_import_models'):
            env = TinkerEnvironment(app)

        with patch.object(Model, '_is_enabled', True), patch('builtins.print') as mock_print:
            env._print_banner_plain()

        printed = '\n'.join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn('Device(device_id', printed)
        self.assertIn('run_async(session.commit())', printed)


if __name__ == '__main__':
    unittest.main()
