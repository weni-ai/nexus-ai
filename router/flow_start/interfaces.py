from typing import List
from abc import ABC, abstractmethod


class FlowStart(ABC):
    @abstractmethod
    def start_flow(self, flow: str, user: str, urns: List) -> None:
        pass
