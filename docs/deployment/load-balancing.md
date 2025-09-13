# Load Balancing

Distribute traffic across multiple RouteMQ instances for high availability and optimal performance.

## Load Balancing Overview

RouteMQ supports multiple load balancing strategies:

- **MQTT Broker Load Balancing**: Distribute MQTT connections
- **Application Load Balancing**: Balance HTTP/API traffic
- **Database Load Balancing**: Distribute database queries
- **Geographic Load Balancing**: Route based on location
- **Failover and High Availability**: Automatic failover mechanisms

## MQTT Load Balancing

### MQTT Broker Clustering

#### Mosquitto Cluster Setup

```yaml
# docker-compose.mqtt-cluster.yml
version: '3.8'

services:
  mosquitto-1:
    image: eclipse-mosquitto:2.0
    container_name: mosquitto-node-1
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./docker/mosquitto/node1.conf:/mosquitto/config/mosquitto.conf:ro
      - ./docker/mosquitto/cluster-key:/mosquitto/config/cluster-key:ro
      - mosquitto1_data:/mosquitto/data
    environment:
      - MOSQUITTO_NODE_ID=1
    networks:
      - mqtt-cluster

  mosquitto-2:
    image: eclipse-mosquitto:2.0
    container_name: mosquitto-node-2
    ports:
      - "1884:1883"
      - "9002:9001"
    volumes:
      - ./docker/mosquitto/node2.conf:/mosquitto/config/mosquitto.conf:ro
      - ./docker/mosquitto/cluster-key:/mosquitto/config/cluster-key:ro
      - mosquitto2_data:/mosquitto/data
    environment:
      - MOSQUITTO_NODE_ID=2
    networks:
      - mqtt-cluster

  mosquitto-3:
    image: eclipse-mosquitto:2.0
    container_name: mosquitto-node-3
    ports:
      - "1885:1883"
      - "9003:9001"
    volumes:
      - ./docker/mosquitto/node3.conf:/mosquitto/config/mosquitto.conf:ro
      - ./docker/mosquitto/cluster-key:/mosquitto/config/cluster-key:ro
      - mosquitto3_data:/mosquitto/data
    environment:
      - MOSQUITTO_NODE_ID=3
    networks:
      - mqtt-cluster

  mqtt-load-balancer:
    image: nginx:alpine
    container_name: mqtt-lb
    ports:
      - "1880:1883"  # Load balanced MQTT port
    volumes:
      - ./docker/nginx/mqtt-lb.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - mosquitto-1
      - mosquitto-2
      - mosquitto-3
    networks:
      - mqtt-cluster

volumes:
  mosquitto1_data:
  mosquitto2_data:
  mosquitto3_data:

networks:
  mqtt-cluster:
    driver: bridge
```

#### NGINX MQTT Load Balancer

```nginx
# docker/nginx/mqtt-lb.conf
events {
    worker_connections 1024;
}

stream {
    upstream mqtt_backend {
        least_conn;
        server mosquitto-1:1883 weight=1 max_fails=3 fail_timeout=30s;
        server mosquitto-2:1883 weight=1 max_fails=3 fail_timeout=30s;
        server mosquitto-3:1883 weight=1 max_fails=3 fail_timeout=30s;
    }

    upstream mqtt_websocket_backend {
        least_conn;
        server mosquitto-1:9001 weight=1;
        server mosquitto-2:9001 weight=1;
        server mosquitto-3:9001 weight=1;
    }

    # MQTT TCP Load Balancer
    server {
        listen 1883;
        proxy_pass mqtt_backend;
        proxy_timeout 3s;
        proxy_connect_timeout 1s;
        
        # Enable session persistence for MQTT
        proxy_bind $remote_addr transparent;
    }

    # MQTT WebSocket Load Balancer
    server {
        listen 9001;
        proxy_pass mqtt_websocket_backend;
        proxy_timeout 3s;
        proxy_connect_timeout 1s;
    }
}

# HTTP block for health checks
http {
    upstream mqtt_health {
        server mosquitto-1:1883;
        server mosquitto-2:1883;
        server mosquitto-3:1883;
    }

    server {
        listen 8080;
        
        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
        
        location /mqtt-status {
            proxy_pass http://mqtt_health;
            proxy_set_header Host $host;
        }
    }
}
```

