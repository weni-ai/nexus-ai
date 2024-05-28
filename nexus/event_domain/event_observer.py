# Interface, define como um observador deve ser implementado

from abc import ABC, abstractmethod


class EventObserver(ABC):
    @abstractmethod
    def perform(self, event):
        pass
