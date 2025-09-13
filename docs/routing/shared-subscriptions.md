# Shared Subscriptions

Scale your RouteMQ application horizontally using MQTT shared subscriptions and worker processes to handle high-throughput message processing.

## Overview

Shared subscriptions enable multiple worker processes to subscribe to the same MQTT topic, with the broker distributing messages across workers for load balancing:

- **Horizontal scaling**: Add more workers to handle increased load
- **Load distribution**: MQTT broker distributes messages across workers
- **High availability**: If one worker fails, others continue processing
- **Per-route configuration**: Different routes can have different worker counts

## Basic Shared Subscription Usage

### Enabling Shared Subscriptions

```python
from core.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()

# Regular subscription (single instance)
router.on("alerts/{device_id}", SensorController.handle_alert)

# Shared subscription with multiple workers
router.on("sensors/{device_id}/data", 
          SensorController.process_data,
          shared=True,           # Enable shared subscription
          worker_count=3)        # Use 3 workers for this route

# High-throughput route with many workers
router.on("telemetry/bulk", 
          SensorController.process_bulk,
          shared=True,
          worker_count=8,
          qos=1)
```

### How Shared Subscriptions Work

```
┌─────────────────┐    ┌─────────────────┐
│   MQTT Broker   │    │  Shared Group   │
│                 │    │  "workers"      │
│ Topic:          │    │                 │
│ sensors/+/data  │───▶│  ┌──────────┐   │
│                 │    │  │ Worker 1 │   │
│ Messages:       │    │  └──────────┘   │
│ [Msg1, Msg2,    │    │  ┌──────────┐   │
│  Msg3, Msg4,    │    │  │ Worker 2 │   │
│  Msg5, Msg6]    │    │  └──────────┘   │
│                 │    │  ┌──────────┐   │
│                 │    │  │ Worker 3 │   │
│                 │    │  └──────────┘   │
└─────────────────┘    └─────────────────┘
        │                       │
        │              Load Balancing:
        │              Worker 1: Msg1, Msg4
        │              Worker 2: Msg2, Msg5  
        │              Worker 3: Msg3, Msg6
        ▼
  Messages distributed
  across workers using
  broker's algorithm
```

## Worker Management

### Starting Workers

```python
from bootstrap.app import Application

# Create application
app = Application()

# Start worker processes for shared subscriptions
app.worker_manager.start_workers()

# Or specify custom worker count
app.worker_manager.start_workers(num_workers=5)
```

### Worker Configuration

```python
import os
from core.worker_manager import WorkerManager

# Configure worker manager
worker_manager = WorkerManager(
    router=main_router,
    group_name=os.getenv("MQTT_GROUP_NAME", "production_workers"),
    router_directory="app.routers"
)

# Get shared routes configuration
shared_routes = worker_manager.get_shared_routes_info()
print(f"Found {len(shared_routes)} shared routes")

# Start workers
worker_manager.start_workers()
```

### Environment Variables

```bash
# .env configuration
MQTT_GROUP_NAME=production_workers
WORKER_COUNT=4
MQTT_BROKER=mqtt.example.com
MQTT_PORT=1883
MQTT_USERNAME=worker_user
MQTT_PASSWORD=worker_password
```

## Advanced Worker Configuration

### Per-Route Worker Counts

```python
from core.router import Router
from app.controllers import *

router = Router()

# Different worker counts for different load patterns
router.on("sensors/temperature/{device_id}", 
          SensorController.handle_temperature,
          shared=True, worker_count=2)     # Light processing

router.on("sensors/image/{device_id}", 
          ImageController.process_image,
          shared=True, worker_count=8)     # Heavy processing

router.on("analytics/realtime", 
          AnalyticsController.process_realtime,
          shared=True, worker_count=12)    # Very high throughput

# Mixed configuration - some shared, some not
router.on("commands/{device_id}", 
          DeviceController.execute_command,
          shared=False)                    # Single worker for order preservation

router.on("events/{device_id}", 
          EventController.handle_event,
          shared=True, worker_count=4)     # Multiple workers for events
```

### Dynamic Worker Scaling

