# Scaling

Scale RouteMQ applications to handle increased load through horizontal and vertical scaling strategies.

## Scaling Overview

RouteMQ supports multiple scaling approaches:

- **Horizontal Scaling**: Add more application instances
- **Vertical Scaling**: Increase resources per instance
- **Database Scaling**: Scale database layer independently
- **MQTT Broker Scaling**: Scale message broker infrastructure
- **Auto-scaling**: Automatic scaling based on metrics

## Horizontal Scaling

### Shared Subscription Scaling

RouteMQ's built-in shared subscription support enables horizontal scaling:

```python
# Enable shared subscriptions in your routes
from core.router import Router

router = Router()

# Scale with multiple workers for high-throughput routes
router.on("sensors/{device_id}/data", 
          SensorController.process_data,
          shared=True, 
          worker_count=5)  # 5 workers for this route

# Different scaling for different routes
router.on("alerts/{device_id}", 
          AlertController.handle_alert,
          shared=True,
          worker_count=2)  # 2 workers for alerts

# Non-shared for order-dependent processing
router.on("commands/{device_id}", 
          CommandController.execute_command,
          shared=False)  # Single worker maintains order
```

### Container-Based Horizontal Scaling

#### Docker Swarm Scaling

```yaml
# docker-compose.swarm.yml
version: '3.8'

services:
  routemq:
    image: routemq:production
    deploy:
      replicas: 5  # Run 5 instances
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M
    environment:
      - MQTT_GROUP_NAME=swarm_workers
      - WORKER_COUNT=3
    networks:
      - routemq-network

networks:
  routemq-network:
    driver: overlay
    attachable: true
```

Deploy with Docker Swarm:

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.swarm.yml routemq

# Scale services
docker service scale routemq_routemq=10

# Check service status
docker service ls
docker service ps routemq_routemq
```

#### Kubernetes Horizontal Scaling

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: routemq
  namespace: production
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
  selector:
    matchLabels:
      app: routemq
  template:
    metadata:
      labels:
        app: routemq
    spec:
      containers:
      - name: routemq
        image: routemq:v1.0.0
        ports:
        - containerPort: 8080
        env:
        - name: MQTT_GROUP_NAME
          value: "k8s_workers"
        - name: WORKER_COUNT
          value: "3"
        envFrom:
        - configMapRef:
            name: routemq-config
        - secretRef:
            name: routemq-secrets
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

Scale Kubernetes deployment:

```bash
# Scale manually
kubectl scale deployment routemq --replicas=10

# Check scaling status
kubectl get deployment routemq
kubectl get pods -l app=routemq
```

### Multi-Instance Configuration

#### Instance Coordination

```python
# config/scaling.py
import os
import socket
import uuid

class InstanceConfig:
    """Configuration for multi-instance coordination"""
    
    def __init__(self):
        self.instance_id = self._generate_instance_id()
        self.group_name = os.getenv('MQTT_GROUP_NAME', 'default_group')
        self.total_instances = int(os.getenv('TOTAL_INSTANCES', '1'))
        self.instance_index = int(os.getenv('INSTANCE_INDEX', '0'))
    
    def _generate_instance_id(self):
        """Generate unique instance ID"""
        hostname = socket.gethostname()
        pod_name = os.getenv('HOSTNAME', hostname)  # Kubernetes pod name
        unique_suffix = str(uuid.uuid4())[:8]
        return f"{pod_name}-{unique_suffix}"
    
    def get_shared_subscription_group(self):
        """Get group name for shared subscriptions"""
        return f"{self.group_name}_{self.instance_index}"
    
    def should_handle_route(self, route_hash: str) -> bool:
        """Determine if this instance should handle a specific route"""
        # Simple hash-based routing for load distribution
        route_hash_int = hash(route_hash) % self.total_instances
        return route_hash_int == self.instance_index
```

#### Load Distribution Strategies

```python
# config/load_distribution.py
import hashlib
import time
from typing import List, Dict

