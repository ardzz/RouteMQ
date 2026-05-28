import logging
import unittest
from typing import Any, cast
from unittest.mock import MagicMock, patch

from routemq.router import Router
from routemq.worker_manager import WorkerProcess, worker_process_main


def _make_worker(
    worker_id: int = 0,
    router_directory: str = 'app.routers',
    shared_routes: Any = None,
    broker_config: Any = None,
    group_name: str = 'workers',
) -> WorkerProcess:
    return WorkerProcess(
        worker_id=worker_id,
        router_directory=router_directory,
        shared_routes=shared_routes or [],
        broker_config=broker_config or {'broker': 'localhost', 'port': '1883'},
        group_name=group_name,
    )


class WorkerProcessSetupRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.Worker-0')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_setup_router_loads_from_registry_when_directory_set(self) -> None:
        worker = _make_worker(router_directory='custom.routers')
        fake_router = Router()
        with patch('routemq.worker_manager.RouterRegistry') as mock_registry_cls:
            mock_instance = MagicMock()
            mock_instance.discover_and_load_routers.return_value = fake_router
            mock_registry_cls.return_value = mock_instance

            worker.setup_router()

        mock_registry_cls.assert_called_once_with('custom.routers')
        self.assertIs(worker.router, fake_router)

    def test_setup_router_uses_empty_when_directory_empty(self) -> None:
        worker = _make_worker(router_directory='')
        worker.setup_router()
        self.assertIsInstance(worker.router, Router)
        self.assertEqual(cast(Router, worker.router).routes, [])

    def test_setup_router_falls_back_to_empty_on_exception(self) -> None:
        worker = _make_worker(router_directory='broken.routers')
        with patch(
            'routemq.worker_manager.RouterRegistry',
            side_effect=RuntimeError('registry boom'),
        ):
            worker.setup_router()
        self.assertIsInstance(worker.router, Router)


class WorkerProcessSetupClientTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.Worker-0')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_setup_client_configures_callbacks(self) -> None:
        worker = _make_worker(broker_config={'broker': 'h', 'port': '1883'})
        fake_client = MagicMock()
        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client) as mock_cls:
            worker.setup_client()
        self.assertIs(worker.client, fake_client)
        self.assertEqual(fake_client.on_connect, worker._on_connect)
        self.assertEqual(fake_client.on_message, worker._on_message)
        mock_cls.assert_called_once()
        fake_client.username_pw_set.assert_not_called()

    def test_setup_client_applies_credentials_when_provided(self) -> None:
        worker = _make_worker(broker_config={'broker': 'h', 'port': '1883', 'username': 'u', 'password': 'p'})
        fake_client = MagicMock()
        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            worker.setup_client()
        fake_client.username_pw_set.assert_called_once_with('u', 'p')


class WorkerProcessOnConnectTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.Worker-0')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_on_connect_subscribes_to_all_shared_routes_with_group_prefix(self) -> None:
        routes = [
            {'mqtt_topic': 'devices/+/status', 'qos': 1},
            {'mqtt_topic': 'sensors/+/data', 'qos': 0},
        ]
        worker = _make_worker(shared_routes=routes, group_name='workers')
        fake_client = MagicMock()
        worker._on_connect(fake_client, None, None, 0)
        call_args = [c.args for c in fake_client.subscribe.call_args_list]
        self.assertIn(('$share/workers/devices/+/status', 1), call_args)
        self.assertIn(('$share/workers/sensors/+/data', 0), call_args)


class WorkerProcessOnMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.Worker-0')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_on_message_strips_share_prefix_and_dispatches(self) -> None:
        worker = _make_worker(group_name='workers')
        captured: dict[str, Any] = {}

        async def fake_dispatch(topic: str, payload: Any, client: Any) -> None:
            captured['topic'] = topic
            captured['payload'] = payload

        router_mock = MagicMock()
        router_mock.dispatch = fake_dispatch
        worker.router = router_mock

        msg = MagicMock()
        msg.topic = '$share/workers/devices/abc/status'
        msg.payload = b'{"state": "ok"}'

        worker._on_message(MagicMock(), None, msg)
        self.addCleanup(worker._stop_dispatch_loop)

        self.assertEqual(captured['topic'], 'devices/abc/status')
        self.assertEqual(captured['payload'], {'state': 'ok'})

    def test_on_message_keeps_raw_bytes_for_non_json_payload(self) -> None:
        worker = _make_worker(group_name='workers')
        captured: dict[str, Any] = {}

        async def fake_dispatch(topic: str, payload: Any, client: Any) -> None:
            captured['payload'] = payload

        router_mock = MagicMock()
        router_mock.dispatch = fake_dispatch
        worker.router = router_mock

        msg = MagicMock()
        msg.topic = 'plain/topic'
        msg.payload = b'\xff\xfe binary'

        worker._on_message(MagicMock(), None, msg)
        self.addCleanup(worker._stop_dispatch_loop)
        self.assertEqual(captured['payload'], b'\xff\xfe binary')

    def test_on_message_swallows_dispatch_exceptions(self) -> None:
        worker = _make_worker(group_name='workers')

        async def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError('dispatch failed')

        router_mock = MagicMock()
        router_mock.dispatch = boom
        worker.router = router_mock

        msg = MagicMock()
        msg.topic = 'plain/topic'
        msg.payload = b'{}'

        worker._on_message(MagicMock(), None, msg)
        self.addCleanup(worker._stop_dispatch_loop)

    def test_on_message_reuses_persistent_loop_for_multiple_messages(self) -> None:
        worker = _make_worker(group_name='workers')
        captured: list[str] = []

        async def fake_dispatch(topic: str, payload: Any, client: Any) -> None:
            captured.append(topic)

        router_mock = MagicMock()
        router_mock.dispatch = fake_dispatch
        worker.router = router_mock

        first = MagicMock(topic='plain/one', payload=b'{}')
        second = MagicMock(topic='plain/two', payload=b'{}')

        worker._on_message(MagicMock(), None, first)
        first_loop = worker.loop
        worker._on_message(MagicMock(), None, second)
        self.addCleanup(worker._stop_dispatch_loop)

        self.assertIs(worker.loop, first_loop)
        self.assertEqual(captured, ['plain/one', 'plain/two'])


class WorkerProcessRunTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger('RouteMQ.Worker-0')
        original_level = logger.level
        logger.setLevel(logging.CRITICAL)
        self.addCleanup(logger.setLevel, original_level)

    def test_run_connects_loops_and_cleans_up_on_interrupt(self) -> None:
        worker = _make_worker(broker_config={'broker': 'h', 'port': '1883'})
        fake_client = MagicMock()

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch('routemq.worker_manager.time.sleep', side_effect=KeyboardInterrupt()),
            patch.object(worker, 'setup_router'),
        ):
            worker.run()

        fake_client.connect.assert_called_once_with('h', 1883)
        fake_client.loop_start.assert_called_once()
        fake_client.loop_stop.assert_called_once()
        fake_client.disconnect.assert_called_once()

    def test_run_logs_expected_broker_connect_failure_without_loop_cleanup(self) -> None:
        worker = _make_worker(broker_config={'broker': 'h', 'port': '1883'})
        fake_client = MagicMock()
        fake_client.connect.side_effect = ConnectionRefusedError(111, 'Connection refused')

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch.object(worker, 'setup_router'),
            self.assertLogs('RouteMQ.Worker-0', level='ERROR') as logs,
        ):
            worker.run()

        self.assertTrue(any('could not connect to MQTT broker at h:1883' in message for message in logs.output))
        fake_client.loop_start.assert_not_called()
        fake_client.loop_stop.assert_not_called()
        fake_client.disconnect.assert_not_called()

    def test_run_propagates_non_network_connect_failure(self) -> None:
        worker = _make_worker(broker_config={'broker': 'h', 'port': '1883'})
        fake_client = MagicMock()
        fake_client.connect.side_effect = OSError(28, 'No space left on device')

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch.object(worker, 'setup_router'),
            self.assertRaises(OSError),
        ):
            worker.run()

        fake_client.loop_start.assert_not_called()


class WorkerProcessMainEntryTests(unittest.TestCase):
    def test_worker_process_main_constructs_and_runs(self) -> None:
        with (
            patch('routemq.worker_manager.WorkerProcess') as mock_cls,
            patch('routemq.worker_manager.configure_logging') as configure_logging,
        ):
            instance = MagicMock()
            mock_cls.return_value = instance
            worker_process_main(7, 'r', [], {'broker': 'h', 'port': '1883'}, 'group')

        configure_logging.assert_called_once_with(log_to_console=True)
        mock_cls.assert_called_once_with(7, 'r', [], {'broker': 'h', 'port': '1883'}, 'group')
        instance.run.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
