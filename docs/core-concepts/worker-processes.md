# Worker Processes

RouteMQ supports horizontal scaling through MQTT shared subscriptions, allowing multiple worker processes to handle messages from the same topic for high-throughput applications.

## Shared Subscriptions Overview

MQTT shared subscriptions distribute messages across multiple subscribers, enabling load balancing and horizontal scaling:

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
  Round-robin or
  broker-specific
  distribution
```

## Enabling Shared Subscriptions

### Route Configuration

Enable shared subscriptions for specific routes:

```python
from core.router import Router
from app.controllers.sensor_controller import SensorController

router = Router()

# Regular subscription (single instance)
router.on("alerts/{device_id}", AlertController.handle_alert)

# Shared subscription with 3 workers
router.on("sensors/{device_id}/data", 
          SensorController.process_data,
          shared=True, 
          worker_count=3)

# High-throughput route with 5 workers
router.on("telemetry/bulk", 
          TelemetryController.process_bulk,
          shared=True,
          worker_count=5,
          qos=1)
```

### Group Configuration

Configure the shared subscription group name:

```python
# Environment variable
MQTT_GROUP_NAME=production_workers

# Or in code
worker_manager = WorkerManager(router, group_name="production_workers")
```

## Worker Manager

The WorkerManager handles the lifecycle of worker processes:

### Starting Workers

```python
from core.worker_manager import WorkerManager

# Initialize worker manager
worker_manager = WorkerManager(
    router=main_router,
    group_name="production_workers",
    router_directory="app.routers"
)

# Start workers for shared subscriptions
worker_manager.start_workers()

# Or specify custom worker count
worker_manager.start_workers(num_workers=8)
```

### Worker Process Management

```python
class WorkerManager:
    def start_workers(self, num_workers: int = None):
        """Start worker processes based on route configuration"""
        
        shared_routes = self.get_shared_routes_info()
        if not shared_routes:
            self.logger.info("No shared routes found, skipping worker startup")
            return
        
        # Calculate total workers needed
        total_workers = num_workers or sum(route['worker_count'] for route in shared_routes)
        
        # Start worker processes
        for worker_id in range(total_workers):
            process = multiprocessing.Process(
                target=worker_process_main,
                args=(worker_id, self.router_directory, shared_routes, 
                      broker_config, self.group_name)
            )
            process.start()
            self.workers.append(process)
        
        self.logger.info(f"Started {total_workers} worker processes")
```

## Worker Process Architecture

### Process Isolation

Each worker runs in a separate process:

```python
def worker_process_main(worker_id: int, router_directory: str, 
                       shared_routes: List[Dict], broker_config: Dict, 
                       group_name: str):
    """Main function for individual worker process"""
    
    # Setup logging for this worker
    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s - Worker-{worker_id} - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create worker instance
    worker = WorkerProcess(worker_id, router_directory, shared_routes, 
                          broker_config, group_name)
    
    # Run the worker
    worker.run()
```

### Independent Router Loading

Each worker loads its own router instance:

```python
class WorkerProcess:
    def setup_router(self):
        """Each worker loads routes independently"""
        try:
            registry = RouterRegistry(self.router_directory)
            self.router = registry.discover_and_load_routers()
            self.logger.info(f"Worker {self.worker_id} loaded {len(self.router.routes)} routes")
        except Exception as e:
            self.logger.error(f"Worker {self.worker_id} failed to load router: {e}")
            self.router = Router()  # Fallback to empty router
```

### MQTT Client per Worker

Each worker maintains its own MQTT connection:

```python
def setup_client(self):
    """Setup dedicated MQTT client for this worker"""
    from paho.mqtt import client as mqtt_client
    
    # Unique client ID per worker
    client_id = f"mqtt-worker-{self.worker_id}-{uuid.uuid4().hex[:8]}"
    
    self.client = mqtt_client.Client(client_id=client_id)
    self.client.on_connect = self._on_connect
    self.client.on_message = self._on_message
    
    # Configure authentication
    if self.broker_config.get('username'):
        self.client.username_pw_set(
            self.broker_config['username'], 
            self.broker_config['password']
        )
```

## Shared Subscription Topics

### Topic Format

Shared subscriptions use the `$share` prefix:

```python
# Regular subscription
topic: "sensors/device123/data"

# Shared subscription  
topic: "$share/workers/sensors/+/data"

# Format: $share/{group_name}/{topic_pattern}
```

### Subscription Management

Workers automatically subscribe to shared topics:

```python
def _on_connect(self, client, userdata, flags, rc):
    """Subscribe to shared topics when connected"""
    self.logger.info(f"Worker {self.worker_id} connected with result code {rc}")
    
    for route_info in self.shared_routes:
        # Create shared subscription topic
        shared_topic = f"$share/{self.group_name}/{route_info['mqtt_topic']}"
        
        self.logger.info(f"Worker {self.worker_id} subscribing to {shared_topic}")
        client.subscribe(shared_topic, route_info['qos'])
