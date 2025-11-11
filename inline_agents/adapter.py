from abc import ABC, abstractmethod
from typing import Any

from inline_agents.team import Team


class TeamAdapter(ABC):
    @abstractmethod
    def to_external(self, team: Team) -> Any:
        pass


class DataLakeEventAdapter(ABC):
    @abstractmethod
    def to_data_lake_event(self, inline_trace: dict):
        pass
