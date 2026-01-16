import logging
from typing import Optional

from django.conf import settings
from redis import ConnectionPool, Redis

logger = logging.getLogger(__name__)

_connection_pool: Optional[ConnectionPool] = None


def get_redis_pool() -> ConnectionPool:
    """
    Get or create the shared Redis connection pool.

    Uses ConnectionPool which:
    - Reuses connections efficiently
    - Creates new connections on demand (no hard limit by default)
    - No timeout - same behavior as before but with connection reuse

    This avoids introducing new failure modes while still benefiting from
    connection reuse across requests within the same worker process.
    """
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=False,
        )
        logger.info("[RedisPool] Created connection pool")
    return _connection_pool


def get_redis_client() -> Redis:
    """Get a Redis client using the shared connection pool."""
    return Redis(connection_pool=get_redis_pool())