```python
class DynamicWorkerManager(WorkerManager):
    """Worker manager with dynamic scaling capabilities"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_workers = int(os.getenv('MIN_WORKERS', '2'))
        self.max_workers = int(os.getenv('MAX_WORKERS', '10'))
        self.scaling_enabled = True
    
    async def monitor_and_scale(self):
        """Monitor load and scale workers accordingly"""
        
        while self.scaling_enabled:
            try:
                # Get current metrics
                message_rate = await self._get_message_rate()
                cpu_usage = await self._get_cpu_usage()
                queue_depth = await self._get_queue_depth()
                
                # Calculate desired worker count
                desired_workers = self._calculate_worker_count(
                    message_rate, cpu_usage, queue_depth
                )
                
                current_workers = len(self.workers)
                
                if desired_workers > current_workers and desired_workers <= self.max_workers:
                    # Scale up
                    workers_to_add = desired_workers - current_workers
                    await self._add_workers(workers_to_add)
                    self.logger.info(f"Scaled up: added {workers_to_add} workers")
                
                elif desired_workers < current_workers and desired_workers >= self.min_workers:
                    # Scale down
                    workers_to_remove = current_workers - desired_workers
                    await self._remove_workers(workers_to_remove)
                    self.logger.info(f"Scaled down: removed {workers_to_remove} workers")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in worker scaling: {e}")
                await asyncio.sleep(60)
    
    def _calculate_worker_count(self, message_rate, cpu_usage, queue_depth):
        """Calculate optimal worker count based on metrics"""
        
        # Base calculation on message rate (100 msgs/second per worker)
        rate_based = max(1, int(message_rate / 100))
        
        # Adjust for CPU usage
        cpu_factor = 1.0
        if cpu_usage > 80:
            cpu_factor = 1.5  # More workers for high CPU
        elif cpu_usage < 30:
            cpu_factor = 0.7  # Fewer workers for low CPU
        
        # Adjust for queue depth
        queue_factor = 1.0
        if queue_depth > 1000:
            queue_factor = 1.3  # More workers for high queue
        
        optimal_workers = int(rate_based * cpu_factor * queue_factor)
        return max(self.min_workers, min(optimal_workers, self.max_workers))

# Usage
dynamic_manager = DynamicWorkerManager(router, "dynamic_workers")
dynamic_manager.start_workers()

# Start monitoring task
asyncio.create_task(dynamic_manager.monitor_and_scale())
```

## MQTT Shared Subscription Details

### Subscription Topics

RouteMQ automatically handles MQTT shared subscription formatting:

```python
# Route definition
router.on("sensors/{device_id}/data", handler, shared=True)

# Regular subscription topic (single instance)
"sensors/+/data"

# Shared subscription topic (multiple workers)
"$share/workers/sensors/+/data"
```

### Group Names

Configure shared subscription groups:

```python
# Different groups for different purposes
production_manager = WorkerManager(router, group_name="production_workers")
staging_manager = WorkerManager(router, group_name="staging_workers") 
analytics_manager = WorkerManager(router, group_name="analytics_workers")

# Groups isolate worker pools
# Messages to production_workers won't go to staging_workers
```

### Load Balancing Algorithms

Different MQTT brokers use different load balancing strategies:

- **Round-robin**: Most common, distributes messages evenly
- **Hash-based**: Routes based on message characteristics
- **Least connections**: Routes to worker with fewest active connections
- **Random**: Randomly distributes messages

## Use Cases and Patterns

### High-Throughput Data Ingestion

```python
# IoT sensor data processing
router.on("iot/sensors/{sensor_type}/{device_id}", 
          DataIngestionController.process_sensor_data,
          shared=True, 
          worker_count=10,   # 10 workers for high throughput
          qos=1)             # At-least-once delivery

# Bulk data uploads
router.on("data/bulk/{batch_id}", 
          BulkController.process_batch,
          shared=True,
          worker_count=5,    # Fewer workers, more CPU per message
          qos=2)             # Exactly-once delivery
```

### Image and File Processing

```python
# Image processing pipeline
router.on("images/upload/{user_id}", 
          ImageController.process_upload,
          shared=True,
          worker_count=4,    # CPU-intensive processing
          qos=1)

# Video processing (very CPU intensive)
router.on("videos/transcode/{video_id}", 
          VideoController.transcode,
          shared=True,
          worker_count=2,    # Limited by CPU cores
          qos=2)
```