```

### Topic Extraction

Workers extract the original topic from shared subscription messages:

```python
def _on_message(self, client, userdata, msg):
    """Handle message from shared subscription"""
    
    # Original topic from shared subscription
    actual_topic = msg.topic
    if msg.topic.startswith(f"$share/{self.group_name}/"):
        # Strip shared prefix to get actual topic
        actual_topic = msg.topic[len(f"$share/{self.group_name}/"):]
    
    # Process with actual topic for route matching
    await self.router.dispatch(actual_topic, payload, client)
```

## Load Balancing Strategies

### Broker-Based Distribution

Most MQTT brokers implement round-robin distribution:

```python
# Messages distributed evenly across workers
Worker 1: Message 1, 4, 7, 10, ...
Worker 2: Message 2, 5, 8, 11, ...  
Worker 3: Message 3, 6, 9, 12, ...
```

### Route-Specific Worker Counts

Configure different worker counts per route:

```python
# Low-throughput routes - single worker
router.on("config/update", ConfigController.update, shared=False)

# Medium-throughput routes - 2 workers  
router.on("alerts/{device_id}", AlertController.handle, shared=True, worker_count=2)

# High-throughput routes - 5 workers
router.on("sensors/+/data", SensorController.process, shared=True, worker_count=5)

# Bulk processing - 10 workers
router.on("telemetry/bulk", BulkController.process, shared=True, worker_count=10)
```

## Scaling Patterns

### Auto-Scaling Based on Load

```python
class AdaptiveWorkerManager(WorkerManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message_rates = {}
        self.scaling_enabled = True
    
    async def monitor_and_scale(self):
        """Monitor message rates and adjust worker count"""
        while self.scaling_enabled:
            for route in self.get_shared_routes_info():
                current_rate = await self.get_message_rate(route['topic'])
                optimal_workers = self.calculate_optimal_workers(current_rate)
                
                if optimal_workers != route['worker_count']:
                    await self.scale_workers(route['topic'], optimal_workers)
            
            await asyncio.sleep(60)  # Check every minute
    
    def calculate_optimal_workers(self, message_rate: float) -> int:
        """Calculate optimal worker count based on message rate"""
        # Example: 1 worker per 100 messages/second
        return max(1, min(10, int(message_rate / 100)))
```

### Geographic Distribution

```python
# Region-specific worker groups
worker_manager_us = WorkerManager(router, group_name="us_east_workers")
worker_manager_eu = WorkerManager(router, group_name="eu_west_workers") 
worker_manager_asia = WorkerManager(router, group_name="asia_workers")

# Each region handles its own message volume
worker_manager_us.start_workers(num_workers=5)
worker_manager_eu.start_workers(num_workers=3)
worker_manager_asia.start_workers(num_workers=2)
```

## Performance Characteristics

### Throughput Benefits

```python
# Single process (no shared subscription)
Throughput: ~1,000 messages/second

# 3 workers with shared subscription
Throughput: ~2,800 messages/second (2.8x improvement)

# 5 workers with shared subscription  
Throughput: ~4,500 messages/second (4.5x improvement)

# Diminishing returns after optimal point
# 10 workers: ~6,000 messages/second (overhead increases)
```

### Latency Considerations

- **Process Startup**: Initial latency for worker process creation
- **Message Distribution**: Small overhead for shared subscription routing
- **Context Switching**: Minimal impact due to process isolation

### Memory Usage

```python
# Memory per worker process
Base Process: ~20MB
Router + Routes: ~5MB  
MQTT Client: ~2MB
Application Code: ~10MB
Total per Worker: ~37MB

# 5 workers = ~185MB total
# vs Single process = ~37MB
```

## Configuration and Deployment

### Environment Configuration

```bash
# .env file
MQTT_BROKER=mqtt.example.com
MQTT_PORT=1883
MQTT_USERNAME=worker_user
MQTT_PASSWORD=worker_pass
MQTT_GROUP_NAME=production_workers

# Worker configuration
WORKER_COUNT=5
WORKER_AUTO_SCALE=true
WORKER_MIN_COUNT=2
WORKER_MAX_COUNT=10
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . /app
WORKDIR /app

# Default to 3 workers
ENV WORKER_COUNT=3

CMD ["python", "main.py", "--workers"]
```

### Kubernetes Scaling

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: routemq-workers
spec:
  replicas: 3  # Number of pods
  selector:
    matchLabels:
      app: routemq-workers
  template:
    metadata:
      labels:
        app: routemq-workers
    spec:
      containers:
      - name: worker
        image: routemq:latest
        env:
        - name: WORKER_COUNT
          value: "2"  # Workers per pod
        - name: MQTT_GROUP_NAME
          value: "k8s-workers"
```

## Monitoring and Observability

### Worker Health Monitoring

```python
class WorkerHealthMonitor:
    def __init__(self, worker_manager: WorkerManager):
        self.worker_manager = worker_manager
        self.health_checks = {}
    
    async def monitor_workers(self):
        """Monitor worker process health"""
        while True:
            for worker in self.worker_manager.workers:
                if not worker.is_alive():
                    self.logger.error(f"Worker {worker.pid} died, restarting...")
                    await self.restart_worker(worker)
            
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def restart_worker(self, failed_worker):
        """Restart a failed worker process"""
        # Remove failed worker
        self.worker_manager.workers.remove(failed_worker)
        
        # Start replacement worker
        new_worker = self.worker_manager.start_single_worker()
        self.worker_manager.workers.append(new_worker)
```

### Metrics Collection

```python
class WorkerMetrics:
    def __init__(self):
        self.message_counts = {}
        self.processing_times = {}
        self.error_counts = {}
    
    def record_message_processed(self, worker_id: int, processing_time: float):
        """Record successful message processing"""
        self.message_counts[worker_id] = self.message_counts.get(worker_id, 0) + 1
        self.processing_times.setdefault(worker_id, []).append(processing_time)
    
    def record_error(self, worker_id: int, error_type: str):
        """Record processing error"""
        key = f"{worker_id}:{error_type}"
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
    
    def get_worker_stats(self, worker_id: int) -> dict:
        """Get performance stats for a worker"""
        times = self.processing_times.get(worker_id, [])
        return {
            'messages_processed': self.message_counts.get(worker_id, 0),
            'avg_processing_time': sum(times) / len(times) if times else 0,
            'error_count': sum(v for k, v in self.error_counts.items() 
                             if k.startswith(f"{worker_id}:"))
        }
```

## Best Practices

### When to Use Shared Subscriptions

✅ **Use for:**
- High-throughput topics (>100 messages/second)
- CPU-intensive processing
- I/O-bound operations that can be parallelized
- Bulk data processing

❌ **Don't use for:**
- Low-frequency topics (<10 messages/second)
- Order-dependent processing
- Stateful operations requiring message sequence
- Simple, fast operations (<1ms processing time)

### Worker Count Guidelines

```python
# Calculation formula
optimal_workers = min(
    max_workers_allowed,
    max(
        min_workers_required,
        message_rate_per_second / messages_per_worker_per_second
    )
)

# Example calculations:
# 500 msg/sec, 50 msg/worker/sec → 10 workers
# 100 msg/sec, 50 msg/worker/sec → 2 workers  
# 50 msg/sec, 50 msg/worker/sec → 1 worker
```

### Resource Management

1. **Memory**: Monitor memory usage per worker
2. **CPU**: Ensure CPU cores available for workers
3. **Connections**: Limit database connections per worker
4. **File Handles**: Monitor open file descriptors

### Error Handling

```python
class RobustWorkerProcess(WorkerProcess):
    async def handle_message_with_retry(self, topic: str, payload: Any):
        """Handle message with retry logic"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                await self.router.dispatch(topic, payload, self.client)
                return
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt == max_retries - 1:
                    # Final attempt failed - send to dead letter queue
                    await self.send_to_dlq(topic, payload, str(e))
                else:
                    # Wait before retry
                    await asyncio.sleep(2 ** attempt)
```

## Troubleshooting

### Common Issues

**Workers not receiving messages:**
```bash
# Check shared subscription support
mosquitto_pub -h broker -t '$share/test/topic' -m 'test'

# Verify group name consistency
grep MQTT_GROUP_NAME .env
```

**Uneven load distribution:**
```python
# Monitor message distribution
for worker_id, count in worker_metrics.message_counts.items():
    print(f"Worker {worker_id}: {count} messages")

# Expected: roughly equal distribution
```

**High memory usage:**
```python
# Monitor worker memory
import psutil
for worker in worker_manager.workers:
    process = psutil.Process(worker.pid)
    print(f"Worker {worker.pid}: {process.memory_info().rss / 1024 / 1024:.1f}MB")
```

### Debug Mode

```python
# Enable debug logging for workers
ROUTEMQ_LOG_LEVEL=DEBUG

# Worker-specific debugging
class DebugWorkerProcess(WorkerProcess):
    def _on_message(self, client, userdata, msg):
        self.logger.debug(f"Worker {self.worker_id} received: {msg.topic}")
        super()._on_message(client, userdata, msg)
        self.logger.debug(f"Worker {self.worker_id} finished processing")
```

## Next Steps

- [Controllers](../controllers/README.md) - Implement business logic for worker processes
- [Deployment](../deployment/README.md) - Deploy workers in production
- [Monitoring](../monitoring/README.md) - Monitor worker performance
