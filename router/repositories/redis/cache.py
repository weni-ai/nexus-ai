import json
from typing import Any, Optional

from django.conf import settings
from redis import Redis

from router.repositories import Repository


class CacheRepository(Repository):
    """Redis implementation of cache repository for configuration data."""

    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis_client = redis_client or Redis.from_url(settings.REDIS_URL)

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        cached = self.redis_client.get(key)
        if cached:
            return json.loads(cached.decode("utf-8"))
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        serialized = json.dumps(value, default=str)
        self.redis_client.setex(key, ttl, serialized)

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        self.redis_client.delete(key)

    def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern."""
        keys = self.redis_client.keys(pattern)
        if keys:
            self.redis_client.delete(*keys)

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return bool(self.redis_client.exists(key))
