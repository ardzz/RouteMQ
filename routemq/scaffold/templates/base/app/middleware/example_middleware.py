import time
from typing import Any, Awaitable, Callable, Dict

from routemq.middleware import Middleware


class LoggingMiddleware(Middleware):
    """Example middleware that logs request information and timing."""

    async def handle(self, context: Dict[str, Any], next_handler: Callable[[Dict[str, Any]], Awaitable[Any]]) -> Any:
        """Log request details and execution time."""
        topic = context.get('topic', 'unknown')
        client_id = context.get('client', {})._client_id if 'client' in context else 'unknown'

        self.logger.info(f'[INCOMING] Topic: {topic}, Client: {client_id}')
        start_time = time.time()

        try:
            result = await next_handler(context)
            execution_time = (time.time() - start_time) * 1000
            self.logger.info(f'[COMPLETED] Topic: {topic}, Execution time: {execution_time:.2f}ms')
            return result
        except Exception as exc:
            execution_time = (time.time() - start_time) * 1000
            self.logger.error(f'[ERROR] Topic: {topic}, Error: {exc}, Execution time: {execution_time:.2f}ms')
            raise
