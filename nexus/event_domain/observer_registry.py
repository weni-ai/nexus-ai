"""
Observer Registry for lazy loading of observers to avoid circular imports.

This module provides a registry pattern that stores observer class paths as strings
and lazily imports them only when needed, breaking circular import dependencies.
"""

import importlib
import logging
from typing import Callable, Dict, List, Optional, Type, Union

from nexus.event_domain.event_observer import EventObserver

logger = logging.getLogger(__name__)


class ObserverRegistry:
    """
    Registry for managing observer subscriptions with lazy loading.

    This class stores observer class paths as strings and imports them
    only when needed, preventing circular import issues.
    """

    def __init__(self, factory: Optional[Callable[[Type], EventObserver]] = None):
        """
        Initialize ObserverRegistry.

        Args:
            factory: Optional factory function to create observer instances.
                     Should accept observer class and return instance.
                     If None, uses default instantiation (observer_class()).
        """
        self._observer_paths: Dict[str, List[str]] = {}
        self._observer_instances: Dict[str, List[EventObserver]] = {}
        self._loaded_paths: Dict[str, set] = {}  # Track which paths have been loaded per event
        self._observer_factories: Dict[str, Callable[[Type], EventObserver]] = {}  # Per-observer factories
        self._observer_isolation: Dict[EventObserver, bool] = {}  # Track error isolation per observer instance
        self._path_isolation: Dict[str, bool] = {}  # Track error isolation per observer path
        self._default_factory = factory
        self._lazy_loaded: bool = False

    def register(
        self,
        event: str,
        observer_path: Union[str, List[str]],
        lazy: bool = True,
        factory: Optional[Callable[[Type], EventObserver]] = None,
        isolate_errors: bool = False,
    ):
        """
        Register an observer for an event.

        Args:
            event: The event name to subscribe to
            observer_path: Full module path to observer class
                          (e.g., 'nexus.intelligences.observer.IntelligenceCreateObserver')
                          or list of paths. Can also be an instance if lazy=False.
            lazy: If True, store as string path for lazy loading. If False, store instance directly.
            factory: Optional factory function to create observer instance. Overrides default factory.
            isolate_errors: If True, errors in this observer won't stop other observers. Default False (fail fast).
        """
        # Initialize storage for this event if needed
        if event not in self._observer_paths:
            self._observer_paths[event] = []
        if event not in self._observer_instances:
            self._observer_instances[event] = []

        if not lazy:
            # Direct instance registration (for backwards compatibility)
            observers = observer_path if isinstance(observer_path, list) else [observer_path]
            for observer in observers:
                self._observer_instances[event].append(observer)
                # Store isolation setting for this observer instance
                self._observer_isolation[observer] = isolate_errors
        else:
            # String-based registration for lazy loading
            paths = observer_path if isinstance(observer_path, list) else [observer_path]
            for path in paths:
                self._observer_paths[event].append(path)
                # Store factory for this observer if provided
                if factory:
                    self._observer_factories[path] = factory
                # Store isolation setting for this observer path
                self._path_isolation[path] = isolate_errors

    def _load_observer(self, observer_path: str) -> EventObserver:
        """
        Lazily load an observer from its module path.

        Args:
            observer_path: Full path like 'module.path.ClassName'

        Returns:
            Instance of the observer class
        """
        try:
            module_path, class_name = observer_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            observer_class: Type[EventObserver] = getattr(module, class_name)

            # Use factory if available (for dependency injection)
            factory = self._observer_factories.get(observer_path) or self._default_factory
            if factory:
                return factory(observer_class)
            else:
                # Default: instantiate with no arguments
                return observer_class()
        except (ImportError, AttributeError, ValueError) as e:
            raise ImportError(
                f"Failed to load observer '{observer_path}': {e}. "
                f"Make sure the module path and class name are correct."
            ) from e

    def get_observers(self, event: str) -> List[EventObserver]:
        """
        Get all observers for an event, loading them lazily if needed.

        Args:
            event: The event name

        Returns:
            List of observer instances
        """
        observers = self._observer_instances.get(event, []).copy()

        # Load lazy observers if any are registered
        if event in self._observer_paths:
            # Initialize loaded paths tracking for this event if needed
            if event not in self._loaded_paths:
                self._loaded_paths[event] = set()

            for observer_path in self._observer_paths[event]:
                # Skip if we've already loaded this path
                if observer_path in self._loaded_paths[event]:
                    continue

                try:
                    observer = self._load_observer(observer_path)
                    observers.append(observer)
                    # Cache the instance to avoid reloading
                    if event not in self._observer_instances:
                        self._observer_instances[event] = []
                    self._observer_instances[event].append(observer)
                    # Store isolation setting from path to instance
                    if observer_path in self._path_isolation:
                        self._observer_isolation[observer] = self._path_isolation[observer_path]
                    self._loaded_paths[event].add(observer_path)
                except ImportError as e:
                    # Log error but don't fail completely
                    logger.error(f"Failed to load observer for event '{event}': {e}")

        return observers

    def should_isolate_errors(self, observer: EventObserver) -> bool:
        """
        Check if errors for this observer should be isolated.

        Args:
            observer: The observer instance

        Returns:
            True if errors should be isolated (continue on error), False if should fail fast
        """
        return self._observer_isolation.get(observer, False)

    def clear_cache(self):
        """Clear cached observer instances (useful for testing)."""
        self._observer_instances.clear()
        self._loaded_paths.clear()

    def get_registered_events(self) -> List[str]:
        """Get list of all registered event names."""
        events = set(self._observer_paths.keys())
        events.update(self._observer_instances.keys())
        return list(events)


# Global registry instance
_observer_registry = ObserverRegistry()


def get_registry() -> ObserverRegistry:
    """Get the global observer registry instance."""
    return _observer_registry