class LoadDistributionStrategy:
    """Strategies for distributing load across instances"""
    
    @staticmethod
    def round_robin(instances: List[str], request_counter: int) -> str:
        """Round-robin distribution"""
        return instances[request_counter % len(instances)]
    
    @staticmethod
    def hash_based(instances: List[str], key: str) -> str:
        """Hash-based distribution for consistency"""
        hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return instances[hash_value % len(instances)]
    
    @staticmethod
    def weighted_distribution(instances: Dict[str, int], total_weight: int) -> str:
        """Weighted distribution based on instance capacity"""
        import random
        
        weight_sum = 0
        random_value = random.randint(1, total_weight)
        
        for instance, weight in instances.items():
            weight_sum += weight
            if random_value <= weight_sum:
                return instance
        
        # Fallback to first instance
        return list(instances.keys())[0]
    
    @staticmethod
    def least_connections(instance_connections: Dict[str, int]) -> str:
        """Route to instance with least active connections"""
        return min(instance_connections.items(), key=lambda x: x[1])[0]
```

## Vertical Scaling

### Resource Optimization

#### CPU Scaling

```yaml
# Increase CPU resources
services:
  routemq:
    deploy:
      resources:
        limits:
          cpus: '4.0'  # Increased from 1.0
          memory: 2G   # Increased memory accordingly
        reservations:
          cpus: '2.0'  # Higher baseline
          memory: 1G
```

```python
# Optimize CPU usage in application
import asyncio
import concurrent.futures

class CPUOptimizedProcessor:
    """CPU-optimized message processor"""
    
    def __init__(self, max_workers=None):
        # Use ThreadPoolExecutor for CPU-bound tasks
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers or os.cpu_count()
        )
    
    async def process_cpu_intensive_task(self, data):
        """Process CPU-intensive tasks in thread pool"""
        loop = asyncio.get_event_loop()
        
        # Run CPU-bound work in thread pool
        result = await loop.run_in_executor(
            self.executor,
            self._cpu_intensive_function,
            data
        )
        
        return result
    
    def _cpu_intensive_function(self, data):
        """CPU-intensive processing function"""
        # Complex calculations, data transformation, etc.
        pass
```

#### Memory Scaling

```python
# config/memory_optimization.py
import gc
import psutil
import logging

class MemoryManager:
    """Memory management for vertical scaling"""
    
    def __init__(self, max_memory_percent=80):
        self.max_memory_percent = max_memory_percent
        self.logger = logging.getLogger('MemoryManager')
    
    def check_memory_usage(self):
        """Monitor memory usage"""
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        
        if memory_percent > self.max_memory_percent:
            self.logger.warning(f"High memory usage: {memory_percent:.1f}%")
            self._optimize_memory()
        
        return {
            'memory_mb': memory_info.rss / 1024 / 1024,
            'memory_percent': memory_percent
        }
    
    def _optimize_memory(self):
        """Optimize memory usage"""
        # Force garbage collection
        gc.collect()
        
        # Clear internal caches if available
        self._clear_application_caches()
    
    def _clear_application_caches(self):
        """Clear application-specific caches"""
        # Clear Redis cache
        # Clear in-memory data structures
        # Reset connection pools if needed
        pass
```

### Worker Process Scaling

#### Dynamic Worker Adjustment

```python
# core/dynamic_worker_manager.py
import asyncio
import psutil
import time
from typing import Dict, List