#### HAProxy MQTT Load Balancer

```conf
# docker/haproxy/haproxy.cfg
global
    daemon
    maxconn 4096
    log stdout local0

defaults
    mode tcp
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms
    option tcplog
    log global

# MQTT Load Balancer
frontend mqtt_frontend
    bind *:1883
    mode tcp
    default_backend mqtt_backend

backend mqtt_backend
    mode tcp
    balance leastconn
    option tcp-check
    tcp-check send "MQTT health check"
    
    server mqtt1 mosquitto-1:1883 check inter 5s rise 2 fall 3
    server mqtt2 mosquitto-2:1883 check inter 5s rise 2 fall 3
    server mqtt3 mosquitto-3:1883 check inter 5s rise 2 fall 3

# MQTT WebSocket Load Balancer
frontend mqtt_ws_frontend
    bind *:9001
    mode tcp
    default_backend mqtt_ws_backend

backend mqtt_ws_backend
    mode tcp
    balance roundrobin
    
    server mqtt_ws1 mosquitto-1:9001 check
    server mqtt_ws2 mosquitto-2:9001 check
    server mqtt_ws3 mosquitto-3:9001 check

# Stats interface
frontend stats
    bind *:8404
    mode http
    stats enable
    stats uri /stats
    stats refresh 30s
    stats admin if TRUE
```

### Client-Side Load Balancing

```python
# core/mqtt_load_balancer.py
import random
import time
import logging
from typing import List, Dict, Optional
import paho.mqtt.client as mqtt

class MQTTLoadBalancer:
    """Client-side MQTT load balancer with failover"""
    
    def __init__(self, brokers: List[Dict[str, any]], strategy: str = "round_robin"):
        self.brokers = brokers
        self.strategy = strategy
        self.current_broker_index = 0
        self.failed_brokers = set()
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        self.logger = logging.getLogger("MQTTLoadBalancer")
    
    def get_next_broker(self) -> Dict[str, any]:
        """Get next broker based on load balancing strategy"""
        available_brokers = [
            broker for i, broker in enumerate(self.brokers)
            if i not in self.failed_brokers
        ]
        
        if not available_brokers:
            # All brokers failed, reset and try again
            self.failed_brokers.clear()
            available_brokers = self.brokers
            self.logger.warning("All brokers failed, resetting failure list")
        
        if self.strategy == "round_robin":
            return self._round_robin_selection(available_brokers)
        elif self.strategy == "random":
            return random.choice(available_brokers)
        elif self.strategy == "weighted":
            return self._weighted_selection(available_brokers)
        else:
            return available_brokers[0]
    
    def _round_robin_selection(self, brokers: List[Dict]) -> Dict:
        """Round-robin broker selection"""
        broker = brokers[self.current_broker_index % len(brokers)]
        self.current_broker_index += 1
        return broker
    
    def _weighted_selection(self, brokers: List[Dict]) -> Dict:
        """Weighted broker selection based on broker weight"""
        total_weight = sum(broker.get('weight', 1) for broker in brokers)
        random_weight = random.uniform(0, total_weight)
        
        current_weight = 0
        for broker in brokers:
            current_weight += broker.get('weight', 1)
            if random_weight <= current_weight:
                return broker
        
        return brokers[-1]  # Fallback
    
    def mark_broker_failed(self, broker: Dict):
        """Mark broker as failed"""
        broker_index = self.brokers.index(broker)
        self.failed_brokers.add(broker_index)
        self.logger.warning(f"Marked broker as failed: {broker['host']}:{broker['port']}")
    
    async def health_check_brokers(self):
        """Perform health checks on failed brokers"""
        if time.time() - self.last_health_check < self.health_check_interval:
            return
        
        self.last_health_check = time.time()
        
        for broker_index in list(self.failed_brokers):
            broker = self.brokers[broker_index]
            
            if await self._check_broker_health(broker):
                self.failed_brokers.remove(broker_index)
                self.logger.info(f"Broker recovered: {broker['host']}:{broker['port']}")
    
    async def _check_broker_health(self, broker: Dict) -> bool:
        """Check if a broker is healthy"""
        try:
            client = mqtt.Client(f"health_check_{int(time.time())}")
            client.connect(broker['host'], broker['port'], 10)
            client.disconnect()
            return True
        except Exception as e:
            self.logger.debug(f"Health check failed for {broker['host']}: {e}")
            return False

class RouteMQMQTTClient:
    """RouteMQ MQTT client with load balancing"""
    
    def __init__(self, brokers: List[Dict], client_id: str = None):
        self.load_balancer = MQTTLoadBalancer(brokers)
        self.client_id = client_id or f"routemq_{int(time.time())}"
        self.client = None
        self.current_broker = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.logger = logging.getLogger("RouteMQMQTTClient")
    
    async def connect(self) -> bool:
        """Connect to MQTT broker with load balancing"""
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                # Health check brokers
                await self.load_balancer.health_check_brokers()
                
                # Get next broker
                self.current_broker = self.load_balancer.get_next_broker()
                
                # Create new client
                self.client = mqtt.Client(self.client_id)
                self._setup_client_callbacks()
                
                # Connect
                self.client.connect(
                    self.current_broker['host'],
                    self.current_broker['port'],
                    60
                )
                
                self.logger.info(f"Connected to {self.current_broker['host']}:{self.current_broker['port']}")
                self.reconnect_attempts = 0
                return True
                
            except Exception as e:
                self.logger.error(f"Connection failed: {e}")
                self.load_balancer.mark_broker_failed(self.current_broker)
                self.reconnect_attempts += 1
                
                # Exponential backoff
                await asyncio.sleep(2 ** self.reconnect_attempts)
        
        self.logger.error("Max reconnection attempts reached")
        return False
    
    def _setup_client_callbacks(self):
        """Setup MQTT client callbacks"""
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle connection event"""
        if rc == 0:
            self.logger.info("MQTT connected successfully")
        else:
            self.logger.error(f"MQTT connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Handle disconnection event"""
        self.logger.warning(f"MQTT disconnected with code {rc}")
        
        if rc != 0:  # Unexpected disconnection
            self.load_balancer.mark_broker_failed(self.current_broker)
            asyncio.create_task(self.connect())  # Reconnect
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming message"""
        # Delegate to application message handler
        pass
```

