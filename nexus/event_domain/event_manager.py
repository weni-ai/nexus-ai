import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional, Union

from nexus.event_domain.event_observer import EventObserver
from nexus.event_domain.middleware import MiddlewareChain, create_default_middleware_chain
from nexus.event_domain.observer_registry import ObserverRegistry, get_registry
from nexus.event_domain.validators import ValidatorChain

logger = logging.getLogger(__name__)


class EventManager:
    def __init__(
        self,
        registry: Optional[ObserverRegistry] = None,
        middleware: Optional[MiddlewareChain] = None,
        validators: Optional[Dict[str, ValidatorChain]] = None,
    ):
        """
        Initialize EventManager.

        Args:
            registry: Optional ObserverRegistry instance. If not provided, uses global registry.
            middleware: Optional MiddlewareChain for cross-cutting concerns. If not provided,
                       uses default middleware chain (Sentry + performance monitoring).
            validators: Optional dictionary mapping event names to ValidatorChain instances.
                       If not provided, no validation is performed.
        """
        self.registry = registry or get_registry()
        self.middleware = middleware or create_default_middleware_chain()
        self.validators: Dict[str, ValidatorChain] = validators or {}
        # Keep backwards compatibility with direct observer storage
        self.observers: Dict[str, List[EventObserver]] = {}

    def subscribe(
        self,
        event: str,
        observer: Union[EventObserver, List[EventObserver], str, List[str]] = None,
        observer_path: Union[str, List[str]] = None,
        isolate_errors: bool = False,
        factory: Optional[Callable] = None,
    ):
        """
        Subscribe an observer to an event.

        Args:
            event: The event name
            observer: Observer instance(s) or class path string(s) for lazy loading
            observer_path: Alternative way to specify observer path(s) for lazy loading
            isolate_errors: If True, errors in this observer won't stop other observers.
                           Default False (fail fast - stop on first error).
            factory: Optional factory function to create observer instance with dependencies.
                     Should accept observer class and return instance.
        """
        # Support both old and new API
        if observer_path:
            self.registry.register(event, observer_path, lazy=True, isolate_errors=isolate_errors, factory=factory)
        elif isinstance(observer, str) or (isinstance(observer, list) and observer and isinstance(observer[0], str)):
            # String-based registration (lazy loading)
            self.registry.register(event, observer, lazy=True, isolate_errors=isolate_errors, factory=factory)
        else:
            # Direct instance registration (backwards compatible)
            if event not in self.observers:
                self.observers[event] = []

            if isinstance(observer, list):
                self.observers[event].extend(observer)
            else:
                self.observers[event].append(observer)

            # Also register in registry for consistency
            self.registry.register(event, observer, lazy=False, isolate_errors=isolate_errors, factory=factory)

    def add_validator(self, event: str, validator_chain: ValidatorChain) -> None:
        """
        Add validator chain for an event.

        Args:
            event: The event name
            validator_chain: ValidatorChain instance to use for validation
        """
        self.validators[event] = validator_chain

    def notify(self, event: str, **kwargs):
        """
        Notify all observers for an event.

        By default, if an observer fails, execution stops (fail fast).
        Observers can be registered with isolate_errors=True to continue on error.

        Args:
            event: The event name
            **kwargs: Event payload

        Raises:
            ValueError: If validation fails
            TypeError: If payload type validation fails
        """
        # Validate event payload if validators are configured
        if event in self.validators:
            try:
                self.validators[event].validate(event, kwargs)
            except Exception as e:
                logger.error(f"Event '{event}' validation failed: {e}", extra={"event": event, "kwargs": kwargs})
                raise

        # Get observers from both sources
        observers = self.observers.get(event, []).copy()
        observers.extend(self.registry.get_observers(event))

        for observer in observers:
            # Check if this observer should have isolated errors
            should_isolate = self.registry.should_isolate_errors(observer)

            # Track execution time for middleware
            start_time = time.time()

            # Call before_perform hooks
            self.middleware.before_perform(observer, event, **kwargs)

            if should_isolate:
                # Isolated: catch errors and continue
                try:
                    observer.perform(**kwargs)
                    duration = time.time() - start_time
                    # Call after_perform hooks on success
                    self.middleware.after_perform(observer, event, duration, **kwargs)
                except Exception as e:
                    duration = time.time() - start_time
                    observer_name = getattr(observer.__class__, "__name__", "Unknown")

                    # Call on_error hooks (includes Sentry capture)
                    self.middleware.on_error(observer, event, e, duration, **kwargs)

                    logger.error(
                        f"Observer '{observer_name}' failed for event '{event}' (isolated): {e}",
                        exc_info=True,
                        extra={
                            "event": event,
                            "observer": observer_name,
                            "kwargs": kwargs,
                        },
                    )
                    # Continue with next observer
            else:
                # Default: fail fast - let exception propagate
                try:
                    observer.perform(**kwargs)
                    duration = time.time() - start_time
                    # Call after_perform hooks on success
                    self.middleware.after_perform(observer, event, duration, **kwargs)
                except Exception as e:
                    duration = time.time() - start_time
                    # Call on_error hooks (includes Sentry capture)
                    self.middleware.on_error(observer, event, e, duration, **kwargs)
                    # Re-raise exception for fail-fast behavior
                    raise


