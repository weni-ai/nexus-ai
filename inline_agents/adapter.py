from abc import ABC, abstractmethod
from typing import Any

from inline_agents.team import Team


class TeamAdapter(ABC):

    @abstractmethod
    def to_external(self, team: Team) -> Any:
        pass