### Real-time Analytics

```python
# Event stream processing
router.on("events/user/{user_id}/{event_type}", 
          AnalyticsController.process_event,
          shared=True,
          worker_count=8,    # High throughput events
          qos=0)             # Fire-and-forget for speed

# Metrics aggregation
router.on("metrics/{metric_type}/{timestamp}", 
          MetricsController.aggregate,
          shared=True,
          worker_count=6)
```

### Order-Sensitive Processing

```python
# Commands must be processed in order - NO shared subscription
router.on("devices/{device_id}/commands", 
          DeviceController.execute_command,
          shared=False,      # Single worker preserves order
          qos=2)

# Financial transactions - order critical
router.on("payments/transactions/{account_id}", 
          PaymentController.process_transaction,
          shared=False,      # Must maintain order
          qos=2)

# But notifications can be parallel
router.on("notifications/{user_id}", 
          NotificationController.send_notification,
          shared=True,       # Order doesn't matter
          worker_count=4)
```

## Worker Process Implementation

### Worker Lifecycle

```python
class WorkerProcess:
    """Individual worker process lifecycle"""
    
    def __init__(self, worker_id, router_directory, shared_routes, broker_config, group_name):
        self.worker_id = worker_id
        self.router_directory = router_directory
        self.shared_routes = shared_routes  # Routes this worker handles
        self.broker_config = broker_config
        self.group_name = group_name
        self.client = None
        self.router = None
    
    def run(self):
        """Main worker process execution"""
        
        # 1. Setup router (reload routes in worker process)
        self.setup_router()
        
        # 2. Setup MQTT client
        self.setup_client()
        
        # 3. Connect to broker
        self.connect_to_broker()
        
        # 4. Subscribe to shared topics
        self.subscribe_to_shared_topics()
        
        # 5. Start message processing loop
        self.start_processing_loop()
    
    def setup_router(self):
        """Load routes dynamically in worker process"""
        
        # Each worker loads its own copy of routes
        registry = RouterRegistry(self.router_directory)
        self.router = registry.discover_and_load_routers()
        
        self.logger.info(f"Worker {self.worker_id} loaded {len(self.router.routes)} routes")
    
    def subscribe_to_shared_topics(self):
        """Subscribe to shared subscription topics"""
        
        for route_info in self.shared_routes:
            # Create shared subscription topic
            shared_topic = f"$share/{self.group_name}/{route_info['mqtt_topic']}"
            
            self.logger.info(f"Worker {self.worker_id} subscribing to {shared_topic}")
            self.client.subscribe(shared_topic, route_info['qos'])
    
    def _on_message(self, client, userdata, msg):
        """Process received message"""
        
        # Extract actual topic from shared subscription
        actual_topic = msg.topic
        if msg.topic.startswith(f"$share/{self.group_name}/"):
            actual_topic = msg.topic[len(f"$share/{self.group_name}/"):]
        
        # Parse payload
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload
        
        # Dispatch through router
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self.router.dispatch(actual_topic, payload, client)
            )
        finally:
            loop.close()
```

### Worker Coordination

```python
def worker_process_main(worker_id, router_directory, shared_routes, broker_config, group_name):
    """Main entry point for worker process"""
    
    # Setup logging for this worker
    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s - Worker-{worker_id} - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(f'Worker-{worker_id}')
    logger.info(f"Starting worker {worker_id}")
    
    try:
        # Create and run worker
        worker = WorkerProcess(worker_id, router_directory, shared_routes, broker_config, group_name)
        worker.run()
        
    except KeyboardInterrupt:
        logger.info(f"Worker {worker_id} shutting down...")
    except Exception as e:
        logger.error(f"Worker {worker_id} error: {e}")
    finally:
        logger.info(f"Worker {worker_id} stopped")
```

## Monitoring and Debugging

### Worker Health Monitoring

