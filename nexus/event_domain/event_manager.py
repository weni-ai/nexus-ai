# Class that will permit subscription in event and notify observers


from .event_observer import EventObserver
from typing import List, Dict


class EventManager:
    def __init__(self):
        self.observer : Dict[str, List[EventObserver]] = {}

    def subscribe(
        self,
        event: str,
        observer: EventObserver,
    ):
        self.observer[event] = observer

    def notify(
        self,
        event: str,
        **kwargs
    ):
        print("ENTROU NO NOTIFY")
        observers = self.observer.get(event, [])
        for observer in observers:
            observer.perform(**kwargs)
