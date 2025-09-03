import asyncio

from typing import List, Dict, Union

from celery import shared_task
from nexus.event_domain.event_observer import EventObserver


class EventManager:
    def __init__(self):
        self.observers: Dict[str, List[EventObserver]] = {}

    def subscribe(
        self, event: str, observer: Union[EventObserver, List[EventObserver]]
    ):
        if event not in self.observers:
            self.observers[event] = []

        if isinstance(observer, list):
            self.observers[event].extend(observer)
        else:
            self.observers[event].append(observer)

    def notify(self, event: str, **kwargs):
        observers = self.observers.get(event, [])
        for observer in observers:
            observer.perform(**kwargs)

    def notify_with_celery(self, event: str, **kwargs):
        process_event_observers.delay(event, **kwargs)


class AsyncEventManager:
    def __init__(self):
        self.observers: Dict[str, List[EventObserver]] = {}

    def subscribe(
        self, event: str, observer: Union[EventObserver, List[EventObserver]]
    ):
        if event not in self.observers:
            self.observers[event] = []

        if isinstance(observer, list):
            self.observers[event].extend(observer)
        else:
            self.observers[event].append(observer)

    async def notify(self, event: str, **kwargs):
        observers = self.observers.get(event, [])
        for observer in observers:
            if hasattr(observer, "perform") and asyncio.iscoroutinefunction(
                observer.perform
            ):
                await observer.perform(**kwargs)
            else:
                observer.perform(**kwargs)


@shared_task()
def process_event_observers(event: str, **kwargs):
    from nexus.events import event_manager

    observers = event_manager.observers.get(event, [])
    for observer in observers:
        observer.perform(**kwargs)
