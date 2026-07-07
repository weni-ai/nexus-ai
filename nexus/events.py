import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from nexus.event_domain.event_manager import AsyncEventManager, EventManager

logger = logging.getLogger(__name__)

event_manager = EventManager()
async_event_manager = AsyncEventManager()

_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="async_event")


def notify_async(event: str, **kwargs):
    """
    Call async_event_manager.notify() from synchronous code.
    Runs in background thread to avoid blocking.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop: dispatch the notification ourselves.
        if getattr(settings, "TESTING", False):
            try:
                asyncio.run(async_event_manager.notify(event, **kwargs))
            except Exception as e:
                logger.error(f"Error in async event notification for {event}: {e}", exc_info=True)
            return

        def run_async():
            try:
                asyncio.run(async_event_manager.notify(event, **kwargs))
            except Exception as e:
                logger.error(f"Error in async event notification for {event}: {e}", exc_info=True)

        _executor.submit(run_async)
    else:
        asyncio.create_task(async_event_manager.notify(event, **kwargs))


def notify_async_sync(event: str, **kwargs):
    """
    Synchronous version that blocks until async observers complete.
    Use only in interactive contexts (Django shell, scripts).
    """
    try:
        asyncio.get_running_loop()
        raise RuntimeError(
            "Cannot use notify_async_sync in an async context. "
            "Use notify_async() or await async_event_manager.notify()"
        )
    except RuntimeError as e:
        if "Cannot use notify_async_sync" in str(e):
            raise
        asyncio.run(async_event_manager.notify(event, **kwargs))