class DynamicWorkerManager:
    """Dynamically adjust worker count based on load"""
    
    def __init__(self, min_workers=2, max_workers=10):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.current_workers = min_workers
        self.metrics = {
            'messages_per_second': 0,
            'cpu_usage': 0,
            'memory_usage': 0,
            'queue_depth': 0
        }
    
    async def monitor_and_scale(self):
        """Monitor metrics and adjust worker count"""
        while True:
            await self._collect_metrics()
            optimal_workers = self._calculate_optimal_workers()
            
            if optimal_workers != self.current_workers:
                await self._adjust_workers(optimal_workers)
            
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def _collect_metrics(self):
        """Collect performance metrics"""
        # CPU and memory metrics
        self.metrics['cpu_usage'] = psutil.cpu_percent(interval=1)
        self.metrics['memory_usage'] = psutil.virtual_memory().percent
        
        # Application-specific metrics
        self.metrics['messages_per_second'] = await self._get_message_rate()
        self.metrics['queue_depth'] = await self._get_queue_depth()
    
    def _calculate_optimal_workers(self) -> int:
        """Calculate optimal number of workers"""
        # Base calculation on CPU usage
        cpu_factor = min(2.0, self.metrics['cpu_usage'] / 50.0)
        
        # Adjust for message rate
        message_factor = min(2.0, self.metrics['messages_per_second'] / 100.0)
        
        # Adjust for queue depth
        queue_factor = min(2.0, self.metrics['queue_depth'] / 1000.0)
        
        # Calculate target workers
        target_workers = int(
            self.min_workers * max(cpu_factor, message_factor, queue_factor)
        )
        
        # Apply limits
        return max(self.min_workers, min(target_workers, self.max_workers))
    
    async def _adjust_workers(self, target_workers: int):
        """Adjust worker count"""
        if target_workers > self.current_workers:
            # Scale up
            for _ in range(target_workers - self.current_workers):
                await self._start_worker()
        elif target_workers < self.current_workers:
            # Scale down
            for _ in range(self.current_workers - target_workers):
                await self._stop_worker()
        
        self.current_workers = target_workers
        logging.info(f"Scaled workers to {target_workers}")
```

## Database Scaling

### Read Replicas

```python
# config/database_scaling.py
import random
from sqlalchemy.ext.asyncio import create_async_engine

class DatabaseScalingConfig:
    """Database scaling configuration"""
    
    def __init__(self):
        self.write_engine = create_async_engine(
            self._get_write_connection_string(),
            pool_size=20,
            max_overflow=30
        )
        
        self.read_engines = [
            create_async_engine(
                self._get_read_connection_string(replica),
                pool_size=15,
                max_overflow=25
            )
            for replica in self._get_read_replicas()
        ]
    
    def get_write_engine(self):
        """Get engine for write operations"""
        return self.write_engine
    
    def get_read_engine(self):
        """Get engine for read operations (load balanced)"""
        return random.choice(self.read_engines)
    
    def _get_read_replicas(self):
        """Get list of read replica hosts"""
        replicas = os.getenv('DB_READ_REPLICAS', '').split(',')
        return [replica.strip() for replica in replicas if replica.strip()]
```

### Connection Pool Scaling

```python
# config/connection_pool_scaling.py
class ConnectionPoolScaler:
    """Scale database connection pools based on load"""
    
    def __init__(self):
        self.base_pool_size = 10
        self.max_pool_size = 50
        self.current_pool_size = self.base_pool_size
    
    async def scale_pool_based_on_load(self, engine):
        """Scale connection pool based on current load"""
        pool = engine.pool
        
        # Get pool metrics
        checked_out = pool.checkedout()
        pool_size = pool.size()
        overflow = pool.overflow()
        
        utilization = checked_out / pool_size if pool_size > 0 else 0
        
        # Scale up if utilization is high
        if utilization > 0.8 and pool_size < self.max_pool_size:
            new_size = min(pool_size + 5, self.max_pool_size)
            await self._resize_pool(engine, new_size)
        
        # Scale down if utilization is low
        elif utilization < 0.3 and pool_size > self.base_pool_size:
            new_size = max(pool_size - 2, self.base_pool_size)
            await self._resize_pool(engine, new_size)
```

## Auto-scaling

### Kubernetes Horizontal Pod Autoscaler

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: routemq-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: routemq
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  - type: Pods
    pods:
      metric:
        name: messages_per_second
      target:
        type: AverageValue
        averageValue: "100"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
```

### Custom Metrics for Auto-scaling

```python
# monitoring/custom_metrics.py
import asyncio
import time
from kubernetes import client, config

class CustomMetricsExporter:
    """Export custom metrics for Kubernetes HPA"""
    
    def __init__(self):
        config.load_incluster_config()  # or load_kube_config() for local
        self.custom_api = client.CustomObjectsApi()
        self.metrics = {}
    
    async def export_message_rate_metric(self, messages_per_second: float):
        """Export message rate metric for HPA"""
        metric = {
            "apiVersion": "custom.metrics.k8s.io/v1beta1",
            "kind": "MetricValue",
            "metadata": {
                "name": "messages_per_second",
                "namespace": "production"
            },
            "value": str(messages_per_second),
            "timestamp": time.time()
        }
        
        try:
            self.custom_api.create_namespaced_custom_object(
                group="custom.metrics.k8s.io",
                version="v1beta1",
                namespace="production",
                plural="metrics",
                body=metric
            )
        except Exception as e:
            logging.error(f"Failed to export metric: {e}")
    
    async def monitor_and_export_metrics(self):
        """Continuously monitor and export metrics"""
        while True:
            # Collect application metrics
            message_rate = await self._get_message_rate()
            queue_depth = await self._get_queue_depth()
            
            # Export to Kubernetes
            await self.export_message_rate_metric(message_rate)
            
            await asyncio.sleep(30)
```

