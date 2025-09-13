# API Gateway

This guide demonstrates how to implement RouteMQ as an API gateway for microservices, providing routing, authentication, rate limiting, and service orchestration.

## Overview

The API Gateway implementation handles:
- Request routing to microservices
- Authentication and authorization
- Rate limiting and throttling
- Request/response transformation
- Service discovery and load balancing
- Circuit breaker patterns
- API versioning
- Logging and monitoring

## Architecture

```
Client -> API Gateway (RouteMQ) -> Microservices
                                -> User Service
                                -> Order Service
                                -> Payment Service
                                -> Notification Service
```

## Gateway Router Setup

```python
# app/routers/api_gateway.py
from core.router import Router
from app.controllers.gateway_controller import GatewayController
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.cors import CORSMiddleware
from app.middleware.request_transform import RequestTransformMiddleware
from app.middleware.circuit_breaker import CircuitBreakerMiddleware

router = Router()

# Gateway middleware stack
auth = AuthMiddleware()
rate_limit = RateLimitMiddleware(max_requests=1000, window_seconds=60)
cors = CORSMiddleware()
transform = RequestTransformMiddleware()
circuit_breaker = CircuitBreakerMiddleware()

# API Gateway routes
with router.group(prefix="api/v1", middleware=[cors, auth, rate_limit, transform]) as api_v1:
    
    # User service routes
    with api_v1.group(prefix="users", middleware=[circuit_breaker]) as users:
        users.on("create", GatewayController.route_to_user_service, qos=2)
        users.on("get/{user_id}", GatewayController.route_to_user_service, qos=1)
        users.on("update/{user_id}", GatewayController.route_to_user_service, qos=2)
        users.on("delete/{user_id}", GatewayController.route_to_user_service, qos=2)
        users.on("list", GatewayController.route_to_user_service, qos=1)
    
    # Order service routes
    with api_v1.group(prefix="orders", middleware=[circuit_breaker]) as orders:
        orders.on("create", GatewayController.route_to_order_service, qos=2)
        orders.on("get/{order_id}", GatewayController.route_to_order_service, qos=1)
        orders.on("update/{order_id}", GatewayController.route_to_order_service, qos=2)
        orders.on("cancel/{order_id}", GatewayController.route_to_order_service, qos=2)
        orders.on("list/{user_id}", GatewayController.route_to_order_service, qos=1)
    
    # Payment service routes
    with api_v1.group(prefix="payments", middleware=[circuit_breaker]) as payments:
        payments.on("process", GatewayController.route_to_payment_service, qos=2)
        payments.on("refund/{payment_id}", GatewayController.route_to_payment_service, qos=2)
        payments.on("status/{payment_id}", GatewayController.route_to_payment_service, qos=1)
    
    # Notification service routes
    with api_v1.group(prefix="notifications", middleware=[circuit_breaker]) as notifications:
        notifications.on("send", GatewayController.route_to_notification_service, qos=1)
        notifications.on("templates/{template_id}", GatewayController.route_to_notification_service, qos=1)

# API v2 routes (newer version)
with router.group(prefix="api/v2", middleware=[cors, auth, rate_limit]) as api_v2:
    api_v2.on("users/{action}", GatewayController.route_to_user_service_v2, qos=1)
    api_v2.on("orders/{action}", GatewayController.route_to_order_service_v2, qos=1)

# Health check and service discovery
with router.group(prefix="gateway") as gateway:
    gateway.on("health", GatewayController.health_check, qos=0)
    gateway.on("services", GatewayController.list_services, qos=1)
    gateway.on("metrics", GatewayController.get_metrics, qos=1)
```

## Gateway Controller Implementation

