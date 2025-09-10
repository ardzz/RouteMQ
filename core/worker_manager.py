import asyncio
import importlib
import logging
import multiprocessing
import os
import time
import uuid
from typing import List, Dict, Any

from .router import Router
from .router_registry import RouterRegistry


class WorkerProcess:
    """Individual worker process that handles MQTT subscriptions."""

    def __init__(self, worker_id: int, router_directory: str, shared_routes: List[Dict[str, Any]],
                 broker_config: Dict[str, str], group_name: str):
        self.worker_id = worker_id
        self.router_directory = router_directory
        self.router = None
        self.shared_routes = shared_routes
        self.broker_config = broker_config
        self.group_name = group_name
        self.client = None
        self.logger = logging.getLogger(f"worker-{worker_id}")

    def setup_router(self):
        """Setup router by dynamically loading from router directory."""
        try:
            if self.router_directory:
                registry = RouterRegistry(self.router_directory)
                self.router = registry.discover_and_load_routers()
                self.logger.info(f"Worker {self.worker_id} loaded router dynamically from {self.router_directory}")
            else:
                self.router = Router()
                self.logger.warning(f"Worker {self.worker_id} using empty router")
        except Exception as e:
            self.logger.error(f"Worker {self.worker_id} failed to load router: {e}")
            self.router = Router()

    def setup_client(self):
        """Setup MQTT client for this worker."""
        from paho.mqtt import client as mqtt_client

        client_id = f"{self.broker_config.get('client_id_prefix', 'mqtt-worker')}-{self.worker_id}-{uuid.uuid4().hex[:8]}"

        self.client = mqtt_client.Client(client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        username = self.broker_config.get('username')
        password = self.broker_config.get('password')
        if username and password:
            self.client.username_pw_set(username, password)

        self.logger.info(f"Worker {self.worker_id} connecting with client ID: {client_id}")

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        self.logger.info(f"Worker {self.worker_id} connected with result code {rc}")

        for route_info in self.shared_routes:
            topic = f"$share/{self.group_name}/{route_info['mqtt_topic']}"
            self.logger.info(f"Worker {self.worker_id} subscribing to {topic}")
            client.subscribe(topic, route_info['qos'])

    def _on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server."""
        import json

        self.logger.debug(f"Worker {self.worker_id} received message on topic {msg.topic}")

        try:
            try:
                payload = json.loads(msg.payload.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = msg.payload

            actual_topic = msg.topic
            if msg.topic.startswith(f"$share/{self.group_name}/"):
                actual_topic = msg.topic[len(f"$share/{self.group_name}/"):]

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.router.dispatch(actual_topic, payload, client))
            finally:
                loop.close()

        except Exception as e:
            self.logger.error(f"Worker {self.worker_id} error processing message: {str(e)}")

    def run(self):
        """Run this worker process."""
        self.setup_router()
        self.setup_client()

        broker = self.broker_config['broker']
        port = int(self.broker_config['port'])

        self.client.connect(broker, port)
        self.client.loop_start()

        try:
            self.logger.info(f"Worker {self.worker_id} started")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info(f"Worker {self.worker_id} shutting down...")
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def worker_process_main(worker_id: int, router_directory: str, shared_routes: List[Dict],
                       broker_config: Dict, group_name: str):
    """Main function for worker process."""
    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s - Worker-{worker_id} - %(name)s - %(levelname)s - %(message)s'
    )

    worker = WorkerProcess(worker_id, router_directory, shared_routes, broker_config, group_name)
    worker.run()


class WorkerManager:
    """Manages multiple worker processes for horizontal scaling."""

    def __init__(self, router: Router, group_name: str = None, router_directory: str = "app.routers"):
        self.router = router
        self.group_name = group_name or os.getenv("MQTT_GROUP_NAME", "mqtt_framework_group")
        self.router_directory = router_directory
        self.workers: List[multiprocessing.Process] = []
        self.logger = logging.getLogger("worker_manager")

    def get_shared_routes_info(self) -> List[Dict[str, Any]]:
        """Extract information about shared routes."""
        shared_routes = []
        for route in self.router.routes:
            if route.shared:
                shared_routes.append({
                    'topic': route.topic,
                    'mqtt_topic': route.mqtt_topic,
                    'qos': route.qos,
                    'worker_count': route.worker_count,
                })
        return shared_routes

    def start_workers(self, num_workers: int = None):
        """Start worker processes for shared subscriptions."""
        shared_routes = self.get_shared_routes_info()
        if not shared_routes:
            self.logger.info("No shared routes found, workers not needed")
            return

        if num_workers is None:
            num_workers = self.router.get_total_workers_needed()

        if num_workers <= 0:
            return

        broker_config = {
            'broker': os.getenv("MQTT_BROKER", "localhost"),
            'port': os.getenv("MQTT_PORT", "1883"),
            'username': os.getenv("MQTT_USERNAME"),
            'password': os.getenv("MQTT_PASSWORD"),
            'client_id_prefix': os.getenv("MQTT_CLIENT_ID", "mqtt-worker")
        }

        self.logger.info(f"Starting {num_workers} workers for shared subscriptions")

        for worker_id in range(num_workers):
            process = multiprocessing.Process(
                target=worker_process_main,
                args=(worker_id, self.router_directory, shared_routes, broker_config, self.group_name)
            )
            process.start()
            self.workers.append(process)
            self.logger.info(f"Started worker {worker_id} (PID: {process.pid})")

    def stop_workers(self):
        """Stop all worker processes."""
        self.logger.info("Stopping all workers...")

        for i, worker in enumerate(self.workers):
            if worker.is_alive():
                self.logger.info(f"Terminating worker {i} (PID: {worker.pid})")
                worker.terminate()
                worker.join(timeout=5)

                if worker.is_alive():
                    self.logger.warning(f"Force killing worker {i}")
                    worker.kill()
                    worker.join()

        self.workers.clear()
        self.logger.info("All workers stopped")

    def get_worker_count(self) -> int:
        """Get the number of active workers."""
        return len([w for w in self.workers if w.is_alive()])
