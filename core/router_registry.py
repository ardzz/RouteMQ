import importlib
import logging
import os
import pkgutil
from pathlib import Path
from typing import List

from .router import Router


class RouterRegistry:
    """
    Dynamically discovers and loads routers from multiple files.
    """

    def __init__(self, router_directory: str = "app.routers"):
        self.router_directory = router_directory
        self.logger = logging.getLogger("RouteMQ.RouterRegistry")
        self.main_router = Router()

    def discover_and_load_routers(self) -> Router:
        """
        Discover all router files and merge them into a single router.

        Returns:
            Router: Combined router with all routes from discovered files
        """
        try:
            # Import the routers package
            routers_package = importlib.import_module(self.router_directory)
            package_path = routers_package.__path__

            # Discover all modules in the routers directory
            router_modules = []
            for finder, name, ispkg in pkgutil.iter_modules(package_path):
                if not ispkg and not name.startswith('_'):  # Skip packages and private modules
                    module_name = f"{self.router_directory}.{name}"
                    router_modules.append(module_name)

            self.logger.info(f"Discovered router modules: {router_modules}")

            # Load each router module and merge routes
            for module_name in router_modules:
                self._load_router_module(module_name)

            self.logger.info(f"Successfully loaded {len(self.main_router.routes)} total routes from {len(router_modules)} modules")

        except ImportError as e:
            self.logger.error(f"Could not import router directory '{self.router_directory}': {e}")
            self.logger.info("Using empty router")
        except Exception as e:
            self.logger.error(f"Error during router discovery: {e}")
            self.logger.info("Using empty router")

        return self.main_router

    def _load_router_module(self, module_name: str) -> None:
        """
        Load a specific router module and merge its routes.

        Args:
            module_name: Full module name (e.g., 'app.routers.api')
        """
        try:
            module = importlib.import_module(module_name)

            # Look for router instance in the module
            if hasattr(module, 'router'):
                router = getattr(module, 'router')
                if isinstance(router, Router):
                    self._merge_router(router, module_name)
                else:
                    self.logger.warning(f"Module {module_name} has 'router' attribute but it's not a Router instance")
            else:
                self.logger.warning(f"Module {module_name} does not have a 'router' attribute")

        except ImportError as e:
            self.logger.error(f"Could not import router module '{module_name}': {e}")
        except Exception as e:
            self.logger.error(f"Error loading router from '{module_name}': {e}")

    def _merge_router(self, router: Router, module_name: str) -> None:
        """
        Merge routes from a router into the main router.

        Args:
            router: Router instance to merge
            module_name: Name of the module for logging
        """
        routes_added = 0
        for route in router.routes:
            self.main_router.routes.append(route)
            routes_added += 1

        self.logger.info(f"Merged {routes_added} routes from {module_name}")

    def get_router_module_path_for_workers(self) -> str:
        """
        Get the router directory path for worker processes.
        This is used by workers to load the same router configuration.

        Returns:
            str: Module path that workers should use
        """
        return self.router_directory


def create_dynamic_router(router_directory: str = "app.routers") -> Router:
    """
    Convenience function to create a router with dynamic loading.

    Args:
        router_directory: Directory containing router modules

    Returns:
        Router: Combined router with all discovered routes
    """
    registry = RouterRegistry(router_directory)
    return registry.discover_and_load_routers()