## Application Load Balancing

### HTTP API Load Balancing

```nginx
# docker/nginx/app-lb.conf
upstream routemq_backend {
    least_conn;
    server routemq-1:8080 weight=1 max_fails=3 fail_timeout=30s;
    server routemq-2:8080 weight=1 max_fails=3 fail_timeout=30s;
    server routemq-3:8080 weight=1 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name api.routemq.com;

    # Health check endpoint
    location /health {
        proxy_pass http://routemq_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 1s;
        proxy_timeout 3s;
    }

    # API endpoints
    location /api/ {
        proxy_pass http://routemq_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Connection pooling
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        # Timeouts
        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
    }

    # Sticky sessions for WebSocket connections
    location /ws/ {
        proxy_pass http://routemq_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        
        # Session affinity
        ip_hash;
    }
}
```

### Kubernetes Service Load Balancing

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: routemq-service
  namespace: production
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
    service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled: "true"
spec:
  selector:
    app: routemq
  ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
  - name: mqtt
    port: 1883
    targetPort: 1883
    protocol: TCP
  type: LoadBalancer
  sessionAffinity: None  # Or "ClientIP" for session persistence

---
apiVersion: v1
kind: Service
metadata:
  name: routemq-internal
  namespace: production
spec:
  selector:
    app: routemq
  ports:
  - name: http
    port: 8080
    targetPort: 8080
  type: ClusterIP
  sessionAffinity: None

---
# Ingress for HTTP traffic
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: routemq-ingress
  namespace: production
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.ingress.kubernetes.io/upstream-hash-by: "$request_uri"
    nginx.ingress.kubernetes.io/load-balance: "ewma"
spec:
  rules:
  - host: api.routemq.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: routemq-internal
            port:
              number: 8080
```

## Database Load Balancing

### Read/Write Split

```python
# core/database_load_balancer.py
import random
import asyncio
import logging
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

