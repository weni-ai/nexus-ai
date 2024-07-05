from abc import ABC, abstractmethod


class EventObserver(ABC):  # pragma: no cover
    @abstractmethod
    def perform(self, event):
        pass
