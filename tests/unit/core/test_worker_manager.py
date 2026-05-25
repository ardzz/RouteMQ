import unittest
from typing import Any, cast
from unittest.mock import MagicMock, patch

from core.router import Router
from core.worker_manager import WorkerManager, WorkerProcess, worker_process_main


async def first_handler(*, payload: Any, client: Any) -> None:
    return None


async def second_handler(*, payload: Any, client: Any) -> None:
    return None


async def device_handler(*, device_id: str, payload: Any, client: Any) -> None:
    return None


class TestWorkerManager(unittest.TestCase):
    def make_process(self, pid: int = 1234, alive: bool = True) -> MagicMock:
        process = MagicMock()
        process.pid = pid
        process.is_alive.return_value = alive
        return process

    def make_router(self) -> Router:
        router = Router()
        router.on('plain/topic', first_handler, qos=0, shared=False, worker_count=99)
        router.on('shared/one', first_handler, qos=1, shared=True, worker_count=2)
        router.on('shared/two/{device_id}', device_handler, qos=2, shared=True, worker_count=3)
        return router

    def test_shared_routes_info_excludes_non_shared_routes(self) -> None:
        manager = WorkerManager(self.make_router(), group_name='workers', router_directory='app.routers')

        shared_routes = manager.get_shared_routes_info()

        self.assertEqual(
            shared_routes,
            [
                {
                    'topic': 'shared/one',
                    'mqtt_topic': 'shared/one',
                    'qos': 1,
                    'worker_count': 2,
                },
                {
                    'topic': 'shared/two/{device_id}',
                    'mqtt_topic': 'shared/two/+',
                    'qos': 2,
                    'worker_count': 3,
                },
            ],
        )

    def test_start_workers_spawns_processes_only_when_shared_routes_exist(self) -> None:
        router = Router()
        router.on('plain/topic', first_handler, shared=False, worker_count=5)
        manager = WorkerManager(router, group_name='workers', router_directory='app.routers')

        with patch('core.worker_manager.multiprocessing.Process') as process_cls:
            manager.start_workers()

        process_cls.assert_not_called()
        self.assertEqual(manager.workers, [])

    def test_start_workers_tracks_started_processes_for_shared_routes(self) -> None:
        manager = WorkerManager(self.make_router(), group_name='workers', router_directory='app.routers')
        processes = [self.make_process(pid=100), self.make_process(pid=101)]

        with patch('core.worker_manager.multiprocessing.Process', side_effect=processes) as process_cls:
            manager.start_workers(num_workers=2)

        self.assertEqual(process_cls.call_count, 2)
        self.assertEqual(manager.workers, processes)
        for process in processes:
            process.start.assert_called_once_with()

    def test_process_targets_include_worker_main_and_shared_route_metadata(self) -> None:
        manager = WorkerManager(self.make_router(), group_name='workers', router_directory='custom.routers')
        processes = [self.make_process(pid=200), self.make_process(pid=201)]

        with patch.dict(
            'os.environ',
            {
                'MQTT_BROKER': 'broker.local',
                'MQTT_PORT': '1884',
                'MQTT_USERNAME': 'user',
                'MQTT_PASSWORD': 'pass',
                'MQTT_CLIENT_ID': 'route-worker',
            },
        ):
            with patch('core.worker_manager.multiprocessing.Process', side_effect=processes) as process_cls:
                manager.start_workers(num_workers=2)

        first_call, second_call = process_cls.call_args_list
        first_kwargs = first_call.kwargs
        second_kwargs = second_call.kwargs
        expected_shared_routes = manager.get_shared_routes_info()
        expected_broker_config = {
            'broker': 'broker.local',
            'port': '1884',
            'username': 'user',
            'password': 'pass',
            'client_id_prefix': 'route-worker',
        }

        self.assertIs(first_kwargs['target'], worker_process_main)
        self.assertEqual(
            first_kwargs['args'], (0, 'custom.routers', expected_shared_routes, expected_broker_config, 'workers')
        )
        self.assertIs(second_kwargs['target'], worker_process_main)
        self.assertEqual(
            second_kwargs['args'], (1, 'custom.routers', expected_shared_routes, expected_broker_config, 'workers')
        )

    def test_default_worker_count_is_sum_of_shared_route_worker_counts(self) -> None:
        manager = WorkerManager(self.make_router(), group_name='workers', router_directory='app.routers')
        processes = [self.make_process(pid=300 + index) for index in range(5)]

        with patch('core.worker_manager.multiprocessing.Process', side_effect=processes) as process_cls:
            manager.start_workers()

        self.assertEqual(process_cls.call_count, 5)

    def test_worker_process_subscribes_to_share_group_topics_on_connect(self) -> None:
        shared_routes = [
            {'mqtt_topic': 'shared/one', 'qos': 1},
            {'mqtt_topic': 'shared/two/+', 'qos': 2},
        ]
        worker = WorkerProcess(
            worker_id=1,
            router_directory='app.routers',
            shared_routes=cast(list[dict[str, Any]], shared_routes),
            broker_config={},
            group_name='workers',
        )
        client = MagicMock()

        worker._on_connect(client, None, None, 0)

        self.assertEqual(
            client.subscribe.call_args_list,
            [
                unittest.mock.call('$share/workers/shared/one', 1),
                unittest.mock.call('$share/workers/shared/two/+', 2),
            ],
        )

    def test_stop_workers_terminates_alive_processes_and_clears_tracking(self) -> None:
        manager = WorkerManager(Router(), group_name='workers', router_directory='app.routers')
        alive = self.make_process(pid=400, alive=True)
        alive.is_alive.side_effect = [True, False]
        stopped = self.make_process(pid=401, alive=False)
        manager.workers.extend([alive, stopped])

        manager.stop_workers()

        alive.terminate.assert_called_once_with()
        alive.join.assert_called_once_with(timeout=5)
        alive.kill.assert_not_called()
        stopped.terminate.assert_not_called()
        stopped.join.assert_not_called()
        self.assertEqual(manager.workers, [])

    def test_stop_workers_kills_process_still_alive_after_terminate(self) -> None:
        manager = WorkerManager(Router(), group_name='workers', router_directory='app.routers')
        process = self.make_process(pid=500)
        process.is_alive.side_effect = [True, True]
        manager.workers.append(process)

        manager.stop_workers()

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.join.call_args_list, [unittest.mock.call(timeout=5), unittest.mock.call()])
        self.assertEqual(manager.workers, [])

    def test_spawn_failure_does_not_crash_manager_and_remaining_workers_start(self) -> None:
        manager = WorkerManager(self.make_router(), group_name='workers', router_directory='app.routers')
        first = self.make_process(pid=600)
        failed = self.make_process(pid=601)
        failed.start.side_effect = OSError('cannot spawn')
        third = self.make_process(pid=602)
        fourth = self.make_process(pid=603)
        fifth = self.make_process(pid=604)

        with patch('core.worker_manager.multiprocessing.Process', side_effect=[first, failed, third, fourth, fifth]):
            manager.start_workers(num_workers=3)

        first.start.assert_called_once_with()
        failed.start.assert_called_once_with()
        third.start.assert_called_once_with()
        fourth.start.assert_called_once_with()
        fifth.start.assert_called_once_with()
        self.assertEqual(manager.workers, [first, third, fourth, fifth])


if __name__ == '__main__':
    unittest.main()