```python
class WorkerHealthMonitor:
    """Monitor worker process health and performance"""
    
    def __init__(self, worker_manager):
        self.worker_manager = worker_manager
        self.metrics = {
            'active_workers': 0,
            'total_messages': 0,
            'messages_per_worker': {},
            'worker_errors': {},
            'average_processing_time': 0
        }
    
    async def monitor_workers(self):
        """Continuously monitor worker health"""
        
        while True:
            try:
                # Check worker processes
                active_workers = sum(1 for worker in self.worker_manager.workers if worker.is_alive())
                self.metrics['active_workers'] = active_workers
                
                # Check for dead workers
                dead_workers = [worker for worker in self.worker_manager.workers if not worker.is_alive()]
                
                if dead_workers:
                    self.logger.warning(f"Found {len(dead_workers)} dead workers, restarting...")
                    await self._restart_dead_workers(dead_workers)
                
                # Log health status
                self.logger.info(f"Worker health: {active_workers}/{len(self.worker_manager.workers)} workers active")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error monitoring workers: {e}")
                await asyncio.sleep(60)
    
    async def _restart_dead_workers(self, dead_workers):
        """Restart dead worker processes"""
        
        for dead_worker in dead_workers:
            try:
                # Remove dead worker
                self.worker_manager.workers.remove(dead_worker)
                dead_worker.terminate()
                
                # Start replacement worker
                worker_id = len(self.worker_manager.workers)
                new_worker = self.worker_manager._create_worker_process(worker_id)
                new_worker.start()
                self.worker_manager.workers.append(new_worker)
                
                self.logger.info(f"Restarted worker {worker_id}")
                
            except Exception as e:
                self.logger.error(f"Failed to restart worker: {e}")

# Usage
health_monitor = WorkerHealthMonitor(worker_manager)
asyncio.create_task(health_monitor.monitor_workers())
```

### Performance Metrics

```python
class WorkerMetrics:
    """Collect and analyze worker performance metrics"""
    
    def __init__(self):
        self.message_counts = {}
        self.processing_times = {}
        self.error_counts = {}
    
    def record_message_processed(self, worker_id, topic, processing_time):
        """Record successful message processing"""
        
        if worker_id not in self.message_counts:
            self.message_counts[worker_id] = 0
            self.processing_times[worker_id] = []
        
        self.message_counts[worker_id] += 1
        self.processing_times[worker_id].append(processing_time)
        
        # Keep only recent processing times (last 1000)
        if len(self.processing_times[worker_id]) > 1000:
            self.processing_times[worker_id] = self.processing_times[worker_id][-1000:]
    
    def record_error(self, worker_id, topic, error):
        """Record processing error"""
        
        if worker_id not in self.error_counts:
            self.error_counts[worker_id] = 0
        
        self.error_counts[worker_id] += 1
    
    def get_worker_stats(self):
        """Get comprehensive worker statistics"""
        
        stats = {
            'total_workers': len(self.message_counts),
            'total_messages': sum(self.message_counts.values()),
            'worker_distribution': {}
        }
        
        for worker_id in self.message_counts:
            message_count = self.message_counts[worker_id]
            error_count = self.error_counts.get(worker_id, 0)
            times = self.processing_times.get(worker_id, [])
            
            avg_time = sum(times) / len(times) if times else 0
            
            stats['worker_distribution'][worker_id] = {
                'messages_processed': message_count,
                'errors': error_count,
                'error_rate': error_count / message_count if message_count > 0 else 0,
                'avg_processing_time': avg_time
            }
        
        return stats

# Usage in middleware
class WorkerMetricsMiddleware(Middleware):
    def __init__(self, metrics_collector):
        self.metrics = metrics_collector
    
    async def handle(self, context, next_handler):
        start_time = time.time()
        worker_id = os.getpid()  # Use process ID as worker identifier
        
        try:
            result = await next_handler(context)
            
            # Record success
            processing_time = time.time() - start_time
            self.metrics.record_message_processed(
                worker_id, context['topic'], processing_time
            )
            
            return result
            
        except Exception as e:
            # Record error
            self.metrics.record_error(worker_id, context['topic'], str(e))
            raise
```

## Testing Shared Subscriptions

### Unit Testing

