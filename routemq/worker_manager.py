import asyncio
import logging
import multiprocessing
import threading
import time
from typing import List, Dict, Any

from .router import Router
from .router_registry import RouterRegistry
from .logging_config import configure_logging
from .observability import lifecycle, reset_context, set_context, start_span
from .mqtt_utils import (
    build_worker_broker_config,
    build_worker_client_id,
    connect_mqtt_client_with_retries,
    create_mqtt_client,
    get_mqtt_group_name,
    is_network_startup_error,
    parse_mqtt_payload,
)


class WorkerProcess:
    """Individual worker process that handles MQTT subscriptions."""

    def __init__(
        self,
        worker_id: int,
        router_directory: str,
        shared_routes: List[Dict[str, Any]],
        broker_config: Dict[str, Any],
        group_name: str,
    ):
        self.worker_id = worker_id
        self.router_directory = router_directory
        self.router: Any = None
        self.shared_routes = shared_routes
        self.broker_config = broker_config
        self.group_name = group_name
        self.client: Any = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self.logger = logging.getLogger(f'RouteMQ.Worker-{self.worker_id}')

    def setup_router(self):
        """Setup router by dynamically loading from router directory."""
        try:
            if self.router_directory:
                registry = RouterRegistry(self.router_directory)
                self.router = registry.discover_and_load_routers()
                self.logger.info(f'Worker {self.worker_id} loaded router dynamically from {self.router_directory}')
            else:
                self.router = Router()
                self.logger.warning(f'Worker {self.worker_id} using empty router')
        except Exception as e:
            self.logger.error(f'Worker {self.worker_id} failed to load router: {e}')
            self.router = Router()

    def setup_client(self):
        """Setup MQTT client for this worker."""
        client_id = build_worker_client_id(
            self.worker_id,
            self.broker_config.get('client_id_prefix', 'mqtt-worker'),
        )

        username = self.broker_config.get('username')
        password = self.broker_config.get('password')
        self.client = create_mqtt_client(
            client_id,
            on_connect=self._on_connect,
            on_message=self._on_message,
            username=username,
            password=password,
        )

        self.logger.info(f'Worker {self.worker_id} connecting with client ID: {client_id}')

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        self.logger.info(f'Worker {self.worker_id} connected with result code {rc}')

        for route_info in self.shared_routes:
            topic = f'$share/{self.group_name}/{route_info["mqtt_topic"]}'
            self.logger.info(f'Worker {self.worker_id} subscribing to {topic}')
            client.subscribe(topic, route_info['qos'])

    def _on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server."""
        self.logger.debug(f'Worker {self.worker_id} received message on topic {msg.topic}')

        try:
            payload = parse_mqtt_payload(msg.payload)

            actual_topic = msg.topic
            if msg.topic.startswith(f'$share/{self.group_name}/'):
                actual_topic = msg.topic[len(f'$share/{self.group_name}/') :]

            context = {
                'source': 'mqtt',
                'process': 'worker',
                'worker_id': self.worker_id,
                'mqtt_topic': msg.topic,
                'actual_topic': actual_topic,
                'group_name': self.group_name,
            }

            self._schedule_dispatch(actual_topic, payload, client, context)

        except Exception as e:
            self.logger.error(f'Worker {self.worker_id} error processing message: {str(e)}')

    def _schedule_dispatch(self, topic: str, payload: Any, client: Any, context: Dict[str, Any]) -> None:
        """Schedule MQTT dispatch on the worker's persistent loop."""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()

        coro = self._dispatch_mqtt_message(topic, payload, client, context)
        if self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)

            def log_failure(done_future: Any) -> None:
                try:
                    done_future.result()
                except Exception as exc:
                    self.logger.error(f'Worker {self.worker_id} error processing message: {str(exc)}')

            future.add_done_callback(log_failure)
        else:
            self.loop.run_until_complete(coro)

    async def _dispatch_mqtt_message(self, topic: str, payload: Any, client: Any, context: Dict[str, Any]) -> None:
        """Restore per-message observability context inside the worker loop."""
        token = set_context(context)
        try:
            span_attributes = {
                'messaging.system': 'mqtt',
                'messaging.destination': topic,
                'routemq.process.role': 'worker',
                'routemq.worker.id': self.worker_id,
            }
            with start_span('mqtt.receive', span_attributes, kind='consumer'):
                lifecycle('mqtt.message.received', {'process': 'worker'})
                await self.router.dispatch(topic, payload, client)
                lifecycle('mqtt.message.succeeded', {'process': 'worker'})
        except Exception as exc:
            lifecycle('mqtt.message.failed', {'process': 'worker', 'error': exc.__class__.__name__})
            raise
        finally:
            reset_context(token)

    def run(self):
        """Run this worker process."""
        self.setup_router()
        self._start_dispatch_loop()
        self.setup_client()

        broker = self.broker_config['broker']
        port = int(self.broker_config['port'])
        retry_config = self.broker_config.get('retry_config')

        try:
            connect_mqtt_client_with_retries(
                self.client,
                broker,
                port,
                retry_config=retry_config,
                process='worker',
            )
        except OSError as exc:
            if not is_network_startup_error(exc):
                raise
            self.logger.error(
                f'Worker {self.worker_id} could not connect to MQTT broker at {broker}:{port} ({exc}). '
                'Please verify the broker is running and the address/port are correct.'
            )
            self._stop_dispatch_loop()
            return

        self.client.loop_start()

        try:
            self.logger.info(f'Worker {self.worker_id} started')
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info(f'Worker {self.worker_id} shutting down...')
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            self._stop_dispatch_loop()

    def _start_dispatch_loop(self) -> None:
        """Start the worker's persistent asyncio loop in a thread."""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
        loop = self.loop
        if loop.is_running():
            return

        def run_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self._loop_thread = threading.Thread(target=run_loop, name=f'RouteMQWorkerLoop-{self.worker_id}', daemon=True)
        self._loop_thread.start()

    def _stop_dispatch_loop(self) -> None:
        """Stop and close the worker's persistent asyncio loop."""
        if self.loop is None:
            return
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=5)
        self.loop.close()
        self.loop = None
        self._loop_thread = None


