"""
RouteMQ Tinker - Interactive REPL for testing ORM relationships and queries
Similar to Laravel Artisan Tinker
"""
import asyncio
import os
import sys
from pathlib import Path

from IPython import embed
from IPython.terminal.interactiveshell import TerminalInteractiveShell

from bootstrap.app import Application
from core.model import Model, Base
from core.redis_manager import redis_manager


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
        print("  asyncio      - Asyncio module for async operations")
        print("\nExample usage:")
        if Model._is_enabled:
            print("  # Query examples (adjust for your models):")
            print("  result = await session.execute(select(YourModel))")
            print("  items = result.scalars().all()")
            print("  ")
            print("  # Create new record:")
            print("  new_item = YourModel(name='test')")
            print("  session.add(new_item)")
            print("  await session.commit()")
        else:
            print("  # Database is disabled. Enable it in .env file:")
            print("  ENABLE_MYSQL=true")
        print("\nType 'exit()' or Ctrl+D to quit")
        print("="*60 + "\n")


class AsyncIPythonShell:
    """Custom IPython shell with async support."""

    def __init__(self, tinker_env: TinkerEnvironment):
        self.tinker_env = tinker_env

    def start(self):
        """Start the interactive shell."""
        # Configure IPython for async support
        shell = TerminalInteractiveShell.instance()
        shell.autoawait = True

        # Start the embedding with our custom namespace
        embed(
            user_ns=self.tinker_env.globals,
            banner1="",  # We'll show our own banner
            exit_msg="Goodbye! 👋"
        )


async def start_tinker(env_file=".env"):
    """Start the tinker REPL environment."""
    try:
        # Create application instance
        print("Initializing RouteMQ application...")
        app = Application(env_file=env_file)

        # Setup tinker environment
        tinker_env = TinkerEnvironment(app)
        await tinker_env.setup()

        # Start interactive shell
        shell = AsyncIPythonShell(tinker_env)
        shell.start()

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


def run_tinker():
    """Entry point for running tinker from command line."""
    asyncio.run(start_tinker())


if __name__ == "__main__":
    run_tinker()
