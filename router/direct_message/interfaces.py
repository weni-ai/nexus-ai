from typing import List
from abc import ABC, abstractmethod


class DirectMessage(ABC):
    @abstractmethod
    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str) -> None:
        pass