def worker_process_main(
    worker_id: int, router_directory: str, shared_routes: List[Dict], broker_config: Dict, group_name: str
):
    """Main function for worker process."""
    configure_logging(log_to_console=True)

    worker = WorkerProcess(worker_id, router_directory, shared_routes, broker_config, group_name)
    worker.run()


class WorkerManager:
    """Manages multiple worker processes for horizontal scaling."""

    def __init__(self, router: Router, group_name: str | None = None, router_directory: str = 'app.routers'):
        self.router = router
        self.group_name = group_name or get_mqtt_group_name()
        self.router_directory = router_directory
        self.workers: List[multiprocessing.Process] = []
        self.logger = logging.getLogger('RouteMQ.WorkerManager')

    def get_shared_routes_info(self) -> List[Dict[str, Any]]:
        """Extract information about shared routes."""
        shared_routes = []
        for route in self.router.routes:
            if route.shared:
                shared_routes.append(
                    {
                        'topic': route.topic,
                        'mqtt_topic': route.mqtt_topic,
                        'qos': route.qos,
                        'worker_count': route.worker_count,
                    }
                )
        return shared_routes

    def start_workers(self, num_workers: int | None = None):
        """Start one process per shared route worker slot and skip failed starts."""
        shared_routes = self.get_shared_routes_info()
        if not shared_routes:
            self.logger.info('No shared routes found, workers not needed')
            return

        required_workers = sum(route_info['worker_count'] for route_info in shared_routes)

        if num_workers is None:
            num_workers = required_workers
        elif num_workers == self.router.get_total_workers_needed() and num_workers < required_workers:
            num_workers = required_workers

        if num_workers <= 0:
            return

        broker_config = build_worker_broker_config()

        self.logger.info(f'Starting {num_workers} workers for shared subscriptions')

        worker_topics = [route_info['topic'] for route_info in shared_routes for _ in range(route_info['worker_count'])]

        for worker_id in range(num_workers):
            process = multiprocessing.Process(
                target=worker_process_main,
                args=(worker_id, self.router_directory, shared_routes, broker_config, self.group_name),
            )
            try:
                process.start()
            except (OSError, RuntimeError) as exc:
                route_topic = worker_topics[worker_id] if worker_id < len(worker_topics) else 'unknown'
                self.logger.warning(
                    f'Failed to start worker {worker_id} for route {route_topic}: {type(exc).__name__}: {exc}'
                )
                continue
            self.workers.append(process)
            self.logger.info(f'Started worker {worker_id} (PID: {process.pid})')

    def stop_workers(self):
        """Stop all worker processes."""
        self.logger.info('Stopping all workers...')

        for i, worker in enumerate(self.workers):
            if worker.is_alive():
                self.logger.info(f'Terminating worker {i} (PID: {worker.pid})')
                worker.terminate()
                worker.join(timeout=5)

                if worker.is_alive():
                    self.logger.warning(f'Force killing worker {i}')
                    worker.kill()
                    worker.join()

        self.workers.clear()
        self.logger.info('All workers stopped')

    def get_worker_count(self) -> int:
        """Get the number of active workers."""
        return len([w for w in self.workers if w.is_alive()])
