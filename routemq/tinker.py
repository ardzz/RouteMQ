"""
RouteMQ Tinker - Interactive REPL for testing ORM relationships and queries
Similar to Laravel Artisan Tinker
"""

import asyncio
import os
import sys
from pathlib import Path
import nest_asyncio  # pyright: ignore[reportMissingImports]

from IPython import embed  # pyright: ignore[reportMissingImports]
from IPython.terminal.interactiveshell import TerminalInteractiveShell  # pyright: ignore[reportMissingImports]
from IPython.core.magic import Magics, magics_class, line_magic  # pyright: ignore[reportMissingImports]

from bootstrap.app import Application
from routemq.model import Model, Base
from routemq.redis_manager import redis_manager

Console = None
Panel = None
Table = None
Syntax = None
RichFiglet = None
_rich_install_traceback = None
box = None
_RICH_AVAILABLE = False
_RICH_FIGLET_AVAILABLE = False
_console = None


def _load_rich():
    """Lazy-load Rich primitives used only by the tinker REPL."""
    global Console, Panel, Table, Syntax, RichFiglet, _rich_install_traceback
    global box, _RICH_AVAILABLE, _RICH_FIGLET_AVAILABLE, _console

    if _console is not None:
        return True

    try:
        from rich.console import Console as _Console  # pyright: ignore[reportMissingImports]
        from rich.panel import Panel as _Panel  # pyright: ignore[reportMissingImports]
        from rich.table import Table as _Table  # pyright: ignore[reportMissingImports]
        from rich.syntax import Syntax as _Syntax  # pyright: ignore[reportMissingImports]
        from rich.traceback import install as _install  # pyright: ignore[reportMissingImports]
        from rich import box as _box  # pyright: ignore[reportMissingImports]
    except ImportError:
        # Audit Accept: Rich is optional for the REPL.
        _RICH_AVAILABLE = False
        return False

    Console = _Console
    Panel = _Panel
    Table = _Table
    Syntax = _Syntax
    _rich_install_traceback = _install
    box = _box

    try:
        from rich_pyfiglet import RichFiglet as _RichFiglet  # pyright: ignore[reportMissingImports]
    except ImportError:
        # Audit Accept: figlet banner is cosmetic; Rich tables still work.
        RichFiglet = None
        _RICH_FIGLET_AVAILABLE = False
    else:
        RichFiglet = _RichFiglet
        _RICH_FIGLET_AVAILABLE = True

    _RICH_AVAILABLE = True
    _console = Console()
    return True


def _install_tracebacks():
    """Install Rich's traceback handler with locals visible."""
    if _load_rich() and _rich_install_traceback is not None:
        _rich_install_traceback(show_locals=True)


# Enable nested event loops for IPython compatibility
nest_asyncio.apply()