```python
import pytest
from unittest.mock import Mock, patch
from core.worker_manager import WorkerManager

def test_shared_route_identification():
    """Test identification of shared routes"""
    
    router = Router()
    
    # Add mixed routes
    router.on("regular/route", Mock(), shared=False)
    router.on("shared/route", Mock(), shared=True, worker_count=3)
    router.on("another/shared", Mock(), shared=True, worker_count=5)
    
    worker_manager = WorkerManager(router, "test_group")
    shared_routes = worker_manager.get_shared_routes_info()
    
    # Should find 2 shared routes
    assert len(shared_routes) == 2
    
    # Check route details
    shared_topics = [route['topic'] for route in shared_routes]
    assert "shared/route" in shared_topics
    assert "another/shared" in shared_topics
    assert "regular/route" not in shared_topics

def test_worker_count_calculation():
    """Test worker count calculation"""
    
    router = Router()
    router.on("high/load", Mock(), shared=True, worker_count=8)
    router.on("medium/load", Mock(), shared=True, worker_count=4)
    
    worker_manager = WorkerManager(router, "test_group")
    
    # Total workers should be sum of all shared routes
    total_workers = sum(route['worker_count'] for route in worker_manager.get_shared_routes_info())
    assert total_workers == 12

@pytest.mark.asyncio
async def test_shared_subscription_topic_format():
    """Test MQTT shared subscription topic formatting"""
    
    from core.router import Route
    
    route = Route("sensors/{device_id}/data", Mock(), shared=True)
    
    # Regular subscription topic
    assert route.get_subscription_topic() == "sensors/+/data"
    
    # Shared subscription topic
    assert route.get_subscription_topic("test_group") == "$share/test_group/sensors/+/data"
```

### Integration Testing

```python
@pytest.mark.asyncio 
async def test_worker_message_distribution():
    """Test that workers actually receive different messages"""
    
    import multiprocessing
    import time
    from unittest.mock import Mock
    
    # Create shared route
    router = Router()
    message_handler = Mock()
    router.on("test/shared/{id}", message_handler, shared=True, worker_count=2)
    
    # Start workers (simplified test version)
    worker_manager = WorkerManager(router, "test_group")
    
    # Simulate message distribution
    messages = [
        ("test/shared/1", {"data": "message1"}),
        ("test/shared/2", {"data": "message2"}),
        ("test/shared/3", {"data": "message3"}),
        ("test/shared/4", {"data": "message4"})
    ]
    
    # In real test, would send actual MQTT messages
    # and verify distribution across workers
    
    # For unit test, verify route configuration
    shared_routes = worker_manager.get_shared_routes_info()
    assert len(shared_routes) == 1
    assert shared_routes[0]['worker_count'] == 2
```

### Load Testing

```python
async def load_test_shared_subscriptions():
    """Load test shared subscription performance"""
    
    import asyncio
    import time
    
    # Setup
    router = Router()
    
    async def fast_handler(context):
        await asyncio.sleep(0.01)  # Simulate 10ms processing
        return {"processed": True}
    
    router.on("load/test/{id}", fast_handler, shared=True, worker_count=4)
    
    # Simulate high message volume
    start_time = time.time()
    message_count = 1000
    
    # In real test, would publish actual MQTT messages
    tasks = []
    for i in range(message_count):
        context = {
            'topic': f'load/test/{i}',
            'payload': {'data': f'message_{i}'},
            'params': {'id': str(i)}
        }
        tasks.append(router.dispatch(context['topic'], context['payload'], None))
    
    # Process all messages
    await asyncio.gather(*tasks)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Processed {message_count} messages in {duration:.2f} seconds")
    print(f"Throughput: {message_count / duration:.2f} messages/second")
    
    # Verify performance meets requirements
    assert duration < 10  # Should process 1000 messages in under 10 seconds

# Run load test
asyncio.run(load_test_shared_subscriptions())
```

## Production Deployment

### Docker Configuration

```yaml
# docker-compose.yml for scaled deployment
version: '3.8'

services:
  routemq-workers:
    build: .
    environment:
      - MQTT_BROKER=mqtt.example.com
      - MQTT_GROUP_NAME=production_workers
      - WORKER_COUNT=4
      - LOG_LEVEL=INFO
    deploy:
      replicas: 3  # 3 containers × 4 workers = 12 total workers
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M
    restart: unless-stopped
    depends_on:
      - mqtt-broker
      - redis
      - mysql

  mqtt-broker:
    image: eclipse-mosquitto:2.0
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
```

