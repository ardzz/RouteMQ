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

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
""")
        print("Created default .env file")
    else:
        print(".env file already exists")

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
    middleware_path = "app/middleware/logging_middleware.py"
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

    router_path = "app/routers/device.py"
    if not os.path.exists(router_path):
        with open(router_path, "w") as f:
            f.write("""from core.router import Router
from app.controllers.example_controller import ExampleController
from app.middleware.logging_middleware import LoggingMiddleware

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

def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="RouteMQ - MQTT routing framework")
    parser.add_argument('--init', action='store_true', help="Initialize a new RouteMQ project")
    parser.add_argument('--run', action='store_true', help="Run the MQTT application")

    args = parser.parse_args()

    if args.init:
        create_env_file()
        setup_example()
        print("RouteMQ project initialized successfully!")
        return

    if args.run or not sys.argv[1:]:
        create_env_file()
        app = create_app()
        app.connect()
        app.run()

if __name__ == "__main__":
    main()