def _make_repl_helpers(console):
    """Return REPL helper functions that use Rich for styled output."""
    import json as _json

    if not _load_rich() or Syntax is None or Table is None or box is None:
        raise RuntimeError('Rich helpers require rich to be installed')

    syntax_cls = Syntax
    table_cls = Table
    box_module = box

    def print_rich(obj):
        """Pretty-print any object via Rich."""
        console.print(obj)

    def print_sql(sql: str):
        """Render SQL with syntax highlighting."""
        console.print(syntax_cls(sql, 'sql', theme='monokai', line_numbers=False))

    def print_json(payload):
        """Render JSON-serializable object as colored JSON."""
        text = payload if isinstance(payload, str) else _json.dumps(payload, indent=2, default=str)
        console.print(syntax_cls(text, 'json', theme='monokai', line_numbers=False))

    def print_rows(rows, title: str = 'Query Results'):
        """Render iterable of ORM rows or dicts as Rich Table."""
        rows = list(rows)
        if not rows:
            console.print(f'[yellow]No rows in {title}[/yellow]')
            return

        first = rows[0]
        if isinstance(first, dict):
            cols = list(first.keys())

            def get_dict(row, col):
                return row.get(col)

            get = get_dict

        elif hasattr(first, '_mapping'):
            cols = list(first._mapping.keys())

            def get_mapping(row, col):
                return row._mapping[col]

            get = get_mapping

        elif hasattr(first, '__table__'):
            cols = [c.name for c in first.__table__.columns]

            def get_table_attr(row, col):
                return getattr(row, col)

            get = get_table_attr

        else:
            if hasattr(first, '_asdict'):
                cols = list(first._asdict().keys())

                def get_namedtuple(row, col):
                    return row._asdict()[col]

                get = get_namedtuple
            elif isinstance(first, (list, tuple)):
                cols = [str(index) for index in range(len(first))]

                def get_sequence(row, col):
                    return row[int(col)]

                get = get_sequence
            else:
                try:
                    attrs = vars(first)
                except TypeError:
                    # Audit Accept: scalar rows are rendered as a single value column.
                    cols = ['value']

                    def get_value(row, col):
                        return row

                    get = get_value
                else:
                    cols = list(attrs.keys())

                    def get_object_attr(row, col):
                        return getattr(row, col)

                    get = get_object_attr

        table = table_cls(title=title, box=box_module.SIMPLE_HEAVY)
        for col in cols:
            table.add_column(str(col), overflow='fold')
        for row in rows:
            table.add_row(*[str(get(row, col)) for col in cols])
        console.print(table)

    return {
        'print_rich': print_rich,
        'print_sql': print_sql,
        'print_json': print_json,
        'print_rows': print_rows,
    }


def _print_banner_rich(console, app):
    """Render the styled startup banner with compact system info."""
    import platform
    import psutil

    if not _load_rich() or Panel is None or Table is None or box is None:
        raise RuntimeError('Rich banner requires rich to be installed')

    panel_cls = Panel
    table_cls = Table
    box_module = box
    figlet_cls = RichFiglet

    summary = table_cls.grid(padding=(0, 2))
    summary.add_column(style='dim')
    summary.add_column(style='bold cyan')
    summary.add_column(style='dim')
    summary.add_column(style='bold')

    mem_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    summary.add_row('RouteMQ', Application.get_version(), 'Host', platform.node() or 'localhost')
    summary.add_row('OS', f'{platform.system()} {platform.release()}', 'Python', platform.python_version())
    summary.add_row(
        'Services',
        f'MySQL {"on" if app.mysql_enabled else "off"} / Redis {"on" if app.redis_enabled else "off"}',
        'Machine',
        f'{psutil.cpu_count(logical=True)} cores / {mem_gb} GB RAM',
    )

    if _RICH_FIGLET_AVAILABLE and figlet_cls is not None:
        console.print(
            figlet_cls(
                'RouteMQ',
                font='standard',
                colors=['cyan', 'bright_blue'],
                justify='left',
                remove_blank_lines=True,
            )
        )
        console.print(summary)
    else:
        console.print(panel_cls(summary, title='RouteMQ Tinker', border_style='cyan', padding=(0, 1)))


def _print_helpers_table_rich(console, db_enabled: bool):
    """Render the available objects + helper functions as Rich tables."""
    if not _load_rich() or Table is None or box is None:
        raise RuntimeError('Rich helper tables require rich to be installed')

    table_cls = Table
    box_module = box

    objects = table_cls(title='Available objects', box=box_module.SIMPLE)
    objects.add_column('Name', style='bold cyan')
    objects.add_column('Description')
    objects.add_row('app', 'Application instance')
    objects.add_row('Model', 'Base Model class')
    objects.add_row('Base', 'SQLAlchemy declarative base')
    objects.add_row('session', 'Database session (if MySQL enabled)')
    objects.add_row('redis_manager', 'Redis manager (if Redis enabled)')
    objects.add_row('select', 'SQLAlchemy select function')
    objects.add_row('and_, or_, func, desc, asc', 'SQLAlchemy query operators')
    objects.add_row('run_async()', 'Helper to run async code in REPL')
    console.print(objects)

    helpers = table_cls(title='Rich helpers', box=box_module.SIMPLE)
    helpers.add_column('Helper', style='bold green')
    helpers.add_column('Use')
    helpers.add_row('print_rich(obj)', 'Pretty-print any object via Rich')
    helpers.add_row('print_sql(sql)', 'SQL with syntax highlighting')
    helpers.add_row('print_json(payload)', 'JSON with syntax highlighting')
    helpers.add_row('print_rows(rows, title=)', 'Iterable of ORM rows or dicts as styled Table')
    console.print(helpers)

    if db_enabled:
        console.print('\n[dim]Tip: Use [bold]run_async()[/bold] to execute async queries.[/dim]')
        console.print('[dim]Example: [bold]devices = run_async(session.execute(select(Device)))[/bold][/dim]')
    else:
        console.print('\n[yellow]Database is disabled. Enable in .env with ENABLE_MYSQL=true.[/yellow]')


