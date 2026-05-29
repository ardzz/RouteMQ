#!/usr/bin/env python3
"""
RouteMQ - A flexible MQTT routing framework with middleware support
"""

import argparse
import logging
import os
import sys

from bootstrap.app import Application
from routemq.logging_config import json_logging_enabled
from routemq.mqtt_utils import is_network_startup_error


logger = logging.getLogger('RouteMQ.CLI')


def create_app(router=None, env_file='.env'):
    """Create and return a new application instance."""
    return Application(router=router, env_file=env_file)


def create_env_file():
    """Create a default .env file if it doesn't exist."""
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write("""# MQTT Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_GROUP_NAME=mqtt_framework_group

# Database Configuration
ENABLE_MYSQL=false
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mqtt_framework
DB_USER=root
DB_PASS=

# Redis Configuration
ENABLE_REDIS=false

# TSDB (ClickHouse) Configuration
ENABLE_TSDB=false
TSDB_HOST=localhost
TSDB_PORT=8123
TSDB_DATABASE=default
TSDB_USER=default
TSDB_PASSWORD=

# Queue Configuration
QUEUE_CONNECTION=redis

# Timezone Configuration
TIMEZONE=Asia/Jakarta

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMATTER=json
LOG_FIELD_PROFILE=otel
LOG_TO_CONSOLE=true
LOG_STREAM=stdout
LOG_TO_FILE=false
LOG_INCLUDE_CONTEXT=true
LOG_LIFECYCLE_EVENTS=true
LOG_LIFECYCLE_LEVEL=INFO
""")
        if not json_logging_enabled():
            print('Created default .env file', file=sys.stderr)


def setup_example():
    """Setup example files for a new project."""
    os.makedirs('app/controllers', exist_ok=True)
    os.makedirs('app/middleware', exist_ok=True)
    os.makedirs('app/models', exist_ok=True)
    os.makedirs('app/routers', exist_ok=True)

    controller_path = 'app/controllers/example_controller.py'
    if not os.path.exists(controller_path):
        with open(controller_path, 'w') as f:
            f.write("""from routemq.controller import Controller

class ExampleController(Controller):
    @staticmethod
    async def handle_message(device_id: str, payload, client):
        print(f"Received message for device {device_id}")
        print(f"Payload: {payload}")
        # Process the message here
        return {"status": "success", "device_id": device_id}
""")

    # Create example middleware
    middleware_path = 'app/middleware/example_middleware.py'
    if not os.path.exists(middleware_path):
        with open(middleware_path, 'w') as f:
            f.write("""from routemq.middleware import Middleware
from typing import Dict, Any, Callable, Awaitable
import time


class LoggingMiddleware(Middleware):
    \"\"\"Example middleware that logs request information and timing.\"\"\"

    async def handle(self, context: Dict[str, Any], next_handler: Callable[[Dict[str, Any]], Awaitable[Any]]) -> Any:
        \"\"\"Log request details and execution time.\"\"\"
        topic = context.get('topic', 'unknown')
        client_id = context.get('client', {})._client_id if 'client' in context else 'unknown'
        device_id = context.get('params', {}).get('device_id', 'unknown')
        
        # Log incoming request
        self.logger.info(f"[INCOMING] Topic: {topic}, Client: {client_id}")
        
        # Record start time
        start_time = time.time()
        
        try:
            # Call the next handler in the chain
            result = await next_handler(context)
            
            # Calculate execution time
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Log successful completion
            self.logger.info(f"[COMPLETED] Topic: {topic}, Execution time: {execution_time:.2f}ms")
            
            return result
            
        except Exception as e:
            # Log any errors that occur
            execution_time = (time.time() - start_time) * 1000
            self.logger.error(f"[ERROR] Topic: {topic}, Error: {str(e)}, Execution time: {execution_time:.2f}ms")
            raise
""")

    router_path = 'app/routers/example_device.py'
    if not os.path.exists(router_path):
        with open(router_path, 'w') as f:
            f.write("""from routemq.router import Router
from app.controllers.example_controller import ExampleController
from app.middleware.example_middleware import LoggingMiddleware

router = Router()

# Define routes using the with syntax for better readability
with router.group(prefix="devices") as devices:
    # Apply logging middleware to this route
    devices.on("message/{device_id}", ExampleController.handle_message, 
              middleware=[LoggingMiddleware()], qos=1)
""")

    init_dirs = ['app', 'app/controllers', 'app/middleware', 'app/models', 'app/routers']
    for dir_path in init_dirs:
        init_file = f'{dir_path}/__init__.py'
        if not os.path.exists(init_file):
            with open(init_file, 'w') as f:
                f.write('# This file marks the directory as a Python package\n')

    print('Example files created successfully!')


