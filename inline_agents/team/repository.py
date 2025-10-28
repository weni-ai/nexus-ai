from abc import ABC, abstractmethod


class TeamRepository(ABC):
    @abstractmethod
    def get_team(self, project_uuid: str) -> dict:
        pass
