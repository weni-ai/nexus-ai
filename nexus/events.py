from .event_domain.event_manager import EventManager

from nexus.intelligences.observer import IntelligenceObserver


event_manager = EventManager()


event_manager.subscribe(
    event="intelligence_activity",
    observer=IntelligenceObserver()
)