```python
# app/controllers/gateway_controller.py
from core.controller import Controller
from core.redis_manager import redis_manager
from app.services.service_discovery import ServiceDiscovery
from app.services.load_balancer import LoadBalancer
from app.services.circuit_breaker import CircuitBreaker
import json
import time
import uuid
import asyncio
import aiohttp
from typing import Dict, Any, Optional

class GatewayController(Controller):
    
    @staticmethod
    async def route_to_user_service(payload: Dict[str, Any], client, **kwargs):
        """Route requests to user microservice"""
        return await GatewayController._route_to_service(
            service_name="user-service",
            payload=payload,
            client=client,
            **kwargs
        )
    
    @staticmethod
    async def route_to_order_service(payload: Dict[str, Any], client, **kwargs):
        """Route requests to order microservice"""
        return await GatewayController._route_to_service(
            service_name="order-service",
            payload=payload,
            client=client,
            **kwargs
        )
    
    @staticmethod
    async def route_to_payment_service(payload: Dict[str, Any], client, **kwargs):
        """Route requests to payment microservice"""
        return await GatewayController._route_to_service(
            service_name="payment-service",
            payload=payload,
            client=client,
            **kwargs
        )
    
    @staticmethod
    async def route_to_notification_service(payload: Dict[str, Any], client, **kwargs):
        """Route requests to notification microservice"""
        return await GatewayController._route_to_service(
            service_name="notification-service",
            payload=payload,
            client=client,
            **kwargs
        )
    
    @staticmethod
    async def _route_to_service(service_name: str, payload: Dict[str, Any], client, **kwargs):
        """Generic service routing with load balancing and circuit breaker"""
        try:
            request_id = str(uuid.uuid4())
            start_time = time.time()
            
            # Extract request context
            context = kwargs.get('context', {})
            path_params = context.get('path_params', {})
            headers = context.get('headers', {})
            method = context.get('method', 'POST')
            
            # Get service instance from service discovery
            service_instance = await ServiceDiscovery.get_service_instance(service_name)
            if not service_instance:
                raise Exception(f"No available instances for service {service_name}")
            
            # Check circuit breaker
            circuit_breaker = CircuitBreaker(service_name)
            if circuit_breaker.is_open():
                raise Exception(f"Circuit breaker is open for service {service_name}")
            
            # Prepare request
            service_url = f"{service_instance['url']}{context.get('path', '')}"
            request_headers = {
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
                "X-Gateway-Service": service_name,
                **headers
            }
            
            # Add authentication headers if present
            if context.get('user_id'):
                request_headers["X-User-ID"] = context['user_id']
            if context.get('auth_token'):
                request_headers["Authorization"] = f"Bearer {context['auth_token']}"
            
            # Log request
            await GatewayController._log_request(request_id, service_name, service_url, payload)
            
            # Make HTTP request to microservice
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=service_url,
                    json=payload,
                    headers=request_headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                    
                    # Record success in circuit breaker
                    circuit_breaker.record_success()
                    
                    # Log response
                    processing_time = time.time() - start_time
                    await GatewayController._log_response(
                        request_id, 
                        service_name, 
                        response.status, 
                        processing_time
                    )
                    
                    # Update service metrics
                    await GatewayController._update_service_metrics(
                        service_name, 
                        response.status, 
                        processing_time
                    )
                    
                    if response.status >= 400:
                        circuit_breaker.record_failure()
                        raise Exception(f"Service error: {response.status} - {response_data}")
                    
                    return {
                        "status": "success",
                        "data": response_data,
                        "request_id": request_id,
                        "service": service_name,
                        "processing_time": processing_time
                    }
            
        except Exception as e:
            # Record failure in circuit breaker
            if 'circuit_breaker' in locals():
                circuit_breaker.record_failure()
            
            # Log error
            await GatewayController._log_error(request_id, service_name, str(e))
            
            # Try fallback service if available
            fallback_response = await GatewayController._try_fallback(service_name, payload)
            if fallback_response:
                return fallback_response
            
            raise
    
    @staticmethod
    async def route_to_user_service_v2(action: str, payload: Dict[str, Any], client, **kwargs):
        """Route to user service v2 with enhanced features"""
        try:
            # API v2 specific transformations
            payload = await GatewayController._transform_payload_v2(payload, action)
            
            # Route to appropriate v2 endpoint
            context = kwargs.get('context', {})
            context['path'] = f"/v2/users/{action}"
            kwargs['context'] = context
            
            return await GatewayController._route_to_service(
                service_name="user-service-v2",
                payload=payload,
                client=client,
                **kwargs
            )
            
        except Exception as e:
            print(f"Error routing to user service v2: {e}")
            raise
    
    @staticmethod
    async def health_check(payload: Dict[str, Any], client):
        """API Gateway health check"""
        try:
            gateway_status = {
                "status": "healthy",
                "timestamp": time.time(),
                "version": "1.0.0"
            }
            
            # Check service health
            services_health = await ServiceDiscovery.check_all_services_health()
            gateway_status["services"] = services_health
            
            # Check Redis connectivity
            try:
                await redis_manager.ping()
                gateway_status["redis"] = "healthy"
            except Exception:
                gateway_status["redis"] = "unhealthy"
                gateway_status["status"] = "degraded"
            
            return gateway_status
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }
    
    @staticmethod
    async def list_services(payload: Dict[str, Any], client):
        """List all registered services"""
        try:
            services = await ServiceDiscovery.list_all_services()
            
            return {
                "status": "success",
                "services": services,
                "count": len(services),
                "timestamp": time.time()
            }
            
        except Exception as e:
            print(f"Error listing services: {e}")
            raise
    
    @staticmethod
    async def get_metrics(payload: Dict[str, Any], client):
        """Get API Gateway metrics"""
        try:
            # Get request metrics
            total_requests = await redis_manager.get("metrics:gateway:total_requests") or 0
            successful_requests = await redis_manager.get("metrics:gateway:successful_requests") or 0
            failed_requests = await redis_manager.get("metrics:gateway:failed_requests") or 0
            
            # Get service metrics
            service_metrics = {}
            services = await ServiceDiscovery.list_all_services()
            
            for service in services:
                service_name = service["name"]
                service_metrics[service_name] = {
                    "total_requests": await redis_manager.get(f"metrics:service:{service_name}:requests") or 0,
                    "avg_response_time": await redis_manager.get(f"metrics:service:{service_name}:avg_time") or 0,
                    "error_rate": await redis_manager.get(f"metrics:service:{service_name}:error_rate") or 0
                }
            
            # Get rate limiting metrics
            rate_limit_hits = await redis_manager.get("metrics:gateway:rate_limit_hits") or 0
            
            return {
                "gateway": {
                    "total_requests": int(total_requests),
                    "successful_requests": int(successful_requests),
                    "failed_requests": int(failed_requests),
                    "success_rate": (int(successful_requests) / max(int(total_requests), 1)) * 100,
                    "rate_limit_hits": int(rate_limit_hits)
                },
                "services": service_metrics,
                "timestamp": time.time()
            }
            
        except Exception as e:
            print(f"Error getting metrics: {e}")
            raise
    
    # Helper methods
    @staticmethod
    async def _log_request(request_id: str, service_name: str, url: str, payload: Dict[str, Any]):
        """Log incoming request"""
        log_entry = {
            "request_id": request_id,
            "service": service_name,
            "url": url,
            "payload_size": len(json.dumps(payload)),
            "timestamp": time.time()
        }
        
        await redis_manager.lpush("gateway:request_logs", json.dumps(log_entry))
        await redis_manager.ltrim("gateway:request_logs", 0, 999)  # Keep last 1000 logs
        await redis_manager.incr("metrics:gateway:total_requests")
    
    @staticmethod
    async def _log_response(request_id: str, service_name: str, status_code: int, processing_time: float):
        """Log service response"""
        log_entry = {
            "request_id": request_id,
            "service": service_name,
            "status_code": status_code,
            "processing_time": processing_time,
            "timestamp": time.time()
        }
        
        await redis_manager.lpush("gateway:response_logs", json.dumps(log_entry))
        await redis_manager.ltrim("gateway:response_logs", 0, 999)
        
        if status_code < 400:
            await redis_manager.incr("metrics:gateway:successful_requests")
        else:
            await redis_manager.incr("metrics:gateway:failed_requests")
    
    @staticmethod
    async def _log_error(request_id: str, service_name: str, error_message: str):
        """Log error"""
        error_entry = {
            "request_id": request_id,
            "service": service_name,
            "error": error_message,
            "timestamp": time.time()
        }
        
        await redis_manager.lpush("gateway:error_logs", json.dumps(error_entry))
        await redis_manager.ltrim("gateway:error_logs", 0, 999)
        await redis_manager.incr("metrics:gateway:failed_requests")
    
    @staticmethod
    async def _update_service_metrics(service_name: str, status_code: int, processing_time: float):
        """Update service performance metrics"""
        await redis_manager.incr(f"metrics:service:{service_name}:requests")
        
        # Update average response time (simplified)
        current_avg = float(await redis_manager.get(f"metrics:service:{service_name}:avg_time") or 0)
        total_requests = int(await redis_manager.get(f"metrics:service:{service_name}:requests") or 1)
        new_avg = ((current_avg * (total_requests - 1)) + processing_time) / total_requests
        await redis_manager.set(f"metrics:service:{service_name}:avg_time", new_avg)
        
        # Update error rate
        if status_code >= 400:
            await redis_manager.incr(f"metrics:service:{service_name}:errors")
            error_count = int(await redis_manager.get(f"metrics:service:{service_name}:errors") or 0)
            error_rate = (error_count / total_requests) * 100
            await redis_manager.set(f"metrics:service:{service_name}:error_rate", error_rate)
    
    @staticmethod
    async def _transform_payload_v2(payload: Dict[str, Any], action: str) -> Dict[str, Any]:
        """Transform payload for API v2"""
        # Add v2 specific fields
        payload["api_version"] = "v2"
        payload["action"] = action
        
        # Transform legacy fields if present
        if "user_data" in payload:
            payload["user"] = payload.pop("user_data")
        
        return payload
    
    @staticmethod
    async def _try_fallback(service_name: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Try fallback service or cached response"""
        # Check for cached response
        cache_key = f"fallback:{service_name}:{hash(json.dumps(payload, sort_keys=True))}"
        cached_response = await redis_manager.get_json(cache_key)
        
        if cached_response:
            cached_response["source"] = "cache"
            return cached_response
        
        # Try fallback service
        fallback_service = f"{service_name}-fallback"
        fallback_instance = await ServiceDiscovery.get_service_instance(fallback_service)
        
        if fallback_instance:
            # Implement fallback logic
            return {
                "status": "fallback",
                "message": "Primary service unavailable, fallback response",
                "data": {}
            }
        
        return None
```