class DatabaseLoadBalancer:
    """Database load balancer with read/write splitting"""
    
    def __init__(self, write_config: Dict, read_configs: List[Dict]):
        self.write_engine = create_async_engine(**write_config)
        self.read_engines = [
            create_async_engine(**config) for config in read_configs
        ]
        self.read_engine_index = 0
        self.failed_read_engines = set()
        self.logger = logging.getLogger("DatabaseLoadBalancer")
        
        # Create session factories
        self.write_session_factory = sessionmaker(
            self.write_engine, class_=AsyncSession, expire_on_commit=False
        )
        self.read_session_factories = [
            sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            for engine in self.read_engines
        ]
    
    async def get_write_session(self) -> AsyncSession:
        """Get session for write operations"""
        return self.write_session_factory()
    
    async def get_read_session(self) -> AsyncSession:
        """Get session for read operations with load balancing"""
        available_engines = [
            i for i, engine in enumerate(self.read_engines)
            if i not in self.failed_read_engines
        ]
        
        if not available_engines:
            # All read replicas failed, use write engine
            self.logger.warning("All read replicas failed, using write engine")
            return self.write_session_factory()
        
        # Round-robin selection
        engine_index = available_engines[self.read_engine_index % len(available_engines)]
        self.read_engine_index += 1
        
        try:
            session = self.read_session_factories[engine_index]()
            return session
        except Exception as e:
            self.logger.error(f"Failed to create read session: {e}")
            self.failed_read_engines.add(engine_index)
            return await self.get_read_session()  # Retry with different engine
    
    async def health_check_read_engines(self):
        """Health check for read engines"""
        for engine_index in list(self.failed_read_engines):
            try:
                engine = self.read_engines[engine_index]
                async with engine.connect() as conn:
                    await conn.execute("SELECT 1")
                
                # Engine is healthy, remove from failed list
                self.failed_read_engines.remove(engine_index)
                self.logger.info(f"Read engine {engine_index} recovered")
                
            except Exception as e:
                self.logger.debug(f"Read engine {engine_index} still failing: {e}")

# Usage in models
class DatabaseRouter:
    """Route database operations to appropriate engines"""
    
    def __init__(self, load_balancer: DatabaseLoadBalancer):
        self.load_balancer = load_balancer
    
    async def execute_read_query(self, query):
        """Execute read-only query"""
        session = await self.load_balancer.get_read_session()
        try:
            result = await session.execute(query)
            return result
        finally:
            await session.close()
    
    async def execute_write_query(self, query):
        """Execute write query"""
        session = await self.load_balancer.get_write_session()
        try:
            result = await session.execute(query)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Database Connection Pooling

```python
# core/connection_pool_manager.py
import asyncio
import time
from typing import Dict, List
from sqlalchemy.ext.asyncio import create_async_engine

class ConnectionPoolManager:
    """Manage database connection pools across multiple databases"""
    
    def __init__(self):
        self.pools = {}
        self.pool_stats = {}
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
    
    async def create_pool(self, name: str, connection_string: str, **kwargs):
        """Create a named connection pool"""
        pool_config = {
            'pool_size': kwargs.get('pool_size', 10),
            'max_overflow': kwargs.get('max_overflow', 20),
            'pool_timeout': kwargs.get('pool_timeout', 30),
            'pool_recycle': kwargs.get('pool_recycle', 3600),
            'pool_pre_ping': True,
            **kwargs
        }
        
        engine = create_async_engine(connection_string, **pool_config)
        self.pools[name] = engine
        self.pool_stats[name] = {
            'created': time.time(),
            'queries': 0,
            'errors': 0,
            'avg_response_time': 0
        }
        
        return engine
    
    def get_pool(self, name: str):
        """Get connection pool by name"""
        return self.pools.get(name)
    
    async def get_least_busy_pool(self, pool_names: List[str]):
        """Get the least busy pool from a list"""
        min_active = float('inf')
        selected_pool = None
        
        for name in pool_names:
            if name in self.pools:
                pool = self.pools[name].pool
                active_connections = pool.checkedout()
                
                if active_connections < min_active:
                    min_active = active_connections
                    selected_pool = self.pools[name]
        
        return selected_pool or self.pools[pool_names[0]]
    
    async def record_query_stats(self, pool_name: str, response_time: float, success: bool):
        """Record query statistics"""
        if pool_name in self.pool_stats:
            stats = self.pool_stats[pool_name]
            stats['queries'] += 1
            
            if not success:
                stats['errors'] += 1
            
            # Update average response time
            current_avg = stats['avg_response_time']
            total_queries = stats['queries']
            stats['avg_response_time'] = (current_avg * (total_queries - 1) + response_time) / total_queries
    
    async def cleanup_idle_connections(self):
        """Clean up idle connections periodically"""
        if time.time() - self.last_cleanup < self.cleanup_interval:
            return
        
        for name, engine in self.pools.items():
            try:
                # Force pool cleanup
                await engine.dispose()
                self.logger.info(f"Cleaned up connections for pool: {name}")
            except Exception as e:
                self.logger.error(f"Failed to cleanup pool {name}: {e}")
        
        self.last_cleanup = time.time()
```

