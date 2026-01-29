"""
Redis client utilities for read/write separation with connection pooling.

Uses read replica for read operations when REDIS_READ_URL is available,
falls back to primary REDIS_URL if not configured.

Uses connection pools to efficiently reuse connections across requests
within the same worker process.
"""

import logging
from typing import Optional

from django.conf import settings
from redis import ConnectionPool, Redis

logger = logging.getLogger(__name__)

# Global connection pools (one for read, one for write)
_read_pool: Optional[ConnectionPool] = None
_write_pool: Optional[ConnectionPool] = None


def _get_read_pool() -> ConnectionPool:
    """Get or create the shared Redis connection pool for read operations."""
    global _read_pool
    if _read_pool is None:
        # Try to use read replica if configured
        read_url = getattr(settings, "REDIS_READ_URL", None)
        if read_url:
            _read_pool = ConnectionPool.from_url(read_url, decode_responses=False)
            logger.info("[RedisPool] Created read replica connection pool")
        else:
            # Fallback to primary if read replica not configured
            _read_pool = ConnectionPool.from_url(settings.REDIS_URL, decode_responses=False)
            logger.info("[RedisPool] Created read connection pool (using primary)")
    return _read_pool


def _get_write_pool() -> ConnectionPool:
    """Get or create the shared Redis connection pool for write operations."""
    global _write_pool
    if _write_pool is None:
        _write_pool = ConnectionPool.from_url(settings.REDIS_URL, decode_responses=False)
        logger.info("[RedisPool] Created write connection pool")
    return _write_pool


def get_redis_client(read_only: bool = False) -> Redis:
    """
    Get Redis client for read or write operations using connection pools.

    Args:
        read_only: If True, use read replica (REDIS_READ_URL) if available,
                   otherwise use primary (REDIS_URL)

    Returns:
        Redis client instance using connection pool
    """
    if read_only:
        return Redis(connection_pool=_get_read_pool())
    else:
        return Redis(connection_pool=_get_write_pool())


def get_redis_read_client() -> Redis:
    """Convenience function for read operations - uses connection pool."""
    return get_redis_client(read_only=True)


def get_redis_write_client() -> Redis:
    """Convenience function for write operations - uses connection pool."""
    return get_redis_client(read_only=False)
