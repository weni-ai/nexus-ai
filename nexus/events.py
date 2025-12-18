"""
Event system with decorator-based observer registration.

This module uses decorator-based registration to simplify observer setup.
Observers are registered using @observer decorator on their class definitions.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from nexus.event_domain.decorators import auto_register_observers
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
            "Cannot use notify_async_sync in an async context. Use notify_async() or await async_event_manager.notify()"
        )
    except RuntimeError as e:
        if "Cannot use notify_async_sync" in str(e):
            raise
        # No event loop exists - create a new one and run
        asyncio.run(async_event_manager.notify(event, **kwargs))


# Import observer modules to trigger decorator registration
# These imports happen after event managers are created to avoid circular imports
# The @observer decorator stores registration info, which is then processed by auto_register_observers()
try:
    # Intelligence observers
    import nexus.actions.observers  # noqa: F401
    import nexus.intelligences.observer  # noqa: F401

    # Health check observers
    import nexus.logs.observers  # noqa: F401

    # Project and action observers
    import nexus.projects.observer  # noqa: F401

    # Cache invalidation observers
    import router.services.cache_invalidation_observers  # noqa: F401

    # Trace observers
    import router.traces_observers.rationale.observer  # noqa: F401
    import router.traces_observers.save_traces  # noqa: F401
    import router.traces_observers.summary  # noqa: F401

    # Auto-register all decorated observers
    auto_register_observers(event_manager, async_event_manager)
except ImportError as e:
    # If imports fail (e.g., during testing), log but don't crash
    logger.warning(f"Failed to import some observer modules: {e}. Some observers may not be registered.")
