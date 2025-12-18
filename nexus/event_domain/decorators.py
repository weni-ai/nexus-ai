"""
Decorator-based observer registration.

This module provides decorators for registering observers directly on their class definitions,
simplifying the registration process and keeping registration close to the observer implementation.
"""

import logging
from typing import Callable, List, Optional, Type, Union

from nexus.event_domain.event_observer import EventObserver

logger = logging.getLogger(__name__)

# Global registry to track decorated observers
_decorated_observers = []


def observer(
    event: str,
    manager: Union[str, List[str]] = "sync",
    isolate_errors: bool = False,
    factory: Optional[Callable] = None,
):
    """
    Decorator for registering observers.

    This decorator stores registration metadata on the observer class.
    The observer will be automatically registered when auto_register_observers() is called.

    Args:
        event: The event name to subscribe to
        manager: Which manager(s) to use - "sync" for EventManager, "async" for AsyncEventManager,
                 or ["sync", "async"] for both. Default "sync".
        isolate_errors: If True, errors in this observer won't stop other observers.
                       Default False (fail fast).
        factory: Optional factory function to create observer instance with dependencies.

    Usage:
        @observer("intelligence_create_activity")
        class IntelligenceCreateObserver(EventObserver):
            def perform(self, intelligence):
                ...

        @observer("inline_trace_observers", factory=create_rationale_observer)
        class RationaleObserver(EventObserver):
            def perform(self, **kwargs):
                ...

        @observer("inline_trace_observers_async", manager="async")
        class AsyncSummaryTracesObserver(EventObserver):
            async def perform(self, **kwargs):
                ...

        @observer("save_inline_trace_events", manager=["sync", "async"])
        class SaveTracesObserver(EventObserver):
            def perform(self, **kwargs):
                ...
    """

    def decorator(cls: Type[EventObserver]) -> Type[EventObserver]:
        if not issubclass(cls, EventObserver):
            raise TypeError(f"{cls.__name__} must inherit from EventObserver")

        # Normalize manager to list
        managers = manager if isinstance(manager, list) else [manager]

        # Store registration metadata on the class
        cls._observer_event = event
        cls._observer_manager = managers
        cls._observer_isolate_errors = isolate_errors
        cls._observer_factory = factory
        cls._observer_decorated = True

        # Get the full module path for lazy loading
        module_path = cls.__module__
        class_name = cls.__name__
        observer_path = f"{module_path}.{class_name}"

        # Store in global registry for auto-registration (one entry per manager)
        for mgr in managers:
            _decorated_observers.append(
                {
                    "event": event,
                    "manager": mgr,
                    "observer_path": observer_path,
                    "isolate_errors": isolate_errors,
                    "factory": factory,
                }
            )

        logger.debug(f"Decorated observer: {observer_path} for event '{event}' with managers {managers}")
        return cls

    return decorator


def auto_register_observers(event_manager, async_event_manager):
    """
    Auto-register all observers that were decorated with @observer.

    This function should be called from nexus/events.py after importing all observer modules.

    Args:
        event_manager: EventManager instance to register sync observers (required)
        async_event_manager: AsyncEventManager instance to register async observers (required)
    """
    registered_count = 0
    for observer_info in _decorated_observers:
        try:
            manager = async_event_manager if observer_info["manager"] == "async" else event_manager

            manager.subscribe(
                event=observer_info["event"],
                observer=observer_info["observer_path"],
                isolate_errors=observer_info["isolate_errors"],
                factory=observer_info["factory"],
            )
            registered_count += 1
            logger.debug(
                f"Auto-registered observer: {observer_info['observer_path']} " f"for event '{observer_info['event']}'"
            )
        except Exception as e:
            logger.error(f"Failed to auto-register observer {observer_info['observer_path']}: {e}", exc_info=True)

    logger.info(f"Auto-registered {registered_count} observers from decorators")
    return registered_count


def get_decorated_observers():
    """
    Get list of all decorated observers (for testing/debugging).

    Returns:
        List of observer registration info dictionaries
    """
    return _decorated_observers.copy()


def clear_decorated_observers():
    """
    Clear the decorated observers registry (for testing).
    """
    global _decorated_observers
    _decorated_observers = []