## Service Discovery Implementation

```python
# app/services/service_discovery.py
from core.redis_manager import redis_manager
import json
import time
import random
from typing import List, Dict, Optional

class ServiceDiscovery:
    
    @staticmethod
    async def register_service(service_name: str, instance_id: str, url: str, health_check_url: str):
        """Register a service instance"""
        instance_data = {
            "instance_id": instance_id,
            "service_name": service_name,
            "url": url,
            "health_check_url": health_check_url,
            "registered_at": time.time(),
            "last_heartbeat": time.time(),
            "status": "healthy"
        }
        
        # Store instance data
        await redis_manager.set_json(f"service:{service_name}:{instance_id}", instance_data, ex=300)
        
        # Add to service instances set
        await redis_manager.sadd(f"services:{service_name}:instances", instance_id)
        
        # Add to global services list
        await redis_manager.sadd("services:all", service_name)
    
    @staticmethod
    async def get_service_instance(service_name: str) -> Optional[Dict]:
        """Get a healthy service instance using load balancing"""
        instances = await redis_manager.smembers(f"services:{service_name}:instances")
        
        if not instances:
            return None
        
        # Filter healthy instances
        healthy_instances = []
        for instance_id in instances:
            instance_data = await redis_manager.get_json(f"service:{service_name}:{instance_id}")
            if instance_data and instance_data.get("status") == "healthy":
                healthy_instances.append(instance_data)
        
        if not healthy_instances:
            return None
        
        # Simple round-robin load balancing
        return await ServiceDiscovery._select_instance(service_name, healthy_instances)
    
    @staticmethod
    async def _select_instance(service_name: str, instances: List[Dict]) -> Dict:
        """Select instance using round-robin load balancing"""
        counter_key = f"load_balancer:{service_name}:counter"
        counter = await redis_manager.incr(counter_key)
        await redis_manager.expire(counter_key, 3600)
        
        selected_index = (counter - 1) % len(instances)
        return instances[selected_index]
    
    @staticmethod
    async def list_all_services() -> List[Dict]:
        """List all registered services"""
        service_names = await redis_manager.smembers("services:all")
        services = []
        
        for service_name in service_names:
            instances = await redis_manager.smembers(f"services:{service_name}:instances")
            healthy_count = 0
            
            for instance_id in instances:
                instance_data = await redis_manager.get_json(f"service:{service_name}:{instance_id}")
                if instance_data and instance_data.get("status") == "healthy":
                    healthy_count += 1
            
            services.append({
                "name": service_name,
                "total_instances": len(instances),
                "healthy_instances": healthy_count,
                "status": "healthy" if healthy_count > 0 else "unhealthy"
            })
        
        return services
    
    @staticmethod
    async def check_all_services_health() -> Dict[str, str]:
        """Check health of all services"""
        service_names = await redis_manager.smembers("services:all")
        health_status = {}
        
        for service_name in service_names:
            instances = await redis_manager.smembers(f"services:{service_name}:instances")
            healthy_instances = 0
            
            for instance_id in instances:
                instance_data = await redis_manager.get_json(f"service:{service_name}:{instance_id}")
                if instance_data and instance_data.get("status") == "healthy":
                    healthy_instances += 1
            
            if healthy_instances == 0:
                health_status[service_name] = "unhealthy"
            elif healthy_instances < len(instances):
                health_status[service_name] = "degraded"
            else:
                health_status[service_name] = "healthy"
        
        return health_status
```