def _cmd_new(
    name: str,
    *,
    yes: bool = False,
    with_mysql: bool = False,
    with_redis: bool = False,
    with_queue: bool = False,
    with_docker: bool = False,
    package_manager: str = 'uv',
    no_input: bool = False,
) -> int:
    """Scaffold a new RouteMQ project."""
    from routemq.scaffold import run_scaffolder

    if name == '.':
        return run_scaffolder(
            '.',
            yes=True,
            with_mysql=False,
            with_redis=False,
            with_queue=False,
            with_docker=False,
            package_manager=package_manager,
            no_input=True,
        )

    return run_scaffolder(
        name,
        yes=yes,
        with_mysql=with_mysql,
        with_redis=with_redis,
        with_queue=with_queue,
        with_docker=with_docker,
        package_manager=package_manager,
        no_input=no_input,
    )


def _cmd_run() -> None:
    """Run the MQTT application."""
    create_env_file()
    app = create_app()
    try:
        app.connect()
    except OSError as exc:
        if not is_network_startup_error(exc):
            raise
        broker = os.getenv('MQTT_BROKER', 'localhost')
        port = os.getenv('MQTT_PORT', '1883')
        message = (
            f'Error: Could not connect to MQTT broker at {broker}:{port} ({exc}). '
            'Please verify the broker is running and the address/port are correct.'
        )
        if json_logging_enabled():
            logger.error(message, extra={'broker': broker, 'port': port, 'error': exc.__class__.__name__})
        else:
            print(message, file=sys.stderr)
        raise SystemExit(1)
    app.run()


def _cmd_tinker() -> None:
    """Start the interactive REPL environment for testing ORM and queries."""
    from routemq.tinker import run_tinker

    run_tinker()


def tinker() -> None:
    """Backward-compatible wrapper for the tinker command handler."""
    _cmd_tinker()


def _cmd_queue_work(
    queue='default', connection=None, max_jobs=None, max_time=None, sleep=3, max_tries=None, timeout=60
) -> None:
    """Start the queue worker to process background jobs."""
    import asyncio
    from routemq.queue.queue_worker import QueueWorker

    # Initialize the application to setup database/redis connections
    create_env_file()
    app = create_app()

    async def run_worker():
        """Run the queue worker with proper initialization and cleanup."""
        # Initialize connections
        await app._initialize_connections()

        try:
            # Create and start the worker
            worker = QueueWorker(
                queue_name=queue,
                connection=connection,
                max_jobs=max_jobs,
                max_time=max_time,
                sleep=sleep,
                max_tries=max_tries,
                timeout=timeout,
            )

            logger.info(
                'Starting queue worker',
                extra={'queue': queue, 'connection': connection or 'default', 'sleep': sleep},
            )

            await worker.work()

        finally:
            # Cleanup connections
            await app._cleanup_connections()

    # Run the worker
    asyncio.run(run_worker())


