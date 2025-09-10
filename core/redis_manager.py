import asyncio
import logging
import os
from typing import Optional, Union, Any, Dict
import json

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None


class RedisManager:
    """
    Redis integration manager for the RouteMQ framework.
    Provides async Redis operations with connection pooling and error handling.
    """

    _instance: Optional['RedisManager'] = None
    _redis_pool: Optional[redis.ConnectionPool] = None
    _redis_client: Optional[redis.Redis] = None

    def __new__(cls) -> 'RedisManager':
        """Singleton pattern to ensure one Redis manager instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize Redis manager."""
        if hasattr(self, '_initialized'):
            return

        self.logger = logging.getLogger("redis_manager")
        self.enabled = os.getenv("ENABLE_REDIS", "false").lower() == "true"
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.db = int(os.getenv("REDIS_DB", "0"))
        self.password = os.getenv("REDIS_PASSWORD", None)
        self.username = os.getenv("REDIS_USERNAME", None)
        self.max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "10"))
        self.socket_timeout = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
        self.socket_connect_timeout = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5.0"))

        self._initialized = True

        if self.enabled and not REDIS_AVAILABLE:
            self.logger.error("Redis is enabled but redis package is not installed. Install with: pip install redis")
            self.enabled = False

        if self.enabled:
            self.logger.info(f"Redis integration enabled - connecting to {self.host}:{self.port}")
        else:
            self.logger.info("Redis integration is disabled")

    async def initialize(self) -> bool:
        """
        Initialize Redis connection pool.

        Returns:
            bool: True if connection successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Create connection pool
            self._redis_pool = redis.ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                username=self.username,
                max_connections=self.max_connections,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                decode_responses=True,
                health_check_interval=30
            )

            # Create Redis client
            self._redis_client = redis.Redis(connection_pool=self._redis_pool)

            # Test connection
            await self._redis_client.ping()
            self.logger.info("Successfully connected to Redis")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            self.enabled = False
            return False

    async def disconnect(self):
        """Close Redis connections."""
        if self._redis_client:
            await self._redis_client.aclose()
            self._redis_client = None

        if self._redis_pool:
            await self._redis_pool.aclose()
            self._redis_pool = None

        self.logger.info("Redis connections closed")

    def get_client(self) -> Optional[redis.Redis]:
        """
        Get Redis client instance.

        Returns:
            Redis client instance or None if not enabled/connected
        """
        if not self.enabled:
            return None
        return self._redis_client

    def is_enabled(self) -> bool:
        """Check if Redis is enabled and available."""
        return self.enabled and self._redis_client is not None

    async def get(self, key: str) -> Optional[str]:
        """
        Get value by key.

        Args:
            key: Redis key

        Returns:
            Value as string or None if not found/error
        """
        if not self.is_enabled():
            return None

        try:
            return await self._redis_client.get(key)
        except Exception as e:
            self.logger.error(f"Redis GET error for key '{key}': {e}")
            return None

    async def set(self, key: str, value: Union[str, int, float], ex: Optional[int] = None,
                  px: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool:
        """
        Set key-value pair.

        Args:
            key: Redis key
            value: Value to set
            ex: Expire time in seconds
            px: Expire time in milliseconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            return False

        try:
            result = await self._redis_client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
            return bool(result)
        except Exception as e:
            self.logger.error(f"Redis SET error for key '{key}': {e}")
            return False

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment key value.

        Args:
            key: Redis key
            amount: Amount to increment

        Returns:
            New value or None if error
        """
        if not self.is_enabled():
            return None

        try:
            return await self._redis_client.incrby(key, amount)
        except Exception as e:
            self.logger.error(f"Redis INCR error for key '{key}': {e}")
            return None

    async def expire(self, key: str, time: int) -> bool:
        """
        Set key expiration.

        Args:
            key: Redis key
            time: Expiration time in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            return False

        try:
            result = await self._redis_client.expire(key, time)
            return bool(result)
        except Exception as e:
            self.logger.error(f"Redis EXPIRE error for key '{key}': {e}")
            return False

    async def delete(self, *keys: str) -> int:
        """
        Delete keys.

        Args:
            keys: Keys to delete

        Returns:
            Number of keys deleted
        """
        if not self.is_enabled():
            return 0

        try:
            return await self._redis_client.delete(*keys)
        except Exception as e:
            self.logger.error(f"Redis DELETE error for keys {keys}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists.

        Args:
            key: Redis key

        Returns:
            True if key exists, False otherwise
        """
        if not self.is_enabled():
            return False

        try:
            result = await self._redis_client.exists(key)
            return bool(result)
        except Exception as e:
            self.logger.error(f"Redis EXISTS error for key '{key}': {e}")
            return False

    async def ttl(self, key: str) -> int:
        """
        Get key time to live.

        Args:
            key: Redis key

        Returns:
            TTL in seconds, -1 if no expiry, -2 if key doesn't exist
        """
        if not self.is_enabled():
            return -2

        try:
            return await self._redis_client.ttl(key)
        except Exception as e:
            self.logger.error(f"Redis TTL error for key '{key}': {e}")
            return -2

    async def hget(self, name: str, key: str) -> Optional[str]:
        """
        Get hash field value.

        Args:
            name: Hash name
            key: Field key

        Returns:
            Field value or None
        """
        if not self.is_enabled():
            return None

        try:
            return await self._redis_client.hget(name, key)
        except Exception as e:
            self.logger.error(f"Redis HGET error for hash '{name}', key '{key}': {e}")
            return None

    async def hset(self, name: str, key: str = None, value: str = None,
                   mapping: Dict[str, Any] = None) -> int:
        """
        Set hash field(s).

        Args:
            name: Hash name
            key: Field key (if setting single field)
            value: Field value (if setting single field)
            mapping: Dictionary of field-value pairs

        Returns:
            Number of fields added
        """
        if not self.is_enabled():
            return 0

        try:
            if mapping:
                return await self._redis_client.hset(name, mapping=mapping)
            elif key and value is not None:
                return await self._redis_client.hset(name, key, value)
            else:
                return 0
        except Exception as e:
            self.logger.error(f"Redis HSET error for hash '{name}': {e}")
            return 0

    async def get_json(self, key: str) -> Optional[Any]:
        """
        Get and deserialize JSON value.

        Args:
            key: Redis key

        Returns:
            Deserialized value or None
        """
        value = await self.get(key)
        if value is None:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error for key '{key}': {e}")
            return None

    async def set_json(self, key: str, value: Any, ex: Optional[int] = None,
                       px: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool:
        """
        Serialize and set JSON value.

        Args:
            key: Redis key
            value: Value to serialize and set
            ex: Expire time in seconds
            px: Expire time in milliseconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if successful, False otherwise
        """
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, ex=ex, px=px, nx=nx, xx=xx)
        except (TypeError, ValueError) as e:
            self.logger.error(f"JSON encode error for key '{key}': {e}")
            return False


# Global Redis manager instance
redis_manager = RedisManager()
