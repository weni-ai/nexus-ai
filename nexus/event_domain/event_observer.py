from abc import ABC, abstractmethod


class EventObserver(ABC):
    @abstractmethod
    def perform(self, event):
        pass
