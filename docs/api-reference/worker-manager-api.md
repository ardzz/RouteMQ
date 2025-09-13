# Worker Manager API

Complete API reference for the RouteMQ Worker Manager class and worker process management for horizontal scaling.

## WorkerManager Class

The `WorkerManager` class manages multiple worker processes to enable horizontal scaling of MQTT message processing through shared subscriptions. It automatically distributes workload across multiple processes for high-throughput scenarios.

### Import

```python
from core.worker_manager import WorkerManager
```

### Constructor

```python
WorkerManager(router, group_name=None, router_directory="app.routers")
```

**Parameters:**
- `router` (Router): Router instance containing route definitions
- `group_name` (str, optional): MQTT shared subscription group name. Default: value from `MQTT_GROUP_NAME` env var or "mqtt_framework_group"
- `router_directory` (str): Python module path for dynamic router loading. Default: "app.routers"

**Example:**
```python
from core.router import Router
from core.worker_manager import WorkerManager

# Create router with shared routes
router = Router()
router.on("telemetry/{sensor_id}", TelemetryController.handle_data, 
          shared=True, worker_count=5)

# Create worker manager
worker_manager = WorkerManager(
    router=router,
    group_name="telemetry_workers",
    router_directory="app.routers"
)
```

## Core Methods

### start_workers(num_workers=None)

Start worker processes for handling shared subscriptions.

**Signature:**
```python
def start_workers(num_workers: int = None) -> None
```

**Parameters:**
- `num_workers` (int, optional): Number of workers to start. If None, uses `router.get_total_workers_needed()`

**Example:**
```python
# Start workers automatically based on route configuration
worker_manager.start_workers()

# Start specific number of workers
worker_manager.start_workers(num_workers=8)

# Check if workers are needed first
if worker_manager.get_shared_routes_info():
    worker_manager.start_workers()
```

### stop_workers()

Stop all worker processes gracefully.

**Signature:**
```python
def stop_workers() -> None
```

**Example:**
```python
# Graceful shutdown
worker_manager.stop_workers()

# In application shutdown handler
import atexit
atexit.register(worker_manager.stop_workers)
```

### get_worker_count()

Get the number of currently active worker processes.

**Signature:**
```python
def get_worker_count() -> int
```

**Returns:** int - Number of active workers

**Example:**
```python
active_workers = worker_manager.get_worker_count()
print(f"Currently running {active_workers} workers")

# Health check
if active_workers == 0 and worker_manager.get_shared_routes_info():
    print("Warning: No workers running but shared routes exist")
```

### get_shared_routes_info()

Extract information about routes that require shared subscriptions.

**Signature:**
```python
def get_shared_routes_info() -> List[Dict[str, Any]]
```

**Returns:** List of dictionaries containing shared route information

**Example:**
```python
shared_routes = worker_manager.get_shared_routes_info()
for route_info in shared_routes:
    print(f"Route: {route_info['topic']}")
    print(f"MQTT Topic: {route_info['mqtt_topic']}")
    print(f"QoS: {route_info['qos']}")
    print(f"Worker Count: {route_info['worker_count']}")
```

## Configuration

Worker processes are configured through environment variables:

### MQTT Broker Configuration

```bash
# MQTT broker connection
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password

# Client identification
MQTT_CLIENT_ID=mqtt-worker
MQTT_GROUP_NAME=your_group_name
```

### Example Configuration

```bash
# Production configuration
MQTT_BROKER=mqtt.production.com
MQTT_PORT=8883
MQTT_USERNAME=worker_user
MQTT_PASSWORD=secure_password
MQTT_CLIENT_ID=routemq-worker
MQTT_GROUP_NAME=production_workers
```

## WorkerProcess Class

Individual worker process that handles MQTT subscriptions. This class is used internally by WorkerManager.

### Key Features

- **Isolated Process**: Each worker runs in a separate process for true parallelism
- **Router Loading**: Dynamically loads router configuration from specified directory
- **MQTT Connection**: Maintains its own MQTT client connection
- **Shared Subscriptions**: Uses MQTT shared subscription feature for load balancing
- **Error Handling**: Graceful error handling for message processing failures

### Worker Lifecycle

1. **Router Setup**: Load router configuration from specified directory
2. **MQTT Client Setup**: Create and configure MQTT client with unique client ID
3. **Connection**: Connect to MQTT broker
4. **Subscription**: Subscribe to shared topics for load balancing
5. **Message Processing**: Process incoming messages through router and middleware
6. **Shutdown**: Clean disconnect and resource cleanup

## Usage Patterns

### Basic Usage

