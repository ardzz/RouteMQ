import re
from typing import Callable, List, Any

from .middleware import Middleware
from .observability import enrich_context, get_correlation_id, lifecycle, reset_context, snapshot_context, start_span


def _callable_name(handler: Callable) -> str:
    name = getattr(handler, '__qualname__', None)
    if isinstance(name, str):
        return name
    name = getattr(handler, '__name__', None)
    if isinstance(name, str):
        return name
    return handler.__class__.__name__


class Route:
    def __init__(
        self,
        topic: str,
        handler: Callable,
        qos: int = 0,
        middleware: List[Middleware] | None = None,
        shared: bool = False,
        worker_count: int = 1,
    ):
        self.topic = topic
        self.handler = handler
        self.qos = qos
        self.middleware = middleware or []
        self.shared = shared
        self.worker_count = worker_count if shared else 1  # Only apply worker_count for shared subscriptions
        self.pattern = self._compile_topic_pattern()
        self.mqtt_topic = self._get_mqtt_subscription_topic()

    def _compile_topic_pattern(self) -> re.Pattern:
        """Convert Laravel-style route params to regex pattern."""
        pattern = self.topic
        pattern = re.sub(r'{([^/]+)}', r'(?P<\1>[^/]+)', pattern)
        return re.compile(f'^{pattern}$')

    def _get_mqtt_subscription_topic(self) -> str:
        """Convert Laravel-style route params to MQTT subscription topic with wildcards."""
        return re.sub(r'{[^/]+}', '+', self.topic)

    def matches(self, topic: str) -> dict[str, str | Any] | None:
        """Check if a topic matches this route and extract parameters."""
        match = self.pattern.match(topic)
        if match:
            return match.groupdict()
        return None

    def get_subscription_topic(self, group_name: str | None = None) -> str:
        """Get the MQTT subscription topic, with shared prefix if needed."""
        if self.shared and group_name:
            return f'$share/{group_name}/{self.mqtt_topic}'
        return self.mqtt_topic


class RouterGroup:
    def __init__(self, router, prefix: str = '', middleware: List[Middleware] | None = None):
        self.router = router
        self.prefix = prefix
        self.middleware = middleware or []

    def on(
        self,
        topic: str,
        handler: Callable,
        qos: int = 0,
        middleware: List[Middleware] | None = None,
        shared: bool = False,
        worker_count: int = 1,
    ) -> None:
        """Register a route handler with this group's prefix and middleware."""
        full_topic = f'{self.prefix}/{topic}' if self.prefix else topic
        combined_middleware = list(self.middleware)
        if middleware:
            combined_middleware.extend(middleware)

        self.router.on(full_topic, handler, qos, combined_middleware, shared, worker_count)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Audit Accept: route groups do not suppress exceptions; None preserves propagation.
        pass


class Router:
    def __init__(self):
        self.routes: List[Route] = []

    def on(
        self,
        topic: str,
        handler: Callable,
        qos: int = 0,
        middleware: List[Middleware] | None = None,
        shared: bool = False,
        worker_count: int = 1,
    ) -> None:
        """Register a route handler."""
        route = Route(topic, handler, qos, middleware, shared, worker_count)
        self.routes.append(route)

    def group(self, prefix: str = '', middleware: List[Middleware] | None = None):
        """Create a route group with shared prefix and middleware."""
        return RouterGroup(self, prefix, middleware)

    async def dispatch(self, topic: str, payload: Any, client) -> None:
        """Find a matching route and dispatch the request through middleware to handler."""
        for route in self.routes:
            params = route.matches(topic)
            if params is not None:
                route_attributes = {
                    'route_pattern': route.topic,
                    'mqtt_subscription_topic': route.mqtt_topic,
                    'route_shared': route.shared,
                }
                context = {
                    'topic': topic,
                    'payload': payload,
                    'params': params,
                    'client': client,
                    'observability': snapshot_context(route_attributes),
                    'correlation_id': get_correlation_id(),
                    'route_pattern': route.topic,
                }
                token = enrich_context(**route_attributes)
                span_attributes = {
                    'messaging.system': 'mqtt',
                    'messaging.operation.type': 'process',
                    'messaging.destination': topic,
                    'messaging.destination.template': route.topic,
                    'routemq.route.pattern': route.topic,
                }
                handler_name = _callable_name(route.handler)

                async def execute_handler(ctx):
                    with start_span(
                        'router.handler',
                        {**span_attributes, 'routemq.handler.name': handler_name},
                        kind='internal',
                    ):
                        return await route.handler(**ctx['params'], payload=ctx['payload'], client=ctx['client'])

                handler = execute_handler

                def wrap_middleware(middleware: Middleware, next_handler: Callable) -> Callable:
                    async def middleware_handler(ctx):
                        with start_span(
                            'router.middleware',
                            {**span_attributes, 'routemq.middleware.name': middleware.__class__.__name__},
                            kind='internal',
                        ):
                            return await middleware.handle(ctx, next_handler)

                    return middleware_handler

                for middleware in reversed(route.middleware):
                    handler = wrap_middleware(middleware, handler)

                try:
                    with start_span('router.dispatch', span_attributes, kind='consumer'):
                        lifecycle('router.dispatch.started', route_attributes)
                        result = await handler(context)
                        lifecycle('router.dispatch.succeeded', route_attributes)
                    return result
                except Exception as exc:
                    lifecycle('router.dispatch.failed', {**route_attributes, 'error': exc.__class__.__name__})
                    raise
                finally:
                    reset_context(token)

        lifecycle('router.dispatch.missed', {'route_found': False})
        raise ValueError(f'No route found for topic: {topic}')

    def get_total_workers_needed(self) -> int:
        """Calculate total number of workers needed for all shared routes."""
        return max((route.worker_count for route in self.routes if route.shared), default=0)
