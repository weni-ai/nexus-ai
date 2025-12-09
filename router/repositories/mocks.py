# Mock repositories for unit tests and local development

from typing import Any, Dict, List, Optional, Tuple

from router.repositories import Repository
from router.repositories.entities import ResolutionEntities


class MockRepository(Repository):
    def storage_message(
        self,
        project_uuid: str,
        contact_urn: str,
        message_data: dict,
        channel_uuid: str = None,
        resolution_status: int = ResolutionEntities.IN_PROGRESS,
        ttl_hours: int = 48,
    ) -> None:
        pass

    def get_messages(
        self, project_uuid: str, contact_urn: str, channel_uuid: str, limit: int = 50, cursor: str = None
    ) -> dict:
        return {"items": [], "next_cursor": None, "total_count": 0}

    def get_messages_for_conversation(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        start_date: str,
        end_date: str,
        resolution_status: int = ResolutionEntities.IN_PROGRESS,
    ) -> list:
        return []

    def _format_message(self, item: dict) -> dict:
        return {
            "text": item["message_text"],
            "source": item["source_type"],
            "created_at": item["created_at"],
        }

    def delete_messages(self, project_uuid: str, contact_urn: str, channel_uuid: str = None) -> None:
        return None

    def add_message(self, project_uuid: str, contact_urn: str, message: dict, channel_uuid: str = None) -> None:
        return None

    def store_batch_messages(
        self, project_uuid: str, contact_urn: str, messages: list, key: str, channel_uuid: str = None
    ) -> None:
        return None


class MockCacheRepository(Repository):
    """In-memory mock implementation of CacheRepository for testing.

    Stores cache data in memory (dict) instead of Redis.
    Useful for unit tests that don't require actual Redis connection.
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expiration_timestamp)
        import time

        self._time = time

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key not in self._cache:
            return None

        value, expiration = self._cache[key]
        current_time = self._time.time()

        # Check if expired
        if expiration > 0 and current_time >= expiration:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        current_time = self._time.time()
        expiration = current_time + ttl if ttl > 0 else 0
        self._cache[key] = (value, expiration)

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]

    def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern."""
        import fnmatch

        keys_to_delete = [key for key in self._cache.keys() if fnmatch.fnmatch(key, pattern)]
        for key in keys_to_delete:
            del self._cache[key]

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        if key not in self._cache:
            return False

        # Check if expired
        value, expiration = self._cache[key]
        current_time = self._time.time()
        if expiration > 0 and current_time >= expiration:
            del self._cache[key]
            return False

        return True

    def clear(self) -> None:
        """Clear all cache (useful for test teardown)."""
        self._cache.clear()

    def get_all_keys(self) -> List[str]:
        """Get all cache keys (useful for testing)."""
        # Clean expired keys first
        current_time = self._time.time()
        expired_keys = [
            key for key, (value, expiration) in self._cache.items() if expiration > 0 and current_time >= expiration
        ]
        for key in expired_keys:
            del self._cache[key]

        return list(self._cache.keys())