def queue_work(
    queue='default', connection=None, max_jobs=None, max_time=None, sleep=3, max_tries=None, timeout=60
) -> None:
    """Backward-compatible wrapper for the queue-work command handler."""
    _cmd_queue_work(
        queue=queue,
        connection=connection,
        max_jobs=max_jobs,
        max_time=max_time,
        sleep=sleep,
        max_tries=max_tries,
        timeout=timeout,
    )


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(prog='routemq', description='RouteMQ - MQTT routing framework')
    parser.add_argument('--init', action='store_true', help='(deprecated alias for `routemq new .`)')
    parser.add_argument('--run', action='store_true', help='(deprecated alias for `routemq run`)')
    parser.add_argument('--tinker', action='store_true', help='(deprecated alias for `routemq tinker`)')
    parser.add_argument('--queue-work', action='store_true', help='(deprecated alias for `routemq queue-work`)')
    parser.add_argument('--queue', type=str, default='default', help='The queue to process (default: default)')
    parser.add_argument('--connection', type=str, help='Queue connection to use (redis or database)')
    parser.add_argument('--max-jobs', type=int, help='Maximum number of jobs to process')
    parser.add_argument('--max-time', type=int, help='Maximum time in seconds to run')
    parser.add_argument('--sleep', type=int, default=3, help='Seconds to sleep when no job is available (default: 3)')
    parser.add_argument('--max-tries', type=int, help='Maximum number of times to attempt a job')
    parser.add_argument('--timeout', type=int, default=60, help='Maximum seconds a job can run (default: 60)')

    sub = parser.add_subparsers(dest='command', required=False, metavar='COMMAND')

    new_p = sub.add_parser('new', help='Scaffold a new RouteMQ project')
    new_p.add_argument('name', nargs='?', default='.', help='Project directory name (default: current dir)')
    new_p.add_argument('--yes', action='store_true', help='Accept defaults')
    new_p.add_argument('--with-mysql', action='store_true')
    new_p.add_argument('--with-redis', action='store_true')
    new_p.add_argument('--with-queue', action='store_true')
    new_p.add_argument('--with-docker', action='store_true')
    new_p.add_argument('--package-manager', choices=['uv', 'pip'], default='uv')
    new_p.add_argument('--no-input', action='store_true', help='Forbid prompts')

    sub.add_parser('run', help='Run the MQTT application')
    sub.add_parser('tinker', help='Interactive REPL for ORM and queries')

    qw_p = sub.add_parser('queue-work', help='Run a queue worker')
    qw_p.add_argument('--queue', type=str, default='default', help='The queue to process (default: default)')
    qw_p.add_argument('--connection', type=str, help='Queue connection to use (redis or database)')
    qw_p.add_argument('--max-jobs', type=int, help='Maximum number of jobs to process')
    qw_p.add_argument('--max-time', type=int, help='Maximum time in seconds to run')
    qw_p.add_argument('--sleep', type=int, default=3, help='Seconds to sleep when no job is available (default: 3)')
    qw_p.add_argument('--max-tries', type=int, help='Maximum number of times to attempt a job')
    qw_p.add_argument('--timeout', type=int, default=60, help='Maximum seconds a job can run (default: 60)')

    args = parser.parse_args()

    effective_command = args.command
    if effective_command is None:
        if args.init:
            effective_command = 'new'
            args.name = '.'
        elif args.queue_work:
            effective_command = 'queue-work'
        elif args.tinker:
            effective_command = 'tinker'
        else:
            effective_command = 'run'

    if effective_command == 'new':
        rc = _cmd_new(
            name=getattr(args, 'name', '.'),
            yes=getattr(args, 'yes', False),
            with_mysql=getattr(args, 'with_mysql', False),
            with_redis=getattr(args, 'with_redis', False),
            with_queue=getattr(args, 'with_queue', False),
            with_docker=getattr(args, 'with_docker', False),
            package_manager=getattr(args, 'package_manager', 'uv'),
            no_input=getattr(args, 'no_input', False),
        )
        if rc:
            raise SystemExit(rc)
        return

    if effective_command == 'run':
        _cmd_run()
        return

    if effective_command == 'tinker':
        tinker()
        return

    if effective_command == 'queue-work':
        queue_work(
            queue=args.queue,
            connection=args.connection,
            max_jobs=args.max_jobs,
            max_time=args.max_time,
            sleep=args.sleep,
            max_tries=args.max_tries,
            timeout=args.timeout,
        )


if __name__ == '__main__':
    main()