@magics_class
class AsyncMagics(Magics):
    """Custom magic commands for async operations."""

    @line_magic
    def arun(self, line):
        """Execute async code using line magic."""
        code = f'await {line}'
        return self.shell.run_cell_async(code)


class TinkerEnvironment:
    """Environment setup for the tinker REPL session."""

    def __init__(self, app: Application):
        self.app = app
        self.session = None
        self._setup_globals()

    async def _setup_database_session(self):
        """Setup database session for the REPL."""
        if Model._is_enabled:
            self.session = await Model.get_session()
            print(f'✓ Database session established')
        else:
            print('⚠ Database is disabled in configuration')

    def _setup_globals(self):
        """Setup global variables for the REPL session."""
        # Import SQLAlchemy query functions
        from sqlalchemy.future import select
        from sqlalchemy import and_, or_, func, desc, asc

        def run_async(coro):
            """Helper to run async code synchronously in REPL."""
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio  # pyright: ignore[reportMissingImports]

                    nest_asyncio.apply()
                    return loop.run_until_complete(coro)
                else:
                    return loop.run_until_complete(coro)
            except RuntimeError:
                # Audit Accept: no active REPL loop, so asyncio.run is the safe fallback.
                return asyncio.run(coro)

        self.globals = {
            'app': self.app,
            'Model': Model,
            'Base': Base,
            'session': None,  # Will be set after async setup
            'redis_manager': redis_manager if self.app.redis_enabled else None,
            'asyncio': asyncio,
            'os': os,
            'sys': sys,
            'Path': Path,
            # SQLAlchemy query helpers
            'select': select,
            'and_': and_,
            'or_': or_,
            'func': func,
            'desc': desc,
            'asc': asc,
            # Helper functions
            'run_async': run_async,
        }

        if _load_rich():
            self.globals.update(_make_repl_helpers(_console))

        # Import all models dynamically
        self._import_models()

    def _import_models(self):
        """Dynamically import all models from app.models."""
        try:
            models_path = Path('app/models')
            if models_path.exists():
                for model_file in models_path.glob('*.py'):
                    if model_file.name != '__init__.py':
                        module_name = f'app.models.{model_file.stem}'
                        try:
                            __import__(module_name)
                            module = sys.modules[module_name]

                            # Add all classes that inherit from Base to globals
                            for attr_name in dir(module):
                                attr = getattr(module, attr_name)
                                if isinstance(attr, type) and hasattr(attr, '__tablename__') and issubclass(attr, Base):
                                    self.globals[attr_name] = attr
                                    if not _RICH_AVAILABLE:
                                        print(f'✓ Imported model: {attr_name}')
                        except ImportError as e:
                            # Audit Accept: optional app model import failures are displayed in the REPL.
                            print(f'⚠ Could not import {module_name}: {e}')
        except Exception as e:
            # Audit Accept: model discovery is optional convenience for tinker startup.
            print(f'⚠ Error importing models: {e}')

    async def setup(self):
        """Async setup for the tinker environment."""
        rich_loaded = _load_rich()
        if rich_loaded:
            _install_tracebacks()
            _print_banner_rich(_console, self.app)

        await self._setup_database_session()
        self.globals['session'] = self.session

        # Setup Redis if enabled
        if self.app.redis_enabled:
            print(f'✓ Redis manager available')

        if rich_loaded:
            _print_helpers_table_rich(_console, Model._is_enabled)
        else:
            self._print_banner_plain()

    def _print_banner_plain(self):
        """Render the plain-text startup banner used when Rich is unavailable."""
        print('\n' + '=' * 60)
        print('🔧 RouteMQ Tinker - Interactive REPL Environment')
        print('=' * 60)
        print('Available objects:')
        print('  app          - Application instance')
        print('  Model        - Base Model class')
        print('  Base         - SQLAlchemy declarative base')
        print('  session      - Database session (if enabled)')
        print('  redis_manager- Redis manager (if enabled)')
        print('  select       - SQLAlchemy select function')
        print('  and_, or_    - SQLAlchemy logical operators')
        print('  func         - SQLAlchemy functions')
        print('  desc, asc    - SQLAlchemy ordering')
        print('  run_async()  - Helper to run async code')
        print('\nHelper Functions:')
        print('  query_devices()      - Get all devices')
        print('  query_users()        - Get all users')
        print('  create_sample_device() - Create a sample device')
        print('\nExample usage:')
        if Model._is_enabled:
            print('  # Using run_async helper for queries:')
            print('  devices = run_async(query_devices())')
            print('  print(devices)')
            print('  ')
            print('  # Direct async queries (use run_async):')
            print('  result = run_async(session.execute(select(Device)))')
            print('  devices = result.scalars().all()')
            print('  ')
            print('  # Create new record:')
            print('  device = run_async(create_sample_device())')
            print('  print(device)')
            print('  ')
            print('  # Manual creation:')
            print("  device = Device(device_id='test-001', name='Test Device')")
            print('  session.add(device)')
            print('  run_async(session.commit())')
        else:
            print('  # Database is disabled. Enable it in .env file:')
            print('  ENABLE_MYSQL=true')
        print("\nTip: Use 'run_async()' to execute async functions.")
        print("Tip: Put a ';' at the end of a line to suppress output.")
        print("Type 'exit()' or Ctrl+D to quit")
        print('=' * 60 + '\n')