### Kubernetes Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: routemq-workers
spec:
  replicas: 5  # 5 pods
  selector:
    matchLabels:
      app: routemq-workers
  template:
    metadata:
      labels:
        app: routemq-workers
    spec:
      containers:
      - name: routemq
        image: routemq:latest
        env:
        - name: WORKER_COUNT
          value: "3"  # 3 workers per pod = 15 total workers
        - name: MQTT_GROUP_NAME
          value: "k8s-workers"
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### Monitoring Setup

```python
# monitoring/worker_dashboard.py
class WorkerDashboard:
    """Dashboard for monitoring worker performance"""
    
    def __init__(self, worker_manager):
        self.worker_manager = worker_manager
    
    async def get_dashboard_data(self):
        """Get comprehensive dashboard data"""
        
        shared_routes = self.worker_manager.get_shared_routes_info()
        
        dashboard_data = {
            'overview': {
                'total_workers': len(self.worker_manager.workers),
                'shared_routes': len(shared_routes),
                'group_name': self.worker_manager.group_name
            },
            'workers': [],
            'routes': shared_routes,
            'health': await self._get_health_status()
        }
        
        # Worker details
        for i, worker in enumerate(self.worker_manager.workers):
            worker_info = {
                'worker_id': i,
                'process_id': worker.pid,
                'is_alive': worker.is_alive(),
                'memory_usage': await self._get_worker_memory(worker.pid),
                'cpu_usage': await self._get_worker_cpu(worker.pid)
            }
            dashboard_data['workers'].append(worker_info)
        
        return dashboard_data
    
    async def _get_health_status(self):
        """Get overall health status"""
        
        total_workers = len(self.worker_manager.workers)
        alive_workers = sum(1 for w in self.worker_manager.workers if w.is_alive())
        
        health_percentage = (alive_workers / total_workers * 100) if total_workers > 0 else 0
        
        if health_percentage >= 90:
            status = "healthy"
        elif health_percentage >= 70:
            status = "degraded"
        else:
            status = "unhealthy"
        
        return {
            'status': status,
            'healthy_workers': alive_workers,
            'total_workers': total_workers,
            'health_percentage': health_percentage
        }
```

## Best Practices

### When to Use Shared Subscriptions

**✅ Use shared subscriptions for:**
- High-throughput data processing
- CPU-intensive operations
- Independent message processing
- Scalable data ingestion
- Parallel analytics processing

**❌ Avoid shared subscriptions for:**
- Order-dependent processing
- Low-volume topics
- State-dependent operations
- Sequential workflows
- Real-time control systems

### Worker Count Guidelines

```python
# Calculate optimal worker count
def calculate_worker_count(expected_throughput, processing_time, cpu_cores):
    """
    Calculate optimal worker count based on system characteristics
    
    Args:
        expected_throughput: Messages per second
        processing_time: Average processing time per message (seconds)
        cpu_cores: Available CPU cores
    """
    
    # Base calculation: throughput × processing time
    base_workers = int(expected_throughput * processing_time)
    
    # Limit by CPU cores (leave some for system)
    cpu_limit = max(1, cpu_cores - 1)
    
    # Apply safety margin
    optimal_workers = min(base_workers, cpu_limit)
    
    return max(1, optimal_workers)

# Example calculations
workers_needed = calculate_worker_count(
    expected_throughput=500,  # 500 messages/second
    processing_time=0.1,      # 100ms per message
    cpu_cores=8               # 8 CPU cores
)
# Result: min(50, 7) = 7 workers
```

### Resource Management

```python
# Configure resource limits per worker
import resource

def configure_worker_resources():
    """Configure resource limits for worker processes"""
    
    # Limit memory usage per worker (in bytes)
    memory_limit = 512 * 1024 * 1024  # 512MB
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    
    # Limit CPU time per process
    cpu_limit = 300  # 5 minutes
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    
    # Limit open files
    file_limit = 1024
    resource.setrlimit(resource.RLIMIT_NOFILE, (file_limit, file_limit))

# Call in worker process
configure_worker_resources()
```

## Next Steps

- [Dynamic Router Loading](dynamic-loading.md) - Learn about automatic route discovery
- [Route Definition](route-definition.md) - Master route syntax and patterns
- [Worker Processes](../core-concepts/worker-processes.md) - Deep dive into worker architecture
- [Scaling](../deployment/scaling.md) - Production scaling strategies
