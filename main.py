#!/usr/bin/env python3
"""
RouteMQ - A flexible MQTT routing framework with middleware support
"""
import argparse
import os
import sys

from bootstrap.app import Application


def create_app(router=None, env_file=".env"):
    """Create and return a new application instance."""
    return Application(router=router, env_file=env_file)

def create_env_file():
    """Create a default .env file if it doesn't exist."""
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
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

# Queue Configuration
QUEUE_CONNECTION=redis

# Timezone Configuration
TIMEZONE=Asia/Jakarta

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
""")
        print("Created default .env file")

def setup_example():
    """Setup example files for a new project."""
    os.makedirs("app/controllers", exist_ok=True)
    os.makedirs("app/middleware", exist_ok=True)
    os.makedirs("app/models", exist_ok=True)
    os.makedirs("app/routers", exist_ok=True)

    controller_path = "app/controllers/example_controller.py"
    if not os.path.exists(controller_path):
        with open(controller_path, "w") as f:
            f.write("""from core.controller import Controller

class ExampleController(Controller):
    @staticmethod
    async def handle_message(device_id: str, payload, client):
        print(f"Received message for device {device_id}")
        print(f"Payload: {payload}")
        # Process the message here
        return {"status": "success", "device_id": device_id}
""")

    # Create example middleware
    middleware_path = "app/middleware/example_middleware.py"
    if not os.path.exists(middleware_path):
        with open(middleware_path, "w") as f:
            f.write("""from core.middleware import Middleware
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

    router_path = "app/routers/example_device.py"
    if not os.path.exists(router_path):
        with open(router_path, "w") as f:
            f.write("""from core.router import Router
from app.controllers.example_controller import ExampleController
from app.middleware.example_middleware import LoggingMiddleware

router = Router()

# Define routes using the with syntax for better readability
with router.group(prefix="devices") as devices:
    # Apply logging middleware to this route
    devices.on("message/{device_id}", ExampleController.handle_message, 
              middleware=[LoggingMiddleware()], qos=1)
""")

    init_dirs = ["app", "app/controllers", "app/middleware", "app/models", "app/routers"]
    for dir_path in init_dirs:
        init_file = f"{dir_path}/__init__.py"
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("# This file marks the directory as a Python package\n")

    print("Example files created successfully!")

def tinker():
    """Start the interactive REPL environment for testing ORM and queries."""
    from core.tinker import run_tinker
    run_tinker()

def queue_work(queue="default", connection=None, max_jobs=None, max_time=None,
               sleep=3, max_tries=None, timeout=60):
    """Start the queue worker to process background jobs."""
    import asyncio
    from bootstrap.app import Application
    from core.queue.queue_worker import QueueWorker

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

            print(f"Starting queue worker for queue: {queue}")
            print(f"Connection: {connection or 'default'}")
            print(f"Sleep when idle: {sleep}s")
            print(f"Press Ctrl+C to stop gracefully\n")

            await worker.work()

        finally:
            # Cleanup connections
            await app._cleanup_connections()

    # Run the worker
    asyncio.run(run_worker())

def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="RouteMQ - MQTT routing framework")
    parser.add_argument('--init', action='store_true', help="Initialize a new RouteMQ project")
    parser.add_argument('--run', action='store_true', help="Run the MQTT application")
    parser.add_argument('--tinker', action='store_true', help="Start interactive REPL for testing ORM and queries")
    parser.add_argument('--queue-work', action='store_true', help="Start queue worker to process background jobs")
    parser.add_argument('--queue', type=str, default="default", help="The queue to process (default: default)")
    parser.add_argument('--connection', type=str, help="Queue connection to use (redis or database)")
    parser.add_argument('--max-jobs', type=int, help="Maximum number of jobs to process")
    parser.add_argument('--max-time', type=int, help="Maximum time in seconds to run")
    parser.add_argument('--sleep', type=int, default=3, help="Seconds to sleep when no job is available (default: 3)")
    parser.add_argument('--max-tries', type=int, help="Maximum number of times to attempt a job")
    parser.add_argument('--timeout', type=int, default=60, help="Maximum seconds a job can run (default: 60)")

    args = parser.parse_args()

    if args.init:
        create_env_file()
        setup_example()
        print("RouteMQ project initialized successfully!")
        return

    if args.tinker:
        tinker()
        return

    if args.queue_work:
        queue_work(
            queue=args.queue,
            connection=args.connection,
            max_jobs=args.max_jobs,
            max_time=args.max_time,
            sleep=args.sleep,
            max_tries=args.max_tries,
            timeout=args.timeout,
        )
        return

    if args.run or not sys.argv[1:]:
        create_env_file()
        app = create_app()
        app.connect()
        app.run()

if __name__ == "__main__":
    main()