```python
from core.router import Router
from core.worker_manager import WorkerManager
from app.controllers.telemetry_controller import TelemetryController

# Define routes with shared subscriptions
router = Router()

# High-volume telemetry data
router.on("sensors/+/temperature", TelemetryController.handle_temperature,
          qos=0, shared=True, worker_count=5)

router.on("sensors/+/humidity", TelemetryController.handle_humidity,
          qos=0, shared=True, worker_count=3)

# Critical commands (not shared)
router.on("devices/+/commands/+", CommandController.handle_command,
          qos=2, shared=False)

# Create and start workers
worker_manager = WorkerManager(router, group_name="sensor_workers")
worker_manager.start_workers()

# Application runs...
# Workers handle shared subscriptions automatically

# Shutdown
worker_manager.stop_workers()
```

### Advanced Configuration

```python
import os
import signal
from core.worker_manager import WorkerManager

class ScalableApplication:
    def __init__(self):
        self.router = self._setup_router()
        self.worker_manager = WorkerManager(
            router=self.router,
            group_name=os.getenv("WORKER_GROUP", "app_workers"),
            router_directory="app.routers"
        )
        self._setup_signal_handlers()
    
    def _setup_router(self):
        # Router configuration loaded from external files
        from core.router_registry import RouterRegistry
        registry = RouterRegistry("app.routers")
        return registry.discover_and_load_routers()
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"Received signal {signum}, shutting down...")
        self.worker_manager.stop_workers()
        exit(0)
    
    def start(self):
        """Start the application."""
        print("Starting scalable MQTT application...")
        
        # Check if workers are needed
        shared_routes = self.worker_manager.get_shared_routes_info()
        if shared_routes:
            print(f"Found {len(shared_routes)} shared routes")
            self.worker_manager.start_workers()
            print(f"Started {self.worker_manager.get_worker_count()} workers")
        else:
            print("No shared routes found, running single-threaded")
        
        # Keep main process alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.worker_manager.stop_workers()

# Usage
app = ScalableApplication()
app.start()
```

### Dynamic Scaling

```python
import asyncio
import time
from core.redis_manager import redis_manager

class DynamicWorkerManager:
    def __init__(self, worker_manager: WorkerManager):
        self.worker_manager = worker_manager
        self.target_workers = 0
        self.monitoring = False
    
    async def start_monitoring(self):
        """Monitor load and scale workers dynamically."""
        self.monitoring = True
        
        while self.monitoring:
            try:
                # Check queue depth or processing load
                load_metrics = await self._get_load_metrics()
                new_target = self._calculate_target_workers(load_metrics)
                
                if new_target != self.target_workers:
                    await self._scale_workers(new_target)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                print(f"Error in worker monitoring: {e}")
                await asyncio.sleep(60)
    
    async def _get_load_metrics(self) -> dict:
        """Get current load metrics from Redis."""
        if not redis_manager.is_enabled():
            return {"queue_depth": 0, "processing_rate": 0}
        
        # Example metrics collection
        queue_depth = await redis_manager.get("metrics:queue_depth") or 0
        processing_rate = await redis_manager.get("metrics:processing_rate") or 0
        
        return {
            "queue_depth": int(queue_depth),
            "processing_rate": float(processing_rate)
        }
    
    def _calculate_target_workers(self, metrics: dict) -> int:
        """Calculate optimal number of workers based on load."""
        queue_depth = metrics["queue_depth"]
        processing_rate = metrics["processing_rate"]
        
        # Simple scaling algorithm
        if queue_depth > 1000:
            return min(10, queue_depth // 100)  # Scale up
        elif queue_depth < 100 and processing_rate < 10:
            return max(1, self.target_workers - 1)  # Scale down
        
        return self.target_workers  # No change
    
    async def _scale_workers(self, target: int):
        """Scale workers to target count."""
        current = self.worker_manager.get_worker_count()
        
        if target > current:
            # Scale up
            additional = target - current
            print(f"Scaling up: adding {additional} workers")
            self.worker_manager.start_workers(additional)
        elif target < current:
            # Scale down (simplified - restart all with new count)
            print(f"Scaling down: restarting with {target} workers")
            self.worker_manager.stop_workers()
            time.sleep(2)  # Brief pause
            self.worker_manager.start_workers(target)
        
        self.target_workers = target
        print(f"Workers scaled to {target}")

# Usage
dynamic_manager = DynamicWorkerManager(worker_manager)
asyncio.create_task(dynamic_manager.start_monitoring())
```

### Health Monitoring

