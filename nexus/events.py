"""
Event system with decorator-based observer registration.

This module provides event managers for the observer pattern.
Observers are registered using @observer decorator on their class definitions.

IMPORTANT: Observer registration happens in nexus.event_driven.apps.EventDrivenConfig.ready()
This avoids circular imports by deferring registration until all Django apps are loaded.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from nexus.event_domain.event_manager import AsyncEventManager, EventManager

logger = logging.getLogger(__name__)

# Create event managers - these can be imported without triggering observer imports
event_manager = EventManager()
async_event_manager = AsyncEventManager()

# Thread pool executor for running async code from sync contexts
_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="async_event")


def notify_async(event: str, **kwargs):
    """
    Helper function to call async_event_manager.notify() from synchronous code.

    This function handles async execution properly:
    - If already in an async context (event loop running), schedules as a background task
    - If in a sync context (Django views), runs in a background thread to avoid blocking

    For cache invalidation events, this allows async observers to be called from
    synchronous Django views and use cases without blocking the request.

    Args:
        event: The event name
        **kwargs: Event payload
    """
    try:
        # Try to get the current running event loop
        # If loop is already running, schedule the coroutine as a background task
        # This is fine for cache invalidation which should run asynchronously
        asyncio.get_running_loop()
        asyncio.create_task(async_event_manager.notify(event, **kwargs))
    except RuntimeError:
        # No event loop exists - we're in a sync context (e.g., Django view)
        # Run in a background thread to avoid blocking the request
        def run_async():
            """Run async code in a new event loop in a background thread."""
            try:
                asyncio.run(async_event_manager.notify(event, **kwargs))
            except Exception as e:
                logger.error(f"Error in async event notification for {event}: {e}", exc_info=True)

        _executor.submit(run_async)


def notify_async_sync(event: str, **kwargs):
    """
    Synchronous version of notify_async for use in Django shell or when you need
    to wait for the async observers to complete.

    This function blocks until all async observers have finished executing.
    Use this only in interactive contexts (Django shell, scripts) where blocking is acceptable.

    Args:
        event: The event name
        **kwargs: Event payload
    """
    try:
        # Try to get the current running event loop
        asyncio.get_running_loop()
        # If loop is already running, we can't use asyncio.run()
        # This shouldn't happen in Django shell, but if it does, we need to handle it differently
        # For now, raise an error to indicate this case needs special handling
        raise RuntimeError(
            "Cannot use notify_async_sync in an async context. "
            "Use notify_async() or await async_event_manager.notify()"
        )
    except RuntimeError as e:
        if "Cannot use notify_async_sync" in str(e):
            raise
        # No event loop exists - create a new one and run
        asyncio.run(async_event_manager.notify(event, **kwargs))


# NOTE: Observer registration is handled in nexus.event_driven.apps.EventDrivenConfig.ready()
# This avoids circular imports that occur when importing observer modules at module load time.
