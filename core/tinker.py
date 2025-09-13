"""
RouteMQ Tinker - Interactive REPL for testing ORM relationships and queries
Similar to Laravel Artisan Tinker
"""
import asyncio
import os
import sys
from pathlib import Path
import nest_asyncio

from IPython import embed
from IPython.terminal.interactiveshell import TerminalInteractiveShell

from bootstrap.app import Application
from core.model import Model, Base
from core.redis_manager import redis_manager


# Enable nested event loops for IPython compatibility
nest_asyncio.apply()


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
            print(f"✓ Database session established")
        else:
            print("⚠ Database is disabled in configuration")

    def _setup_globals(self):
        """Setup global variables for the REPL session."""
        # Import SQLAlchemy query functions
        from sqlalchemy.future import select
        from sqlalchemy import and_, or_, func, desc, asc

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
        }

        # Import all models dynamically
        self._import_models()

    def _import_models(self):
        """Dynamically import all models from app.models."""
        try:
            models_path = Path("app/models")
            if models_path.exists():
                for model_file in models_path.glob("*.py"):
                    if model_file.name != "__init__.py":
                        module_name = f"app.models.{model_file.stem}"
                        try:
                            __import__(module_name)
                            module = sys.modules[module_name]

                            # Add all classes that inherit from Base to globals
                            for attr_name in dir(module):
                                attr = getattr(module, attr_name)
                                if (isinstance(attr, type) and
                                    hasattr(attr, '__tablename__') and
                                    issubclass(attr, Base)):
                                    self.globals[attr_name] = attr
                                    print(f"✓ Imported model: {attr_name}")
                        except ImportError as e:
                            print(f"⚠ Could not import {module_name}: {e}")
        except Exception as e:
            print(f"⚠ Error importing models: {e}")

    async def setup(self):
        """Async setup for the tinker environment."""
        await self._setup_database_session()
        self.globals['session'] = self.session

        # Setup Redis if enabled
        if self.app.redis_enabled:
            print(f"✓ Redis manager available")

        print("\n" + "="*60)
        print("🔧 RouteMQ Tinker - Interactive REPL Environment")
        print("="*60)
        print("Available objects:")
        print("  app          - Application instance")
        print("  Model        - Base Model class")
        print("  Base         - SQLAlchemy declarative base")
        print("  session      - Database session (if enabled)")
        print("  redis_manager- Redis manager (if enabled)")
        print("  select       - SQLAlchemy select function")
        print("  and_, or_    - SQLAlchemy logical operators")
        print("  func         - SQLAlchemy functions")
        print("  desc, asc    - SQLAlchemy ordering")
        print("\nExample usage:")
        if Model._is_enabled:
            print("  # Query examples:")
            print("  result = await session.execute(select(Device))")
            print("  devices = result.scalars().all()")
            print("  ")
            print("  # Query with filters:")
            print("  result = await session.execute(")
            print("      select(Device).where(Device.status == 'active')")
            print("  )")
            print("  ")
            print("  # Create new record:")
            print("  device = Device(device_id='test-001', name='Test Device', device_type='sensor')")
            print("  session.add(device)")
            print("  await session.commit()")
            print("  ")
            print("  # Relationships:")
            print("  result = await session.execute(")
            print("      select(Device).where(Device.id == 1)")
            print("  )")
            print("  device = result.scalar_one_or_none()")
            print("  if device:")
            print("      await session.refresh(device, ['messages', 'sensors'])")
            print("      print(device.messages)  # Access related messages")
        else:
            print("  # Database is disabled. Enable it in .env file:")
            print("  ENABLE_MYSQL=true")
        print("\nTip: Put a ';' at the end of a line to suppress output.")
        print("Type 'exit()' or Ctrl+D to quit")
        print("="*60 + "\n")


def start_tinker_sync(env_file=".env"):
    """Synchronous wrapper for starting tinker."""
    async def _start_tinker():
        try:
            # Create application instance
            print("Initializing RouteMQ application...")
            app = Application(env_file=env_file)

            # Setup tinker environment
            tinker_env = TinkerEnvironment(app)
            await tinker_env.setup()

            # Configure IPython for async support
            shell = TerminalInteractiveShell.instance()
            shell.autoawait = True

            # Start the embedding with our custom namespace
            embed(
                user_ns=tinker_env.globals,
                banner1="",  # We'll show our own banner
                exit_msg="Goodbye! 👋"
            )

        except KeyboardInterrupt:
            print("\nGoodbye! 👋")
        except Exception as e:
            print(f"Error starting tinker: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            if hasattr(tinker_env, 'session') and tinker_env.session:
                await tinker_env.session.close()

    # Check if we're already in an event loop
    try:
        loop = asyncio.get_running_loop()
        # If we get here, there's already a running loop
        # Use asyncio.create_task or run in thread
        import threading

        def run_in_thread():
            asyncio.run(_start_tinker())

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

    except RuntimeError:
        # No running loop, safe to use asyncio.run
        asyncio.run(_start_tinker())


def run_tinker():
    """Entry point for running tinker from command line."""
    start_tinker_sync()


if __name__ == "__main__":
    run_tinker()