### Cloud Auto-scaling

#### AWS ECS Auto-scaling

```json
{
  "service": "routemq-service",
  "cluster": "production-cluster",
  "taskDefinition": "routemq:latest",
  "desiredCount": 3,
  "deploymentConfiguration": {
    "maximumPercent": 200,
    "minimumHealthyPercent": 50
  },
  "autoScalingSettings": {
    "targetTrackingScalingPolicies": [
      {
        "targetValue": 70.0,
        "predefinedMetricSpecification": {
          "predefinedMetricType": "ECSServiceAverageCPUUtilization"
        },
        "scaleOutCooldown": 300,
        "scaleInCooldown": 300
      },
      {
        "targetValue": 80.0,
        "predefinedMetricSpecification": {
          "predefinedMetricType": "ECSServiceAverageMemoryUtilization"
        }
      }
    ]
  }
}
```

#### AWS Lambda Auto-scaling

```yaml
# serverless.yml for Lambda deployment
service: routemq-lambda

provider:
  name: aws
  runtime: python3.9
  memorySize: 512
  timeout: 30
  
functions:
  processMessage:
    handler: lambda_handler.process_message
    events:
      - sqs:
          arn:
            Fn::GetAtt:
              - MessageQueue
              - Arn
          batchSize: 10
    reservedConcurrency: 100  # Limit concurrent executions
    
resources:
  Resources:
    MessageQueue:
      Type: AWS::SQS::Queue
      Properties:
        VisibilityTimeoutSeconds: 60
        RedrivePolicy:
          deadLetterTargetArn:
            Fn::GetAtt:
              - DeadLetterQueue
              - Arn
          maxReceiveCount: 3
```

## Performance Monitoring for Scaling

### Scaling Metrics Dashboard

```python
# monitoring/scaling_dashboard.py
import time
import json
from typing import Dict, List

class ScalingMetricsDashboard:
    """Dashboard for monitoring scaling metrics"""
    
    def __init__(self):
        self.metrics_history = []
        self.scaling_events = []
    
    def record_scaling_event(self, event_type: str, old_count: int, new_count: int, reason: str):
        """Record a scaling event"""
        event = {
            'timestamp': time.time(),
            'type': event_type,  # 'scale_up' or 'scale_down'
            'old_count': old_count,
            'new_count': new_count,
            'reason': reason
        }
        self.scaling_events.append(event)
    
    def get_scaling_summary(self, hours: int = 24) -> Dict:
        """Get scaling summary for the last N hours"""
        cutoff_time = time.time() - (hours * 3600)
        
        recent_events = [
            event for event in self.scaling_events
            if event['timestamp'] >= cutoff_time
        ]
        
        scale_ups = len([e for e in recent_events if e['type'] == 'scale_up'])
        scale_downs = len([e for e in recent_events if e['type'] == 'scale_down'])
        
        return {
            'period_hours': hours,
            'total_scaling_events': len(recent_events),
            'scale_up_events': scale_ups,
            'scale_down_events': scale_downs,
            'events': recent_events[-10:]  # Last 10 events
        }
```

### Load Testing for Scaling Validation