def start_tinker_sync(env_file='.env'):  # pragma: no cover - interactive IPython entrypoint
    """Synchronous wrapper for starting tinker."""

    async def _start_tinker():
        tinker_env = None
        try:
            # Create application instance
            app = Application(env_file=env_file, show_banner=False, log_to_console=False)

            # Setup tinker environment
            tinker_env = TinkerEnvironment(app)
            await tinker_env.setup()

            # Configure IPython for better async support
            from IPython.terminal.interactiveshell import TerminalInteractiveShell  # pyright: ignore[reportMissingImports]

            # Get or create IPython instance
            shell = TerminalInteractiveShell.instance()

            # Enable autoawait for async support
            shell.autoawait = True

            # Register custom magic commands
            shell.register_magics(AsyncMagics)

            # Start the embedding with our custom namespace
            embed(
                user_ns=tinker_env.globals,
                banner1='',  # We'll show our own banner
                exit_msg='Goodbye! 👋',
                config=shell.config,
            )

        except KeyboardInterrupt:
            # Audit Accept: interactive Ctrl+C exits cleanly.
            print('\nGoodbye! 👋')
        except Exception as e:
            # Audit Accept: interactive startup errors are printed with traceback for users.
            print(f'Error starting tinker: {e}')
            import traceback

            traceback.print_exc()
        finally:
            # Cleanup
            if tinker_env is not None and tinker_env.session:
                await tinker_env.session.close()

    # Check if we're already in an event loop
    try:
        loop = asyncio.get_running_loop()
        # If we get here, there's already a running loop
        # Use nest_asyncio to handle this
        nest_asyncio.apply()
        # Create a new event loop in a thread
        import threading

        def run_in_thread():
            # Create new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(_start_tinker())
            finally:
                new_loop.close()

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

    except RuntimeError:
        # Audit Accept: no running event loop, safe to use asyncio.run.
        # No running loop, safe to use asyncio.run
        asyncio.run(_start_tinker())


def run_tinker():  # pragma: no cover - console script entrypoint
    """Entry point for running tinker from command line."""
    start_tinker_sync()


if __name__ == '__main__':  # pragma: no cover
    run_tinker()
