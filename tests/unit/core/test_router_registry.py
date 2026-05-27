import logging
import unittest
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from routemq.router import Router
from routemq.router_registry import RouterRegistry, create_dynamic_router


def _make_router_module(name: str, routes: list[Any]) -> ModuleType:
    module = ModuleType(name)
    router = Router()
    for route in routes:
        cast(Any, router.routes).append(route)
    cast(Any, module).router = router
    return module


class RouterRegistryInitializationTests(unittest.TestCase):
    def test_default_router_directory_is_app_routers(self) -> None:
        registry = RouterRegistry()
        self.assertEqual(registry.router_directory, 'app.routers')

    def test_custom_router_directory_is_respected(self) -> None:
        registry = RouterRegistry(router_directory='custom.routers')
        self.assertEqual(registry.router_directory, 'custom.routers')

    def test_initialization_creates_empty_main_router(self) -> None:
        registry = RouterRegistry()
        self.assertIsInstance(registry.main_router, Router)
        self.assertEqual(registry.main_router.routes, [])

    def test_logger_is_namespaced(self) -> None:
        registry = RouterRegistry()
        self.assertEqual(registry.logger.name, 'RouteMQ.RouterRegistry')


class RouterRegistryWorkerPathTests(unittest.TestCase):
    def test_returns_configured_directory(self) -> None:
        registry = RouterRegistry(router_directory='custom.path')
        self.assertEqual(registry.get_router_module_path_for_workers(), 'custom.path')

    def test_returns_default_when_unset(self) -> None:
        registry = RouterRegistry()
        self.assertEqual(registry.get_router_module_path_for_workers(), 'app.routers')


class RouterRegistryDiscoveryHappyPathTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.RouterRegistry')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_discovers_valid_modules_and_merges_routes(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])
        module_a = _make_router_module('app.routers.a', ['route_a'])
        module_b = _make_router_module('app.routers.b', ['route_b1', 'route_b2'])

        iter_modules_return = [
            (None, 'a', False),
            (None, 'b', False),
        ]

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=iter_modules_return),
            patch('routemq.router_registry.importlib.import_module') as mock_import,
        ):
            mock_import.side_effect = [fake_package, module_a, module_b]

            registry = RouterRegistry()
            result = registry.discover_and_load_routers()

        self.assertIs(result, registry.main_router)
        self.assertEqual(registry.main_router.routes, ['route_a', 'route_b1', 'route_b2'])

    def test_skips_underscore_prefixed_modules(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])
        module_public = _make_router_module('app.routers.public', ['route_public'])

        iter_modules_return = [
            (None, '_private', False),
            (None, 'public', False),
            (None, '_internal', False),
        ]

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=iter_modules_return),
            patch('routemq.router_registry.importlib.import_module') as mock_import,
        ):
            mock_import.side_effect = [fake_package, module_public]

            registry = RouterRegistry()
            registry.discover_and_load_routers()

        called_modules = [c.args[0] for c in mock_import.call_args_list]
        self.assertIn('app.routers', called_modules)
        self.assertIn('app.routers.public', called_modules)
        self.assertNotIn('app.routers._private', called_modules)
        self.assertNotIn('app.routers._internal', called_modules)
        self.assertEqual(registry.main_router.routes, ['route_public'])

    def test_skips_subpackages(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])
        module_real = _make_router_module('app.routers.real', ['r'])

        iter_modules_return = [
            (None, 'subpkg', True),
            (None, 'real', False),
        ]

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=iter_modules_return),
            patch('routemq.router_registry.importlib.import_module') as mock_import,
        ):
            mock_import.side_effect = [fake_package, module_real]

            registry = RouterRegistry()
            registry.discover_and_load_routers()

        called_modules = [c.args[0] for c in mock_import.call_args_list]
        self.assertNotIn('app.routers.subpkg', called_modules)
        self.assertEqual(registry.main_router.routes, ['r'])

    def test_discovery_returns_empty_when_package_empty(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=[]),
            patch('routemq.router_registry.importlib.import_module', return_value=fake_package),
        ):
            registry = RouterRegistry()
            result = registry.discover_and_load_routers()

        self.assertIsInstance(result, Router)
        self.assertEqual(result.routes, [])


class RouterRegistryDiscoveryErrorPathTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.RouterRegistry')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_import_error_on_root_package_returns_empty_router(self) -> None:
        with patch(
            'routemq.router_registry.importlib.import_module',
            side_effect=ImportError('boom'),
        ):
            registry = RouterRegistry()
            result = registry.discover_and_load_routers()

        self.assertIsInstance(result, Router)
        self.assertEqual(result.routes, [])

    def test_generic_exception_on_root_package_returns_empty_router(self) -> None:
        with patch(
            'routemq.router_registry.importlib.import_module',
            side_effect=RuntimeError('unexpected'),
        ):
            registry = RouterRegistry()
            result = registry.discover_and_load_routers()

        self.assertIsInstance(result, Router)
        self.assertEqual(result.routes, [])

    def test_module_without_router_attribute_is_skipped(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])
        bare_module = ModuleType('app.routers.bare')

        iter_modules_return = [(None, 'bare', False)]

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=iter_modules_return),
            patch('routemq.router_registry.importlib.import_module') as mock_import,
        ):
            mock_import.side_effect = [fake_package, bare_module]

            registry = RouterRegistry()
            registry.discover_and_load_routers()

        self.assertEqual(registry.main_router.routes, [])

    def test_module_with_wrong_type_router_attribute_is_skipped(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])
        bad_module = ModuleType('app.routers.bad')
        cast(Any, bad_module).router = 'not a router instance'

        iter_modules_return = [(None, 'bad', False)]

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=iter_modules_return),
            patch('routemq.router_registry.importlib.import_module') as mock_import,
        ):
            mock_import.side_effect = [fake_package, bad_module]

            registry = RouterRegistry()
            registry.discover_and_load_routers()

        self.assertEqual(registry.main_router.routes, [])

    def test_import_error_on_single_module_does_not_break_others(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])
        good_module = _make_router_module('app.routers.good', ['route_good'])

        iter_modules_return = [
            (None, 'broken', False),
            (None, 'good', False),
        ]

        def import_side_effect(name: str) -> Any:
            if name == 'app.routers':
                return fake_package
            if name == 'app.routers.broken':
                raise ImportError('broken module')
            if name == 'app.routers.good':
                return good_module
            raise AssertionError(f'unexpected import: {name}')

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=iter_modules_return),
            patch('routemq.router_registry.importlib.import_module', side_effect=import_side_effect),
        ):
            registry = RouterRegistry()
            registry.discover_and_load_routers()

        self.assertEqual(registry.main_router.routes, ['route_good'])

    def test_generic_exception_on_single_module_does_not_break_others(self) -> None:
        fake_package = SimpleNamespace(__path__=['/fake/path'])
        good_module = _make_router_module('app.routers.good', ['ok'])

        iter_modules_return = [
            (None, 'crashes', False),
            (None, 'good', False),
        ]

        def import_side_effect(name: str) -> Any:
            if name == 'app.routers':
                return fake_package
            if name == 'app.routers.crashes':
                raise RuntimeError('crash')
            if name == 'app.routers.good':
                return good_module
            raise AssertionError(f'unexpected import: {name}')

        with (
            patch('routemq.router_registry.pkgutil.iter_modules', return_value=iter_modules_return),
            patch('routemq.router_registry.importlib.import_module', side_effect=import_side_effect),
        ):
            registry = RouterRegistry()
            registry.discover_and_load_routers()

        self.assertEqual(registry.main_router.routes, ['ok'])


class RouterRegistryMergeTests(unittest.TestCase):
    def test_merge_preserves_route_order(self) -> None:
        registry = RouterRegistry()
        sub_router = Router()
        for r in ['r1', 'r2', 'r3']:
            cast(Any, sub_router.routes).append(r)

        registry._merge_router(sub_router, 'fake.module')

        self.assertEqual(registry.main_router.routes, ['r1', 'r2', 'r3'])

    def test_merge_appends_to_existing_routes(self) -> None:
        registry = RouterRegistry()
        cast(Any, registry.main_router.routes).append('existing')
        sub_router = Router()
        cast(Any, sub_router.routes).append('new')

        registry._merge_router(sub_router, 'fake.module')

        self.assertEqual(registry.main_router.routes, ['existing', 'new'])

    def test_merge_empty_sub_router_is_noop(self) -> None:
        registry = RouterRegistry()
        cast(Any, registry.main_router.routes).append('original')
        empty_sub = Router()

        registry._merge_router(empty_sub, 'fake.module')

        self.assertEqual(registry.main_router.routes, ['original'])


class CreateDynamicRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.RouterRegistry')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_uses_default_directory(self) -> None:
        with patch('routemq.router_registry.RouterRegistry') as mock_registry_cls:
            mock_instance = MagicMock()
            mock_instance.discover_and_load_routers.return_value = 'sentinel'
            mock_registry_cls.return_value = mock_instance

            result = create_dynamic_router()

        mock_registry_cls.assert_called_once_with('app.routers')
        mock_instance.discover_and_load_routers.assert_called_once_with()
        self.assertEqual(result, 'sentinel')

    def test_passes_custom_directory(self) -> None:
        with patch('routemq.router_registry.RouterRegistry') as mock_registry_cls:
            mock_instance = MagicMock()
            mock_instance.discover_and_load_routers.return_value = 'sentinel'
            mock_registry_cls.return_value = mock_instance

            create_dynamic_router(router_directory='custom.routers')

        mock_registry_cls.assert_called_once_with('custom.routers')


if __name__ == '__main__':
    unittest.main()
