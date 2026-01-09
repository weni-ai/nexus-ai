import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

OBSERVER_MODULES = [
    "nexus.actions.observers",
    "nexus.intelligences.observer",
    "nexus.logs.observers",
    "nexus.projects.observer",
    "router.services.cache_invalidation_observers",
    "router.tasks.workflow_observers",
    "router.traces_observers.rationale.observer",
    "router.traces_observers.save_traces",
    "router.traces_observers.summary",
]


class ObserversConfig(AppConfig):
    name = "nexus.observers"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        self._register_observers()

    def _register_observers(self):
        from nexus.event_domain.decorators import auto_register_observers
        from nexus.events import async_event_manager, event_manager

        for module_path in OBSERVER_MODULES:
            try:
                __import__(module_path)
            except ImportError as e:
                logger.warning(f"Failed to import observer module {module_path}: {e}")

        auto_register_observers(event_manager, async_event_manager)
