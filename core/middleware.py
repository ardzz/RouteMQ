from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Awaitable
import logging


class Middleware(ABC):
    """Base middleware class that all middleware should extend."""
    
    # Class-level logger that can be accessed by all middleware instances
    logger = logging.getLogger("RouteMQ.Middleware")

    @abstractmethod
    async def handle(self, context: Dict[str, Any], next_handler: Callable[[Dict[str, Any]], Awaitable[Any]]) -> Any:
        """
        Process the request context and call the next handler in chain.
        
        Args:
            context: The request context including topic, payload, params
            next_handler: The next handler in the middleware chain
            
        Returns:
            The result of the request handling
        """
        pass