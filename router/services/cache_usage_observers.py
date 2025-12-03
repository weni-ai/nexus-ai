"""
Cache usage observers for monitoring cache performance.

These observers track cache hit/miss rates, performance metrics, and usage patterns
to help monitor and optimize the cache layer.
"""
import logging
import time
from typing import Dict, Optional

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver

logger = logging.getLogger(__name__)


@observer("cache:usage", isolate_errors=True, manager="async")
class CacheUsageObserver(EventObserver):
    """
    Observer that tracks cache usage metrics.

    Monitors cache hits, misses, and performance for all cache operations.
    """

    async def perform(self, **kwargs):
        """
        Track cache usage event.

        Expected kwargs:
        - cache_type: Type of cache (project, content_base, team, guardrails, inline_agent_config)
        - project_uuid: Project UUID
        - operation: Operation type (get, set, delete)
        - cache_hit: Whether it was a cache hit (bool)
        - duration: Duration of the operation in seconds (float)
        - cache_key: Cache key used (optional)
        """
        cache_type = kwargs.get("cache_type")
        project_uuid = kwargs.get("project_uuid")
        operation = kwargs.get("operation", "get")
        cache_hit = kwargs.get("cache_hit", False)
        duration = kwargs.get("duration", 0.0)
        cache_key = kwargs.get("cache_key")

        # Log cache usage
        logger.debug(
            f"Cache {operation} for {cache_type}",
            extra={
                "cache_type": cache_type,
                "project_uuid": project_uuid,
                "operation": operation,
                "cache_hit": cache_hit,
                "duration_seconds": duration,
                "cache_key": cache_key,
            },
        )

        # TODO: Send metrics to Prometheus/StatsD if needed
        # Example:
        # from prometheus_client import Counter, Histogram
        # cache_operations = Counter('cache_operations_total', 'Total cache operations', ['type', 'operation', 'hit'])
        # cache_duration = Histogram('cache_operation_duration_seconds', 'Cache operation duration', ['type'])
        # cache_operations.labels(type=cache_type, operation=operation, hit='hit' if cache_hit else 'miss').inc()
        # cache_duration.labels(type=cache_type).observe(duration)


@observer("cache:performance", isolate_errors=True, manager="async")
class CachePerformanceObserver(EventObserver):
    """
    Observer that tracks cache performance metrics.

    Monitors slow cache operations and performance degradation.
    """

    async def perform(self, **kwargs):
        """
        Track cache performance event.

        Expected kwargs:
        - cache_type: Type of cache
        - project_uuid: Project UUID
        - duration: Duration of the operation in seconds
        - operation: Operation type
        - threshold: Performance threshold (optional)
        """
        cache_type = kwargs.get("cache_type")
        project_uuid = kwargs.get("project_uuid")
        duration = kwargs.get("duration", 0.0)
        operation = kwargs.get("operation", "get")
        threshold = kwargs.get("threshold", 0.1)  # Default 100ms threshold

        if duration > threshold:
            logger.warning(
                f"Slow cache {operation} for {cache_type}: {duration:.3f}s (threshold: {threshold}s)",
                extra={
                    "cache_type": cache_type,
                    "project_uuid": project_uuid,
                    "operation": operation,
                    "duration_seconds": duration,
                    "threshold_seconds": threshold,
                    "slow": True,
                },
            )

        # TODO: Send to monitoring system (Sentry, DataDog, etc.)
        # Example:
        # if duration > threshold:
        #     sentry_sdk.set_context("cache_performance", {
        #         "cache_type": cache_type,
        #         "duration": duration,
        #         "operation": operation,
        #     })
        #     sentry_sdk.capture_message(f"Slow cache operation: {cache_type}", level="warning")


def track_cache_operation(
    cache_type: str,
    project_uuid: str,
    operation: str,
    cache_hit: bool,
    duration: float,
    cache_key: Optional[str] = None,
    event_manager=None,
):
    """
    Helper function to track cache operations via observers.

    This can be called from CacheService or PreGenerationService to track usage.

    Args:
        cache_type: Type of cache (project, content_base, team, etc.)
        project_uuid: Project UUID
        operation: Operation type (get, set, delete)
        cache_hit: Whether it was a cache hit
        duration: Duration in seconds
        cache_key: Optional cache key
        event_manager: Optional event manager (will import if not provided)
    """
    if event_manager is None:
        from nexus.events import async_event_manager as event_manager

    # Fire cache usage event
    event_manager.notify(
        event="cache:usage",
        cache_type=cache_type,
        project_uuid=project_uuid,
        operation=operation,
        cache_hit=cache_hit,
        duration=duration,
        cache_key=cache_key,
    )

    # Fire performance event if slow
    if duration > 0.1:  # 100ms threshold
        event_manager.notify(
            event="cache:performance",
            cache_type=cache_type,
            project_uuid=project_uuid,
            duration=duration,
            operation=operation,
            threshold=0.1,
        )
