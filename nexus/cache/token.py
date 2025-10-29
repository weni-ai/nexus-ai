import logging
import time
from typing import Callable, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)


class TokenCache:
    """
    Simple token cache with TTL and automatic invalidation.
    """

    def __init__(self, cache_key_prefix: str = "token"):
        self.cache_key_prefix = cache_key_prefix
        self.default_ttl = 12 * 60 * 60
        self.safety_margin = 5 * 60

    def _make_key(self, identifier: str) -> str:
        """Creates cache key."""
        return f"{self.cache_key_prefix}:{identifier}"

    def get(self, identifier: str) -> Optional[str]:
        """
        Retrieves token from cache.
        """
        cache_key = self._make_key(identifier)
        cached_data = cache.get(cache_key)

        if cached_data and isinstance(cached_data, dict):
            token = cached_data.get("token")
            expires_at = cached_data.get("expires_at", 0)

            if not time.time() < (expires_at - self.safety_margin):
                logger.debug(f"Token expired for: {identifier}, removing from cache")
                self.delete(identifier)
                return None

            logger.debug(f"Using cached token for: {identifier}")
            return token

        return None

    def set(self, identifier: str, token: str, ttl_seconds: Optional[int] = None) -> None:
        """
        Stores token in cache.
        """
        ttl = ttl_seconds or self.default_ttl
        cache_key = self._make_key(identifier)

        cache_data = {
            "token": token,
            "expires_at": time.time() + ttl,
            "cached_at": time.time(),
        }

        cache.set(cache_key, cache_data, ttl)
        logger.debug(f"Cached token for: {identifier} (TTL: {ttl}s)")

    def delete(self, identifier: str) -> None:
        """
        Removes token from cache.
        """
        cache_key = self._make_key(identifier)
        cache.delete(cache_key)
        logger.debug(f"Deleted token cache for: {identifier}")

    def get_or_generate(
        self,
        identifier: str,
        token_factory: Callable[[], str],
        ttl_seconds: Optional[int] = None,
    ) -> str:
        """
        Retrieves token from cache or generates new one.
        """
        cached_token = self.get(identifier)

        if cached_token:
            return cached_token

        logger.debug(f"Generating new token for: {identifier}")

        new_token = token_factory()

        if new_token:
            self.set(identifier, new_token, ttl_seconds)
            return new_token

        raise ValueError("Token factory returned empty token")

    def invalidate(self, identifier: str) -> None:
        """Alias for delete() - more semantic for tokens."""
        self.delete(identifier)