class AsyncEventManager:
    def __init__(
        self,
        registry: Optional[ObserverRegistry] = None,
        middleware: Optional[MiddlewareChain] = None,
        validators: Optional[Dict[str, ValidatorChain]] = None,
    ):
        """
        Initialize AsyncEventManager.

        Args:
            registry: Optional ObserverRegistry instance. If not provided, uses global registry.
            middleware: Optional MiddlewareChain for cross-cutting concerns. If not provided,
                       uses default middleware chain (Sentry + performance monitoring).
            validators: Optional dictionary mapping event names to ValidatorChain instances.
                       If not provided, no validation is performed.
        """
        self.registry = registry or get_registry()
        self.middleware = middleware or create_default_middleware_chain()
        self.validators: Dict[str, ValidatorChain] = validators or {}
        # Keep backwards compatibility with direct observer storage
        self.observers: Dict[str, List[EventObserver]] = {}

    def subscribe(
        self,
        event: str,
        observer: Union[EventObserver, List[EventObserver], str, List[str]] = None,
        observer_path: Union[str, List[str]] = None,
        isolate_errors: bool = False,
        factory: Optional[Callable] = None,
    ):
        """
        Subscribe an observer to an event.

        Args:
            event: The event name
            observer: Observer instance(s) or class path string(s) for lazy loading
            observer_path: Alternative way to specify observer path(s) for lazy loading
            isolate_errors: If True, errors in this observer won't stop other observers.
                           Default False (fail fast - stop on first error).
            factory: Optional factory function to create observer instance with dependencies.
                     Should accept observer class and return instance.
        """
        # Support both old and new API
        if observer_path:
            self.registry.register(event, observer_path, lazy=True, isolate_errors=isolate_errors, factory=factory)
        elif isinstance(observer, str) or (isinstance(observer, list) and observer and isinstance(observer[0], str)):
            # String-based registration (lazy loading)
            self.registry.register(event, observer, lazy=True, isolate_errors=isolate_errors, factory=factory)
        else:
            # Direct instance registration (backwards compatible)
            if event not in self.observers:
                self.observers[event] = []

            if isinstance(observer, list):
                self.observers[event].extend(observer)
            else:
                self.observers[event].append(observer)

            # Also register in registry for consistency
            self.registry.register(event, observer, lazy=False, isolate_errors=isolate_errors, factory=factory)

    def add_validator(self, event: str, validator_chain: ValidatorChain) -> None:
        """
        Add validator chain for an event.

        Args:
            event: The event name
            validator_chain: ValidatorChain instance to use for validation
        """
        self.validators[event] = validator_chain

    async def notify(self, event: str, **kwargs):
        """
        Notify all observers for an event asynchronously.

        By default, if an observer fails, execution stops (fail fast).
        Observers can be registered with isolate_errors=True to continue on error.

        Args:
            event: The event name
            **kwargs: Event payload

        Raises:
            ValueError: If validation fails
            TypeError: If payload type validation fails
        """
        # Validate event payload if validators are configured
        if event in self.validators:
            try:
                self.validators[event].validate(event, kwargs)
            except Exception as e:
                logger.error(f"Event '{event}' validation failed: {e}", extra={"event": event, "kwargs": kwargs})
                raise

        # Get observers from both sources
        observers = self.observers.get(event, []).copy()
        observers.extend(self.registry.get_observers(event))

        for observer in observers:
            # Check if this observer should have isolated errors
            should_isolate = self.registry.should_isolate_errors(observer)

            # Track execution time for middleware
            start_time = time.time()

            # Call before_perform hooks
            self.middleware.before_perform(observer, event, **kwargs)

            if should_isolate:
                # Isolated: catch errors and continue
                try:
                    if hasattr(observer, "perform") and asyncio.iscoroutinefunction(observer.perform):
                        await observer.perform(**kwargs)
                    else:
                        observer.perform(**kwargs)
                    duration = time.time() - start_time
                    # Call after_perform hooks on success
                    self.middleware.after_perform(observer, event, duration, **kwargs)
                except Exception as e:
                    duration = time.time() - start_time
                    observer_name = getattr(observer.__class__, "__name__", "Unknown")

                    # Call on_error hooks (includes Sentry capture)
                    self.middleware.on_error(observer, event, e, duration, **kwargs)

                    logger.error(
                        f"Observer '{observer_name}' failed for event '{event}' (isolated): {e}",
                        exc_info=True,
                        extra={
                            "event": event,
                            "observer": observer_name,
                            "kwargs": kwargs,
                        },
                    )
                    # Continue with next observer
            else:
                # Default: fail fast - let exception propagate
                try:
                    if hasattr(observer, "perform") and asyncio.iscoroutinefunction(observer.perform):
                        await observer.perform(**kwargs)
                    else:
                        observer.perform(**kwargs)
                    duration = time.time() - start_time
                    # Call after_perform hooks on success
                    self.middleware.after_perform(observer, event, duration, **kwargs)
                except Exception as e:
                    duration = time.time() - start_time
                    # Call on_error hooks (includes Sentry capture)
                    self.middleware.on_error(observer, event, e, duration, **kwargs)
                    # Re-raise exception for fail-fast behavior
                    raise