## Geographic Load Balancing

### DNS-Based Geographic Routing

```yaml
# DNS configuration for geographic load balancing
# This would be configured in your DNS provider (Route 53, CloudFlare, etc.)

# Primary regions
api-us-east.routemq.com:
  type: A
  records:
    - 54.123.45.67  # US East load balancer
  
api-us-west.routemq.com:
  type: A
  records:
    - 34.567.89.12  # US West load balancer

api-eu.routemq.com:
  type: A
  records:
    - 52.234.56.78  # EU load balancer

api-asia.routemq.com:
  type: A
  records:
    - 13.345.67.89  # Asia load balancer

# Geographic routing
api.routemq.com:
  type: CNAME
  geolocation_routing:
    - continent: "NA"
      country: "US"
      subdivision: "us-east-1"
      target: "api-us-east.routemq.com"
    - continent: "NA"
      country: "US"
      subdivision: "us-west-1"
      target: "api-us-west.routemq.com"
    - continent: "EU"
      target: "api-eu.routemq.com"
    - continent: "AS"
      target: "api-asia.routemq.com"
    - default: "api-us-east.routemq.com"  # Fallback
```

### Application-Level Geographic Routing

```python
# core/geo_load_balancer.py
import geoip2.database
import logging
from typing import Dict, List, Optional

class GeographicLoadBalancer:
    """Geographic load balancer based on client location"""
    
    def __init__(self, geoip_database_path: str):
        self.reader = geoip2.database.Reader(geoip_database_path)
        self.region_endpoints = {
            'us-east': {
                'mqtt_brokers': ['mqtt1.us-east.routemq.com:1883'],
                'api_endpoints': ['api1.us-east.routemq.com'],
                'database': 'db.us-east.routemq.com'
            },
            'us-west': {
                'mqtt_brokers': ['mqtt1.us-west.routemq.com:1883'],
                'api_endpoints': ['api1.us-west.routemq.com'],
                'database': 'db.us-west.routemq.com'
            },
            'eu': {
                'mqtt_brokers': ['mqtt1.eu.routemq.com:1883'],
                'api_endpoints': ['api1.eu.routemq.com'],
                'database': 'db.eu.routemq.com'
            },
            'asia': {
                'mqtt_brokers': ['mqtt1.asia.routemq.com:1883'],
                'api_endpoints': ['api1.asia.routemq.com'],
                'database': 'db.asia.routemq.com'
            }
        }
        self.logger = logging.getLogger("GeographicLoadBalancer")
    
    def get_region_for_ip(self, ip_address: str) -> str:
        """Determine region based on IP address"""
        try:
            response = self.reader.city(ip_address)
            continent = response.continent.code
            country = response.country.iso_code
            
            # Simple region mapping
            if continent == 'NA' and country == 'US':
                # Could add more sophisticated logic based on state/coordinates
                return 'us-east'  # Default to us-east
            elif continent == 'NA':
                return 'us-east'
            elif continent == 'EU':
                return 'eu'
            elif continent == 'AS':
                return 'asia'
            else:
                return 'us-east'  # Default fallback
                
        except Exception as e:
            self.logger.error(f"GeoIP lookup failed for {ip_address}: {e}")
            return 'us-east'  # Default fallback
    
    def get_endpoints_for_region(self, region: str) -> Dict:
        """Get service endpoints for a region"""
        return self.region_endpoints.get(region, self.region_endpoints['us-east'])
    
    def get_optimal_endpoints(self, client_ip: str) -> Dict:
        """Get optimal endpoints for client"""
        region = self.get_region_for_ip(client_ip)
        endpoints = self.get_endpoints_for_region(region)
        
        self.logger.info(f"Routing client {client_ip} to region {region}")
        return {
            'region': region,
            'endpoints': endpoints
        }
```