## Circuit Breaker Implementation

```python
# app/services/circuit_breaker.py
from core.redis_manager import redis_manager
import time

class CircuitBreaker:
    def __init__(self, service_name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.key_prefix = f"circuit_breaker:{service_name}"
    
    async def is_open(self) -> bool:
        """Check if circuit breaker is open"""
        state = await redis_manager.get(f"{self.key_prefix}:state")
        
        if state == "open":
            # Check if recovery timeout has passed
            opened_at = await redis_manager.get(f"{self.key_prefix}:opened_at")
            if opened_at and (time.time() - float(opened_at)) > self.recovery_timeout:
                # Move to half-open state
                await redis_manager.set(f"{self.key_prefix}:state", "half_open")
                return False
            return True
        
        return False
    
    async def record_success(self):
        """Record successful request"""
        state = await redis_manager.get(f"{self.key_prefix}:state")
        
        if state == "half_open":
            # Success in half-open state, close circuit
            await redis_manager.set(f"{self.key_prefix}:state", "closed")
            await redis_manager.delete(f"{self.key_prefix}:failure_count")
            await redis_manager.delete(f"{self.key_prefix}:opened_at")
        elif state != "open":
            # Reset failure count on success
            await redis_manager.delete(f"{self.key_prefix}:failure_count")
    
    async def record_failure(self):
        """Record failed request"""
        state = await redis_manager.get(f"{self.key_prefix}:state")
        
        if state == "half_open":
            # Failure in half-open state, reopen circuit
            await redis_manager.set(f"{self.key_prefix}:state", "open")
            await redis_manager.set(f"{self.key_prefix}:opened_at", time.time())
            return
        
        # Increment failure count
        failure_count = await redis_manager.incr(f"{self.key_prefix}:failure_count")
        await redis_manager.expire(f"{self.key_prefix}:failure_count", 300)  # 5 minutes
        
        # Open circuit if threshold exceeded
        if failure_count >= self.failure_threshold:
            await redis_manager.set(f"{self.key_prefix}:state", "open")
            await redis_manager.set(f"{self.key_prefix}:opened_at", time.time())
```

## Usage Examples

### API Request Routing
```python
# Send to: api/v1/users/create
{
    "name": "John Doe",
    "email": "john@example.com",
    "role": "user"
}

# Response:
{
    "status": "success",
    "data": {
        "user_id": "123",
        "name": "John Doe",
        "email": "john@example.com"
    },
    "request_id": "req_456",
    "service": "user-service",
    "processing_time": 0.245
}
```

### Service Health Check
```python
# Send to: gateway/health
# Response:
{
    "status": "healthy",
    "timestamp": 1694678400,
    "version": "1.0.0",
    "services": {
        "user-service": "healthy",
        "order-service": "healthy",
        "payment-service": "degraded"
    },
    "redis": "healthy"
}
```

This API Gateway implementation provides comprehensive routing, monitoring, and resilience patterns for microservices architecture.
