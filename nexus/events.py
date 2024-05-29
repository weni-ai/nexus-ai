from .event_domain.event_manager import EventManager

from nexus.intelligences.observer import IntelligenceCreateObserver


event_manager = EventManager()


event_manager.subscribe(
    event="intelligence_create_activity",
    observer=[IntelligenceCreateObserver()]
)
