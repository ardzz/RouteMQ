import asyncio
import importlib
import json
import logging
import os

from dotenv import load_dotenv
from paho.mqtt import client as mqtt_client

from core.model import Model
from core.router import Router
from core.worker_manager import WorkerManager


class Application:
    def __init__(self, router=None, env_file=".env"):
        """
        Initialize a new RouteMQ application.

        Args:
            router: A Router instance to use. If None, tries to import from app.routers.api
            env_file: The environment file to load configuration from
        """
        load_dotenv(env_file)

        self._setup_logging()

        self.router = router
        if self.router is None:
            try:
                api_module = importlib.import_module('app.routers.api')
                self.router = getattr(api_module, 'router')
                self.logger.info("Router loaded from app.routers.api")
            except (ImportError, AttributeError) as e:
                self.router = Router()
                self.logger.warning(f"Could not load router from app.routers.api: {str(e)}")
                self.logger.info("Using empty router. Register routes manually.")

        self.mysql_enabled = os.getenv("ENABLE_MYSQL", "true").lower() == "true"
        if self.mysql_enabled:
            self._setup_database()
        else:
            self.logger.info("MySQL integration is disabled")

        self.client = None
        self.group_name = os.getenv("MQTT_GROUP_NAME", "mqtt_framework_group")
        self.loop = asyncio.get_event_loop()

        self.worker_manager = WorkerManager(self.router, self.group_name)

    def _setup_logging(self):
        """Configure logging based on environment variables."""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_format = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format=log_format
        )
        
        self.logger = logging.getLogger("mqtt_framework")
    
    def _setup_database(self):
        """Configure database connection."""
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "3306")
        db_name = os.getenv("DB_NAME", "mqtt_framework")
        db_user = os.getenv("DB_USER", "root")
        db_pass = os.getenv("DB_PASS", "")
        
        conn_str = f"mysql+aiomysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        Model.configure(conn_str)
    
    async def initialize_database(self):
        """Create database tables."""
        if self.mysql_enabled:
            await Model.create_tables()

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        self.logger.info(f"Main client connected with result code {rc}")

        for route in self.router.routes:
            if not route.shared:
                topic = route.get_subscription_topic()
                self.logger.info(f"Main client subscribing to {topic}")
                client.subscribe(topic, route.qos)
                self.logger.info(f"Subscribed to {topic} with QoS {route.qos}")

    def _on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server."""
        self.logger.debug(f"Received message on topic {msg.topic}")
        
        try:
            try:
                payload = json.loads(msg.payload.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = msg.payload
            
            asyncio.run_coroutine_threadsafe(
                self.router.dispatch(msg.topic, payload, client),
                self.loop
            )
            
        except Exception as e:
            self.logger.error(f"Error processing message: {str(e)}")
    
    def connect(self):
        """Connect to the MQTT broker."""
        broker = os.getenv("MQTT_BROKER", "localhost")
        port = int(os.getenv("MQTT_PORT", "1883"))
        client_id = os.getenv("MQTT_CLIENT_ID", f"mqtt-framework-main-{os.getpid()}")
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")
        
        self.client = mqtt_client.Client(client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        if username and password:
            self.client.username_pw_set(username, password)
        
        self.logger.info(f"Connecting main client to {broker}:{port}")
        self.client.connect(broker, port)
        
    def start_workers(self):
        """Start worker processes for shared subscriptions."""
        total_workers = self.router.get_total_workers_needed()
        if total_workers > 0:
            self.logger.info(f"Starting {total_workers} workers for shared subscriptions")
            self.worker_manager.start_workers(total_workers)
        else:
            self.logger.info("No shared routes found, no workers needed")

    def run(self):
        """Run the application."""
        self.start_workers()
        self.client.loop_start()
        
        try:
            self.loop.run_until_complete(self.initialize_database())
            self.logger.info("Application started. Press Ctrl+C to exit.")
            self.logger.info(f"Active workers: {self.worker_manager.get_worker_count()}")
            self.loop.run_forever()
            
        except KeyboardInterrupt:
            self.logger.info("Shutting down...")
            
        finally:
            self.worker_manager.stop_workers()

            self.client.loop_stop()
            self.client.disconnect()
            self.loop.close()