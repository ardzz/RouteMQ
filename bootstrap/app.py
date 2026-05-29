import asyncio
import logging
import os
import platform
import psutil
import signal
from collections.abc import Callable
from importlib import import_module
from importlib.util import find_spec
from typing import Any

from dotenv import load_dotenv

from routemq.health import HealthServer, HealthStatus, health_server_from_env
from routemq.logging_config import configure_logging, json_logging_enabled
from routemq.metrics.exposition import negotiate_content_type, render as render_stdlib_metrics
from routemq.metrics.hooks import DefaultHooksHandle, install_default_hooks
from routemq.metrics.prometheus import PrometheusAdapter
from routemq.metrics.registry import MetricsRegistry
from routemq.model import Model
from routemq.router import Router
from routemq.router_registry import RouterRegistry
from routemq.settings import (
    MetricsHttpSettings,
    load_database_pool_settings,
    load_health_http_settings,
    load_metrics_http_settings,
)
from routemq.mqtt_utils import (
    connect_mqtt_client_with_retries,
    create_mqtt_client,
    get_main_client_id,
    get_mqtt_connection_config,
    get_mqtt_group_name,
    parse_mqtt_payload,
)
from routemq.worker_manager import WorkerManager
from routemq.redis_manager import redis_manager
from routemq.tsdb.tsdb_manager import tsdb_manager

observability = import_module('routemq.observability')


