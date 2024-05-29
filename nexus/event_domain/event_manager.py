# Class that will permit subscription in event and notify observers


from .event_observer import EventObserver
from typing import List, Dict, Union


class EventManager:
    def __init__(self):
        self.observers : Dict[str, List[EventObserver]] = {}

    def subscribe(
        self,
        event: str,
        observer: Union[EventObserver, List[EventObserver]]
    ):
        if event not in self.observers:
            self.observers[event] = []

        if isinstance(observer, list):
            self.observers[event].extend(observer)
        else:
            self.observers[event].append(observer)

    def notify(
        self,
        event: str,
        **kwargs
    ):
        print("ENTROU NO NOTIFY")
        observers = self.observers.get(event, [])
        for observer in observers:
            observer.perform(**kwargs)
