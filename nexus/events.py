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
                asyncio.run(_notify_with_test_cleanup(event, **kwargs))
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


async def _notify_with_test_cleanup(event: str, **kwargs):
    """
    Run the async notification during tests and close any database connection
    left open on asgiref's thread-sensitive executor thread.

    Observers touch the DB via the async ORM / sync_to_async, which run in a
    shared executor thread whose connection would otherwise stay open after the
    event loop is torn down. On PostgreSQL that lingering session prevents the
    test runner from dropping the test database ("is being accessed by other
    users"). Closing it on the same thread avoids that.
    """
    from asgiref.sync import sync_to_async

    from django.db import connections

    def _close_connections():
        for conn in connections.all():
            conn.close()

    try:
        await async_event_manager.notify(event, **kwargs)
    finally:
        await sync_to_async(_close_connections, thread_sensitive=True)()


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
