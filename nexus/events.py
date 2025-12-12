"""
Event system with decorator-based observer registration.

This module uses decorator-based registration to simplify observer setup.
Observers are registered using @observer decorator on their class definitions.
"""

import logging

from nexus.event_domain.decorators import auto_register_observers
from nexus.event_domain.event_manager import AsyncEventManager, EventManager

logger = logging.getLogger(__name__)

# Create event managers - these can be imported without triggering observer imports
event_manager = EventManager()
async_event_manager = AsyncEventManager()

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

    # Trace observers
    import router.traces_observers.rationale.observer  # noqa: F401
    import router.traces_observers.save_traces  # noqa: F401
    import router.traces_observers.summary  # noqa: F401

    # Auto-register all decorated observers
    auto_register_observers(event_manager, async_event_manager)
except ImportError as e:
    # If imports fail (e.g., during testing), log but don't crash
    logger.warning(f"Failed to import some observer modules: {e}. Some observers may not be registered.")