```python
import psutil
import time
from typing import Dict, List

class WorkerHealthMonitor:
    def __init__(self, worker_manager: WorkerManager):
        self.worker_manager = worker_manager
        self.health_data = {}
    
    def get_worker_health(self) -> Dict[str, any]:
        """Get health status of all workers."""
        workers = self.worker_manager.workers
        health_status = {
            "total_workers": len(workers),
            "active_workers": self.worker_manager.get_worker_count(),
            "workers": []
        }
        
        for i, worker in enumerate(workers):
            worker_info = {
                "worker_id": i,
                "pid": worker.pid,
                "is_alive": worker.is_alive(),
                "exit_code": worker.exitcode
            }
            
            # Get process info if alive
            if worker.is_alive():
                try:
                    process = psutil.Process(worker.pid)
                    worker_info.update({
                        "cpu_percent": process.cpu_percent(),
                        "memory_mb": process.memory_info().rss / 1024 / 1024,
                        "create_time": process.create_time(),
                        "status": process.status()
                    })
                except psutil.NoSuchProcess:
                    worker_info["status"] = "not_found"
            
            health_status["workers"].append(worker_info)
        
        return health_status
    
    def restart_unhealthy_workers(self):
        """Restart workers that appear to be unhealthy."""
        health = self.get_worker_health()
        
        for worker_info in health["workers"]:
            if not worker_info["is_alive"] and worker_info["exit_code"] is not None:
                print(f"Worker {worker_info['worker_id']} died with exit code {worker_info['exit_code']}")
                # Could implement restart logic here
    
    async def monitor_health(self, interval: int = 60):
        """Continuously monitor worker health."""
        while True:
            try:
                health = self.get_worker_health()
                await self._log_health_metrics(health)
                self.restart_unhealthy_workers()
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                print(f"Health monitoring error: {e}")
                await asyncio.sleep(interval)
    
    async def _log_health_metrics(self, health: Dict):
        """Log health metrics to Redis or logging system."""
        if redis_manager.is_enabled():
            timestamp = int(time.time())
            key = f"worker_health:{timestamp}"
            await redis_manager.set_json(key, health, ex=3600)

# Usage
health_monitor = WorkerHealthMonitor(worker_manager)
asyncio.create_task(health_monitor.monitor_health())
```

## Best Practices

### 1. Proper Shutdown Handling

```python
import atexit
import signal

# Register shutdown handlers
def cleanup():
    worker_manager.stop_workers()

atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda s, f: cleanup())
signal.signal(signal.SIGINT, lambda s, f: cleanup())
```

### 2. Worker Count Optimization

```python
# Configure worker counts based on route characteristics
router.on("high_volume/logs/+", LogController.handle,
          shared=True, worker_count=8, qos=0)  # Many workers, low QoS

router.on("critical/commands/+", CommandController.handle,
          shared=True, worker_count=2, qos=2)  # Fewer workers, high QoS

router.on("admin/actions/+", AdminController.handle,
          shared=False, qos=1)  # No sharing for admin actions
```

### 3. Resource Management

```python
# Monitor resource usage
def check_system_resources():
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_percent = psutil.virtual_memory().percent
    
    if cpu_percent > 80 or memory_percent > 80:
        print("Warning: High resource usage detected")
        # Consider scaling down workers
    
    return {"cpu": cpu_percent, "memory": memory_percent}
```

### 4. Error Recovery

```python
# Implement worker restart logic
def ensure_workers_running():
    """Ensure workers are running and restart if needed."""
    shared_routes = worker_manager.get_shared_routes_info()
    if shared_routes and worker_manager.get_worker_count() == 0:
        print("No workers running, restarting...")
        worker_manager.start_workers()
```

### 5. Logging and Monitoring

```python
# Configure per-worker logging
import logging
import os

def setup_worker_logging():
    """Setup structured logging for workers."""
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.FileHandler(f'logs/workers.log'),
            logging.StreamHandler()
        ]
    )

# Call before starting workers
setup_worker_logging()
worker_manager.start_workers()
```

## Troubleshooting

### Common Issues

#### Workers Not Starting
```python
# Check if shared routes exist
shared_routes = worker_manager.get_shared_routes_info()
if not shared_routes:
    print("No shared routes found - workers not needed")

# Check MQTT configuration
broker = os.getenv("MQTT_BROKER", "localhost")
port = os.getenv("MQTT_PORT", "1883")
print(f"MQTT Config: {broker}:{port}")
```

#### Workers Dying
```python
# Check worker health
health = health_monitor.get_worker_health()
for worker in health["workers"]:
    if not worker["is_alive"]:
        print(f"Worker {worker['worker_id']} exit code: {worker['exit_code']}")
```

#### Memory Leaks
```python
# Monitor memory usage over time
def log_memory_usage():
    for worker in worker_manager.workers:
        if worker.is_alive():
            process = psutil.Process(worker.pid)
            memory_mb = process.memory_info().rss / 1024 / 1024
            print(f"Worker {worker.pid}: {memory_mb:.1f}MB")
```

The Worker Manager API provides powerful horizontal scaling capabilities for RouteMQ applications, enabling you to handle high-throughput MQTT workloads efficiently across multiple processes.
