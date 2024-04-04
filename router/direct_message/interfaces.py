from abc import ABC, abstractmethod


class DirectMessage(ABC):
    @abstractmethod
    def send_direct_message(self, text: str, urn, project: str, user: str) -> None:
        pass
