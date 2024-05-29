from .event_domain.event_manager import EventManager

from nexus.intelligences.observer import (
    IntelligenceCreateObserver,
    LLMUpdateObserver
)


event_manager = EventManager()


event_manager.subscribe(
    event="intelligence_create_activity",
    observer=[IntelligenceCreateObserver()]
)

event_manager.subscribe(
    event="llm_update_activity",
    observer=[LLMUpdateObserver()]
)