```python
# testing/load_test.py
import asyncio
import time
import paho.mqtt.client as mqtt
from concurrent.futures import ThreadPoolExecutor

class LoadTester:
    """Load testing tool for validating scaling"""
    
    def __init__(self, broker_host: str, broker_port: int = 1883):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.clients = []
        self.message_count = 0
    
    async def run_load_test(self, num_clients: int, messages_per_second: int, duration_seconds: int):
        """Run load test with specified parameters"""
        print(f"Starting load test: {num_clients} clients, {messages_per_second} msg/s, {duration_seconds}s")
        
        # Create MQTT clients
        for i in range(num_clients):
            client = mqtt.Client(f"load_test_client_{i}")
            client.connect(self.broker_host, self.broker_port, 60)
            self.clients.append(client)
        
        # Calculate message interval
        interval = 1.0 / messages_per_second if messages_per_second > 0 else 1.0
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        with ThreadPoolExecutor(max_workers=num_clients) as executor:
            while time.time() < end_time:
                # Send messages from all clients
                tasks = []
                for client in self.clients:
                    task = executor.submit(self._send_test_message, client)
                    tasks.append(task)
                
                # Wait for all messages to be sent
                for task in tasks:
                    task.result()
                
                self.message_count += num_clients
                await asyncio.sleep(interval)
        
        # Cleanup
        for client in self.clients:
            client.disconnect()
        
        total_time = time.time() - start_time
        actual_rate = self.message_count / total_time
        
        print(f"Load test completed:")
        print(f"  Messages sent: {self.message_count}")
        print(f"  Actual rate: {actual_rate:.1f} msg/s")
        print(f"  Duration: {total_time:.1f}s")
    
    def _send_test_message(self, client):
        """Send a test message"""
        message = {
            'timestamp': time.time(),
            'test_data': 'load_test_message',
            'message_id': self.message_count
        }
        
        topic = f"test/load/{self.message_count % 100}"  # Distribute across topics
        client.publish(topic, json.dumps(message), qos=1)
```

## Scaling Best Practices

### Guidelines

1. **Start Small**: Begin with minimal resources and scale up based on actual load
2. **Monitor Continuously**: Use comprehensive monitoring to understand scaling needs
3. **Test Scaling**: Regularly test scaling scenarios under load
4. **Plan for Peak Load**: Consider peak usage patterns and seasonal variations
5. **Automate Scaling**: Use auto-scaling to respond quickly to load changes

### Common Pitfalls

- **Over-provisioning**: Wasting resources on unused capacity
- **Under-provisioning**: Causing performance issues during peak load
- **Ignoring Dependencies**: Scaling application without considering database/MQTT broker limits
- **Missing Monitoring**: Scaling without proper metrics and alerting
- **State Management**: Not considering stateful operations when scaling horizontally

### Resource Planning

```python
# planning/capacity_planning.py
class CapacityPlanner:
    """Tool for capacity planning and scaling decisions"""
    
    def __init__(self):
        self.baseline_metrics = {
            'messages_per_instance': 1000,  # Messages/hour per instance
            'cpu_per_message': 0.01,        # CPU seconds per message
            'memory_per_message': 0.1,      # MB per message
            'db_connections_per_instance': 5,
        }
    
    def calculate_required_instances(self, expected_messages_per_hour: int) -> dict:
        """Calculate required instances for expected load"""
        
        # Calculate based on message throughput
        throughput_instances = expected_messages_per_hour / self.baseline_metrics['messages_per_instance']
        
        # Calculate based on CPU
        cpu_hours = (expected_messages_per_hour * self.baseline_metrics['cpu_per_message']) / 3600
        cpu_instances = cpu_hours / 1.0  # Assume 1 CPU hour per instance
        
        # Calculate based on memory
        memory_mb = expected_messages_per_hour * self.baseline_metrics['memory_per_message']
        memory_instances = memory_mb / 512  # Assume 512MB per instance
        
        # Use the maximum requirement
        required_instances = max(throughput_instances, cpu_instances, memory_instances)
        
        # Add safety margin
        recommended_instances = int(required_instances * 1.2)  # 20% safety margin
        
        return {
            'expected_load': expected_messages_per_hour,
            'throughput_instances': throughput_instances,
            'cpu_instances': cpu_instances,
            'memory_instances': memory_instances,
            'recommended_instances': max(1, recommended_instances),
            'safety_margin': 0.2
        }
```

## Next Steps

- [Load Balancing](load-balancing.md) - Distribute traffic across scaled instances
- [Security](security.md) - Secure your scaled deployment
- [Monitoring](../monitoring/README.md) - Monitor your scaled infrastructure
- [Production Configuration](production-config.md) - Optimize configuration for scaling
