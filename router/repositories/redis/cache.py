import json
from typing import Any, Optional

from redis import Redis

from router.repositories import Repository
from router.utils.redis_clients import get_redis_read_client, get_redis_write_client


class CacheRepository(Repository):
    """Redis implementation of cache repository for configuration data."""

    def __init__(self, redis_client: Optional[Redis] = None):
        if redis_client:
            self._read_client = redis_client
            self._write_client = redis_client
        else:
            self._read_client = get_redis_read_client()
            self._write_client = get_redis_write_client()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache - uses read replica if available."""
        cached = self._read_client.get(key)
        if cached:
            return json.loads(cached.decode("utf-8"))
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL - uses primary."""
        serialized = json.dumps(value, default=str)
        self._write_client.setex(key, ttl, serialized)

    def delete(self, key: str) -> None:
        """Delete key from cache - uses primary."""
        self._write_client.delete(key)

    def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern - uses primary."""
        keys = self._read_client.keys(pattern)
        if keys:
            self._write_client.delete(*keys)

    def exists(self, key: str) -> bool:
        """Check if key exists - uses read replica if available."""
        return bool(self._read_client.exists(key))
