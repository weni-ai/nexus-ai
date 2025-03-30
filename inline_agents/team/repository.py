from abc import ABC

from typing import Any
from inline_agents.team import Team


class TeamRepository(ABC):
    def get_team(self, project_uuid: str) -> Team:
        pass