## Health Checks and Failover

### Advanced Health Monitoring

```python
# monitoring/health_monitor.py
import asyncio
import time
import logging
from typing import Dict, List, Callable
from dataclasses import dataclass

@dataclass
class HealthCheck:
    name: str
    check_function: Callable
    interval: int
    timeout: int
    retries: int
    critical: bool = False

class HealthMonitor:
    """Advanced health monitoring with automatic failover"""
    
    def __init__(self):
        self.health_checks = {}
        self.health_status = {}
        self.failover_callbacks = {}
        self.logger = logging.getLogger("HealthMonitor")
        self.running = False
    
    def register_health_check(self, check: HealthCheck):
        """Register a health check"""
        self.health_checks[check.name] = check
        self.health_status[check.name] = {
            'status': 'unknown',
            'last_check': 0,
            'consecutive_failures': 0,
            'last_error': None
        }
    
    def register_failover_callback(self, service_name: str, callback: Callable):
        """Register callback for service failover"""
        self.failover_callbacks[service_name] = callback
    
    async def start_monitoring(self):
        """Start health monitoring"""
        self.running = True
        tasks = []
        
        for check_name, check in self.health_checks.items():
            task = asyncio.create_task(self._monitor_service(check_name, check))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
    
    async def _monitor_service(self, check_name: str, check: HealthCheck):
        """Monitor a specific service"""
        while self.running:
            try:
                # Perform health check with timeout
                start_time = time.time()
                
                health_result = await asyncio.wait_for(
                    check.check_function(),
                    timeout=check.timeout
                )
                
                response_time = time.time() - start_time
                
                # Update health status
                self.health_status[check_name].update({
                    'status': 'healthy' if health_result else 'unhealthy',
                    'last_check': time.time(),
                    'consecutive_failures': 0 if health_result else self.health_status[check_name]['consecutive_failures'] + 1,
                    'response_time': response_time,
                    'last_error': None
                })
                
                # Check if failover is needed
                if not health_result and self.health_status[check_name]['consecutive_failures'] >= check.retries:
                    await self._trigger_failover(check_name, check)
                
            except asyncio.TimeoutError:
                self.logger.error(f"Health check timeout for {check_name}")
                self._mark_service_unhealthy(check_name, "timeout")
                
            except Exception as e:
                self.logger.error(f"Health check error for {check_name}: {e}")
                self._mark_service_unhealthy(check_name, str(e))
            
            await asyncio.sleep(check.interval)
    
    def _mark_service_unhealthy(self, check_name: str, error: str):
        """Mark service as unhealthy"""
        self.health_status[check_name].update({
            'status': 'unhealthy',
            'last_check': time.time(),
            'consecutive_failures': self.health_status[check_name]['consecutive_failures'] + 1,
            'last_error': error
        })
    
    async def _trigger_failover(self, check_name: str, check: HealthCheck):
        """Trigger failover for failed service"""
        if check.critical and check_name in self.failover_callbacks:
            self.logger.critical(f"Triggering failover for critical service: {check_name}")
            
            try:
                await self.failover_callbacks[check_name]()
            except Exception as e:
                self.logger.error(f"Failover callback failed for {check_name}: {e}")
    
    def get_health_summary(self) -> Dict:
        """Get summary of all health checks"""
        healthy_services = sum(1 for status in self.health_status.values() if status['status'] == 'healthy')
        total_services = len(self.health_status)
        
        return {
            'overall_status': 'healthy' if healthy_services == total_services else 'degraded',
            'healthy_services': healthy_services,
            'total_services': total_services,
            'services': self.health_status.copy()
        }

# Usage example
async def mqtt_health_check():
    """Health check for MQTT broker"""
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client("health_check")
        client.connect("mqtt.example.com", 1883, 10)
        client.disconnect()
        return True
    except:
        return False

async def database_health_check():
    """Health check for database"""
    try:
        from core.model import Model
        session = await Model.get_session()
        await session.execute("SELECT 1")
        await session.close()
        return True
    except:
        return False

# Setup health monitoring
health_monitor = HealthMonitor()

# Register health checks
health_monitor.register_health_check(HealthCheck(
    name="mqtt_broker",
    check_function=mqtt_health_check,
    interval=30,
    timeout=10,
    retries=3,
    critical=True
))

health_monitor.register_health_check(HealthCheck(
    name="database",
    check_function=database_health_check,
    interval=60,
    timeout=15,
    retries=2,
    critical=True
))
```

