from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from calling.sessions import Session

from abc import ABC, abstractmethod


class EventListener(ABC):  # pragma: no cover

    @abstractmethod
    async def perform(self, event_key: str, session: "Session", **kwargs):
        pass
