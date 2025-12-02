from abc import ABC, abstractmethod
from typing import Dict, List


class DirectMessage(ABC):  # pragma: no cover
    @abstractmethod
    def send_direct_message(
        self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict] = None, **kwargs
    ) -> None:
        pass