## Load Balancing Best Practices

### Configuration Guidelines

1. **Health Checks**: Always implement comprehensive health checks
2. **Graceful Degradation**: Plan for partial service failures
3. **Session Persistence**: Use sticky sessions when needed
4. **Connection Pooling**: Optimize connection reuse
5. **Monitoring**: Monitor load balancer performance
6. **Failover Speed**: Minimize failover detection time

### Performance Optimization

```python
# config/load_balancer_optimization.py
class LoadBalancerOptimization:
    """Optimization settings for load balancers"""
    
    # Connection settings
    CONNECTION_SETTINGS = {
        'keep_alive': True,
        'keep_alive_timeout': 65,
        'max_connections': 1000,
        'connection_timeout': 30,
        'idle_timeout': 300,
    }
    
    # Health check settings
    HEALTH_CHECK_SETTINGS = {
        'interval': 30,  # seconds
        'timeout': 10,   # seconds
        'healthy_threshold': 2,
        'unhealthy_threshold': 3,
    }
    
    # Load balancing algorithms
    ALGORITHMS = {
        'round_robin': 'Equal distribution',
        'least_connections': 'Route to least busy',
        'weighted_round_robin': 'Based on server capacity',
        'ip_hash': 'Session persistence',
        'least_response_time': 'Performance-based routing',
    }
```

### Monitoring and Alerting

```python
# monitoring/load_balancer_metrics.py
class LoadBalancerMetrics:
    """Metrics collection for load balancers"""
    
    def __init__(self):
        self.metrics = {
            'total_requests': 0,
            'failed_requests': 0,
            'average_response_time': 0,
            'active_connections': 0,
            'backend_errors': {},
            'failover_events': 0,
        }
    
    def record_request(self, backend: str, response_time: float, success: bool):
        """Record request metrics"""
        self.metrics['total_requests'] += 1
        
        if not success:
            self.metrics['failed_requests'] += 1
            if backend not in self.metrics['backend_errors']:
                self.metrics['backend_errors'][backend] = 0
            self.metrics['backend_errors'][backend] += 1
        
        # Update average response time
        current_avg = self.metrics['average_response_time']
        total_requests = self.metrics['total_requests']
        self.metrics['average_response_time'] = (
            (current_avg * (total_requests - 1) + response_time) / total_requests
        )
    
    def record_failover(self):
        """Record failover event"""
        self.metrics['failover_events'] += 1
    
    def get_health_score(self) -> float:
        """Calculate health score (0-100)"""
        if self.metrics['total_requests'] == 0:
            return 100.0
        
        success_rate = (
            (self.metrics['total_requests'] - self.metrics['failed_requests']) / 
            self.metrics['total_requests']
        ) * 100
        
        # Penalize high response times
        response_penalty = min(self.metrics['average_response_time'] / 10, 20)
        
        # Penalize failovers
        failover_penalty = min(self.metrics['failover_events'] * 5, 30)
        
        return max(0, success_rate - response_penalty - failover_penalty)
```

## Next Steps

- [Security](security.md) - Secure your load-balanced deployment
- [Monitoring](../monitoring/README.md) - Monitor load balancer performance
- [Scaling](scaling.md) - Scale your load-balanced infrastructure
- [Production Configuration](production-config.md) - Optimize for production use
