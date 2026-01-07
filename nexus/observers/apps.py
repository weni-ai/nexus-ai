"""
Observer Registration App

This app is responsible for registering all event observers at Django startup.
It follows Django's recommended pattern of using AppConfig.ready() for imports
that have cross-app dependencies, avoiding circular import issues.

ADDING NEW OBSERVERS:
1. Create your observer class with @observer decorator in the appropriate module
2. Add the module path to OBSERVER_MODULES list below
3. The observer will be automatically registered at startup

Observer implementations should be placed in their respective domains:
- router/tasks/workflow_observers.py - Workflow-related observers
- router/traces_observers/ - Tracing observers
- router/services/ - Service-level observers
- nexus/intelligences/ - Intelligence observers
- nexus/inline_agents/ - Inline agent observers (DataLake, Metrics, etc.)
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# List of observer modules to import and register
# Each module should contain observer classes decorated with @observer
OBSERVER_MODULES = [
    # ==========================================================================
    # Nexus Domain Observers
    # ==========================================================================
    "nexus.actions.observers",
    "nexus.intelligences.observer",
    "nexus.logs.observers",
    "nexus.projects.observer",
    # ==========================================================================
    # Router Domain Observers
    # ==========================================================================
    # Cache invalidation
    "router.services.cache_invalidation_observers",
    # Workflow observers (typing indicator, etc.)
    "router.tasks.workflow_observers",
    # Trace observers
    "router.traces_observers.rationale.observer",
    "router.traces_observers.save_traces",
    "router.traces_observers.summary",
    # ==========================================================================
    # Future Observers (uncomment when implemented)
    # ==========================================================================
    # "nexus.inline_agents.observers",  # DataLakeObserver, MetricsObserver, etc.
]


class ObserversConfig(AppConfig):
    """
    Django app configuration for observer registration.

    This app handles the registration of all event observers in the system.
    The ready() method is called AFTER all Django apps are loaded, making it
    safe to import from any module without circular import issues.
    """

    name = "nexus.observers"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Register event observers after all Django apps are loaded."""
        self._register_observers()

    def _register_observers(self):
        """Import observer modules and register them with event managers."""
        from nexus.event_domain.decorators import auto_register_observers
        from nexus.events import async_event_manager, event_manager

        # Import each observer module
        # We import individually so one failure doesn't prevent others from loading
        successful_imports = 0
        for module_path in OBSERVER_MODULES:
            try:
                __import__(module_path)
                successful_imports += 1
            except ImportError as e:
                logger.warning(f"Failed to import observer module {module_path}: {e}")

        # Register all successfully imported observers with event managers
        registered_count = auto_register_observers(event_manager, async_event_manager)

        logger.info(
            f"Observer registration complete: "
            f"{successful_imports}/{len(OBSERVER_MODULES)} modules loaded, "
            f"{registered_count} observers registered"
        )