class Application:
    @staticmethod
    def get_version() -> str:
        """Get installed package version, with src-checkout fallback."""
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version('routemq')
        except PackageNotFoundError:
            # Audit Accept: source checkout fallback; see docs/monitoring/error-handling-audit.md.
            return '0.0.0+dev'

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

    def __init__(
        self,
        router=None,
        env_file='.env',
        router_directory='app.routers',
        show_banner: bool = True,
        log_to_console: bool = True,
    ):
        """
        Initialize a new RouteMQ application.

        Args:
            router: A Router instance to use. If None, dynamically loads from router_directory
            env_file: The environment file to load configuration from
            router_directory: Directory containing router modules (default: "app.routers")
            show_banner: Whether to print the standard RouteMQ startup banner
            log_to_console: Whether startup logging should include a console handler
        """
        load_dotenv(env_file)

        self._setup_logging(log_to_console=log_to_console)

        self.metrics_settings = load_metrics_http_settings()
        self.metrics_registry = MetricsRegistry()
        self.metrics_hooks_handle = install_default_hooks(
            self.metrics_registry,
            namespace=self.metrics_settings.namespace,
            histogram_buckets=self.metrics_settings.histogram_buckets,
        )

        if show_banner and not json_logging_enabled():
            self.print_banner()

        self.router_directory = router_directory
        self.router: Any = router
        if self.router is None:
            try:
                registry = RouterRegistry(self.router_directory)
                self.router = registry.discover_and_load_routers()
                self.logger.info(f'Router loaded dynamically from {self.router_directory}')
            except Exception as e:
                self.router = Router()
                # Audit Accept: router auto-discovery fallback keeps manual router registration usable.
                self.logger.warning(f'Could not load routers dynamically: {str(e)}')
                self.logger.info('Using empty router. Register routes manually.')

        self.mysql_enabled = os.getenv('ENABLE_MYSQL', 'true').lower() == 'true'
        if self.mysql_enabled:
            self._setup_database()
        else:
            self.logger.info('MySQL integration is disabled')

        self.redis_enabled = os.getenv('ENABLE_REDIS', 'false').lower() == 'true'
        if self.redis_enabled:
            self.logger.info('Redis integration is enabled')
        else:
            self.logger.info('Redis integration is disabled')

        self.tsdb_enabled = os.getenv('ENABLE_TSDB', 'false').lower() == 'true'
        if self.tsdb_enabled:
            self.logger.info('TSDB integration is enabled')
        else:
            self.logger.info('TSDB integration is disabled')

        self.client: Any = None
        self.group_name = get_mqtt_group_name()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.worker_manager = WorkerManager(self.router, self.group_name, self.router_directory)
        self.health_status = HealthStatus()
        self.health_server: HealthServer | None = None
        self.metrics_health_server: HealthServer | None = None
        self._setup_metrics()
        self._shutdown_requested = False

    def _setup_logging(self, log_to_console: bool = True):
        """Configure logging based on environment variables."""
        settings = configure_logging(log_to_console=log_to_console)
        self.logger = logging.getLogger('RouteMQ.Application')
        self.logger.info(
            'Logging configured',
            extra={
                'formatter': settings.formatter,
                'field_profile': settings.field_profile,
                'lifecycle_events': settings.lifecycle_events,
            },
        )

    def _setup_database(self):
        """Configure database connection."""
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '3306')
        db_name = os.getenv('DB_NAME', 'mqtt_framework')
        db_user = os.getenv('DB_USER', 'root')
        db_pass = os.getenv('DB_PASS', '')
        pool_settings = load_database_pool_settings()

        conn_str = f'mysql+aiomysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'
        Model.configure(
            conn_str,
            pool_size=pool_settings.pool_size,
            max_overflow=pool_settings.max_overflow,
            pool_timeout=pool_settings.pool_timeout,
            pool_recycle=pool_settings.pool_recycle,
            pool_pre_ping=pool_settings.pool_pre_ping,
            pool_use_lifo=pool_settings.pool_use_lifo,
            pool_class=pool_settings.pool_class,
        )

    def _setup_metrics(self) -> None:
        """Configure HealthServer instances that can expose RouteMQ metrics."""

        self.metrics_health_server = None
        renderer = self._build_metrics_renderer(self.metrics_settings) if self.metrics_settings.enabled else None
        if self.metrics_settings.enabled and self.metrics_settings.separate:
            self.health_server = health_server_from_env(self.health_status)
            self.metrics_health_server = HealthServer(
                self.health_status,
                host=self.metrics_settings.host,
                port=self.metrics_settings.port,
                metrics_renderer=renderer,
                metrics_path=self.metrics_settings.path,
            )
            return

        self.health_server = health_server_from_env(
            self.health_status,
            metrics_renderer=renderer,
            metrics_path=self.metrics_settings.path,
        )
        if self.health_server is None and renderer is not None:
            health_settings = load_health_http_settings()
            self.health_server = HealthServer(
                self.health_status,
                host=health_settings.host,
                port=health_settings.port,
                metrics_renderer=renderer,
                metrics_path=self.metrics_settings.path,
            )

    def _build_metrics_renderer(self, settings: MetricsHttpSettings) -> Callable[[str | None], tuple[str, bytes]]:
        default_labels = dict(settings.default_labels)
        prometheus_adapter = PrometheusAdapter(namespace=settings.namespace) if find_spec('prometheus_client') else None

        def render(accept: str | None) -> tuple[str, bytes]:
            content_type = negotiate_content_type(accept)
            stdlib_body = render_stdlib_metrics(
                self.metrics_registry,
                content_type=content_type,
                static_labels=default_labels,
            )
            if prometheus_adapter is None:
                return content_type, stdlib_body
            prometheus_content_type, prometheus_body = prometheus_adapter.render(accept)
            return prometheus_content_type, _combine_metrics_payloads(
                prometheus_body,
                stdlib_body,
                openmetrics=prometheus_content_type.startswith('application/openmetrics-text'),
            )

        return render

    async def initialize_database(self):
        """Create database tables."""
        if self.mysql_enabled:
            await Model.create_tables()

    async def initialize_redis(self):
        """Initialize Redis connection."""
        if self.redis_enabled:
            success = await redis_manager.initialize()
            if success:
                self.logger.info('Redis initialized successfully')
            else:
                self.logger.warning('Redis initialization failed')

    async def initialize_tsdb(self):
        """Initialize TSDB connection."""
        if self.tsdb_enabled:
            success = await tsdb_manager.initialize()
            if success:
                self.logger.info('TSDB initialized successfully')
            else:
                self.logger.warning('TSDB initialization failed')

    async def _initialize_connections(self):
        """Initialize database, Redis, and TSDB connections."""
        await self.initialize_database()
        await self.initialize_redis()
        await self.initialize_tsdb()

    async def _cleanup_connections(self):
        """Cleanup database, Redis, and TSDB connections."""
        if self.tsdb_enabled:
            await tsdb_manager.disconnect()
        if self.redis_enabled:
            await redis_manager.disconnect()
        if self.mysql_enabled:
            await Model.cleanup()

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        self.logger.info(f'Main client connected with result code {rc}')
        if hasattr(self, 'health_status'):
            self.health_status.mqtt_connected = rc == 0

        for route in self.router.routes:
            if not route.shared:
                topic = route.get_subscription_topic()
                self.logger.info(f'Main client subscribing to {topic}')
                client.subscribe(topic, route.qos)
                self.logger.info(f'Subscribed to {topic} with QoS {route.qos}')

    def _on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server."""
        self.logger.debug(f'Received message on topic {msg.topic}')

        try:
            payload = parse_mqtt_payload(msg.payload)
            context = {
                'source': 'mqtt',
                'mqtt_topic': msg.topic,
                'process': 'main',
            }
            coro = self._dispatch_mqtt_message(msg.topic, payload, client, context)
            try:
                asyncio.run_coroutine_threadsafe(coro, self.loop)
            except Exception:
                coro.close()
                raise

        except Exception as e:
            topic = getattr(msg, 'topic', 'unknown')
            observability.lifecycle(
                'mqtt.message.failed',
                {'process': 'main', 'error': e.__class__.__name__, 'mqtt_topic': topic},
            )
            self.logger.error(
                f'Error processing message on topic {topic}: {str(e)}',
                exc_info=True,
                extra={'mqtt_topic': topic, 'error': e.__class__.__name__},
            )

    async def _dispatch_mqtt_message(self, topic: str, payload: Any, client: Any, context: dict[str, Any]) -> None:
        """Restore MQTT correlation context inside the application event loop."""
        token = observability.set_context(context)
        try:
            span_attributes = {
                'messaging.system': 'mqtt',
                'messaging.destination': topic,
                'routemq.process.role': 'main',
            }
            with observability.start_span('mqtt.receive', span_attributes, kind='consumer'):
                observability.lifecycle('mqtt.message.received', {'process': 'main'})
                await self.router.dispatch(topic, payload, client)
                observability.lifecycle('mqtt.message.succeeded', {'process': 'main'})
        except Exception as exc:
            observability.lifecycle('mqtt.message.failed', {'process': 'main', 'error': exc.__class__.__name__})
            raise
        finally:
            observability.reset_context(token)

    def connect(self):
        """Connect to the MQTT broker."""
        config = get_mqtt_connection_config()
        client_id = get_main_client_id()

        self.client = create_mqtt_client(
            client_id,
            on_connect=self._on_connect,
            on_message=self._on_message,
            on_disconnect=self._on_disconnect,
            username=config.username,
            password=config.password,
        )

        self.logger.info(f'Connecting main client to {config.broker}:{config.port}')
        connect_mqtt_client_with_retries(self.client, config.broker, config.port, process='main')

    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.logger.info(f'Main client disconnected with result code {rc}')
        if hasattr(self, 'health_status'):
            self.health_status.mqtt_connected = False

    def _request_shutdown(self, signum: int | None = None, frame: Any = None) -> None:
        """Request a graceful application shutdown from a signal handler."""
        signal_name = signal.Signals(signum).name if signum is not None else 'internal'
        self.logger.info(f'Received {signal_name}; requesting graceful shutdown...')
        self._shutdown_requested = True
        self.health_status.shutting_down = True
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    def _install_signal_handlers(self) -> dict[int, Any]:
        """Install SIGTERM handler where the platform/thread allows it."""
        previous_handlers: dict[int, Any] = {}
        try:
            previous_handlers[signal.SIGTERM] = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, self._request_shutdown)
        except (ValueError, RuntimeError):
            # Audit Accept: signal handlers can only be installed on the main thread.
            self.logger.debug('SIGTERM handler not installed outside the main thread')
        return previous_handlers

    def _restore_signal_handlers(self, previous_handlers: dict[int, Any]) -> None:
        for signum, handler in previous_handlers.items():
            try:
                signal.signal(signum, handler)
            except (ValueError, RuntimeError):
                # Audit Accept: best-effort signal restore during shutdown; see audit doc.
                pass

    def start_workers(self):
        """Start worker processes for shared subscriptions."""
        total_workers = self.router.get_total_workers_needed()
        if total_workers > 0:
            self.logger.info(f'Starting {total_workers} workers for shared subscriptions')
            self.worker_manager.start_workers(total_workers)
        else:
            self.logger.info('No shared routes found, no workers needed')

    def run(self):
        """Run the application."""
        if not hasattr(self, 'health_status'):
            self.health_status = HealthStatus()
        if not hasattr(self, 'health_server'):
            self.health_server = None
        if not hasattr(self, 'metrics_health_server'):
            self.metrics_health_server = None
        if not hasattr(self, '_shutdown_requested'):
            self._shutdown_requested = False
        previous_handlers = self._install_signal_handlers()
        self.start_workers()
        if self.health_server is not None:
            self.health_server.start()
        if self.metrics_health_server is not None:
            self.metrics_health_server.start()
        if self.client is not None:
            self.client.loop_start()

        try:
            self.loop.run_until_complete(self.initialize_database())
            self.loop.run_until_complete(self.initialize_redis())
            self.loop.run_until_complete(self.initialize_tsdb())
            self.health_status.startup_complete = True
            self.logger.info('Application started. Press Ctrl+C to exit.')
            self.logger.info(f'Active workers: {self.worker_manager.get_worker_count()}')
            self.loop.run_forever()

        except KeyboardInterrupt:
            # Audit Accept: Ctrl+C is the expected graceful shutdown path.
            self.logger.info('Shutting down...')
            self.health_status.shutting_down = True

        finally:
            self.logger.info('Application cleanup started')
            self.health_status.shutting_down = True
            self.worker_manager.stop_workers()
            if self.tsdb_enabled:
                self.loop.run_until_complete(tsdb_manager.disconnect())
            if self.redis_enabled:
                self.loop.run_until_complete(redis_manager.disconnect())
            if self.mysql_enabled:
                self.loop.run_until_complete(Model.cleanup())
            if self.health_server is not None:
                self.health_server.stop()
            if self.metrics_health_server is not None:
                self.metrics_health_server.stop()
            if self.client is not None:
                self.client.loop_stop()
                self.client.disconnect()
            self.health_status.alive = False
            self._restore_signal_handlers(previous_handlers)
            self.loop.close()
            self.logger.info('Application cleanup completed')


def _combine_metrics_payloads(prometheus_body: bytes, stdlib_body: bytes, *, openmetrics: bool) -> bytes:
    if not openmetrics:
        separator = b'' if prometheus_body.endswith(b'\n') else b'\n'
        return prometheus_body + separator + stdlib_body
    parts = [_without_openmetrics_eof(prometheus_body), _without_openmetrics_eof(stdlib_body)]
    combined = b''
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        combined += part if part.endswith(b'\n') else part + b'\n'
    return combined + b'# EOF\n'


def _without_openmetrics_eof(body: bytes) -> bytes:
    marker = b'# EOF\n'
    return body[: -len(marker)] if body.endswith(marker) else body
