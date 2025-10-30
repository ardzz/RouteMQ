import asyncio
import json
import logging
import logging.handlers
import os
import platform
import psutil
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from paho.mqtt import client as mqtt_client

from core.model import Model
from core.router import Router
from core.router_registry import RouterRegistry
from core.worker_manager import WorkerManager
from core.redis_manager import redis_manager


class Application:
    @staticmethod
    def get_version():
        """Get version from pyproject.toml commitizen section."""
        try:
            pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            return data.get("tool", {}).get("commitizen", {}).get("version", "latest")
        except Exception:
            return "latest"

    @staticmethod
    def print_banner():
        """Print the RouteMQ ASCII art banner with system information."""
        version = Application.get_version()

        system_info = platform.system()
        cpu_count = psutil.cpu_count(logical=True)
        memory = psutil.virtual_memory()
        memory_gb = round(memory.total / (1024**3), 1)

        banner = f"""
______            _      ___  ________ 
| ___ \\          | |     |  \\/  |  _  |
| |_/ /___  _   _| |_ ___| .  . | | | |
|    // _ \\| | | | __/ _ \\ |\\/| | | | |
| |\\ \\ (_) | |_| | ||  __/ |  | \\ \\/' /
\\_| \\_\\___/ \\__,_|\\__\\___\\_|  |_/\\_/\\_\\ {version}

Running on {system_info} | CPU: {cpu_count} cores | RAM: {memory_gb} GB
"""
        print(banner)

    def __init__(self, router=None, env_file=".env", router_directory="app.routers"):
        """
        Initialize a new RouteMQ application.

        Args:
            router: A Router instance to use. If None, dynamically loads from router_directory
            env_file: The environment file to load configuration from
            router_directory: Directory containing router modules (default: "app.routers")
        """
        # Print banner first
        self.print_banner()

        load_dotenv(env_file)

        self._setup_logging()

        self.router_directory = router_directory
        self.router = router
        if self.router is None:
            try:
                registry = RouterRegistry(self.router_directory)
                self.router = registry.discover_and_load_routers()
                self.logger.info(f"Router loaded dynamically from {self.router_directory}")
            except Exception as e:
                self.router = Router()
                self.logger.warning(f"Could not load routers dynamically: {str(e)}")
                self.logger.info("Using empty router. Register routes manually.")

        self.mysql_enabled = os.getenv("ENABLE_MYSQL", "true").lower() == "true"
        if self.mysql_enabled:
            self._setup_database()
        else:
            self.logger.info("MySQL integration is disabled")

        self.redis_enabled = os.getenv("ENABLE_REDIS", "false").lower() == "true"
        if self.redis_enabled:
            self.logger.info("Redis integration is enabled")
        else:
            self.logger.info("Redis integration is disabled")

        self.client = None
        self.group_name = os.getenv("MQTT_GROUP_NAME", "mqtt_framework_group")
        self.loop = asyncio.get_event_loop()

        self.worker_manager = WorkerManager(self.router, self.group_name, self.router_directory)

    def _setup_logging(self):
        """Configure logging based on environment variables with file rotation support."""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_format = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"
        log_file = os.getenv("LOG_FILE", "logs/app.log")

        log_rotation_type = os.getenv("LOG_ROTATION_TYPE", "size").lower()  # 'size' or 'time'

        max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10 MB default
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))

        rotation_when = os.getenv("LOG_ROTATION_WHEN", "midnight").lower()  # 'midnight', 'D', 'H', etc.
        rotation_interval = int(os.getenv("LOG_ROTATION_INTERVAL", "1"))

        date_format = os.getenv("LOG_DATE_FORMAT", "%Y-%m-%d")

        handlers = [logging.StreamHandler()]

        if log_to_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                if log_rotation_type == "time":
                    file_handler = logging.handlers.TimedRotatingFileHandler(
                        filename=log_file,
                        when=rotation_when,
                        interval=rotation_interval,
                        backupCount=backup_count,
                        encoding='utf-8'
                    )
                    file_handler.suffix = date_format
                else:
                    file_handler = logging.handlers.RotatingFileHandler(
                        filename=log_file,
                        maxBytes=max_bytes,
                        backupCount=backup_count,
                        encoding='utf-8'
                    )

                file_handler.setFormatter(logging.Formatter(log_format))
                handlers.append(file_handler)

            except Exception as e:
                print(f"Warning: Could not setup file logging: {e}")
                print("Falling back to console logging only")

        logging.basicConfig(
            level=getattr(logging, log_level),
            format=log_format,
            handlers=handlers,
            force=True
        )
        
        self.logger = logging.getLogger("RouteMQ.Application")

        if log_to_file:
            self.logger.info(f"Logging configured - File: {log_file}, Rotation: {log_rotation_type}")
            if log_rotation_type == "size":
                self.logger.info(f"Size rotation - Max: {max_bytes} bytes, Backups: {backup_count}")
            else:
                self.logger.info(f"Time rotation - When: {rotation_when}, Interval: {rotation_interval}, Backups: {backup_count}")
        else:
            self.logger.info("File logging disabled - Console only")

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

    async def initialize_redis(self):
        """Initialize Redis connection."""
        if self.redis_enabled:
            success = await redis_manager.initialize()
            if success:
                self.logger.info("Redis initialized successfully")
            else:
                self.logger.warning("Redis initialization failed")

    async def _initialize_connections(self):
        """Initialize database and Redis connections."""
        await self.initialize_database()
        await self.initialize_redis()

    async def _cleanup_connections(self):
        """Cleanup database and Redis connections."""
        if self.redis_enabled:
            await redis_manager.disconnect()
        if self.mysql_enabled:
            await Model.cleanup()

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
        
        self.client = mqtt_client.Client(client_id=client_id)
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
            self.loop.run_until_complete(self.initialize_redis())
            self.logger.info("Application started. Press Ctrl+C to exit.")
            self.logger.info(f"Active workers: {self.worker_manager.get_worker_count()}")
            self.loop.run_forever()
            
        except KeyboardInterrupt:
            self.logger.info("Shutting down...")
            
        finally:
            self.worker_manager.stop_workers()

            if self.redis_enabled:
                self.loop.run_until_complete(redis_manager.disconnect())

            if self.mysql_enabled:
                self.loop.run_until_complete(Model.cleanup())

            self.client.loop_stop()
            self.client.disconnect()
            self.loop.close()