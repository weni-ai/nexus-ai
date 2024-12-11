from typing import List
from abc import ABC, abstractmethod


class FlowStart(ABC):  # pragma: no cover
    @abstractmethod
    def start_flow(
        self,
        flow: str,
        user: str,
        urns: List,
        user_message: str,
        msg_event: dict = None,
        llm_response: str = None,
    ) -> None:
        pass
