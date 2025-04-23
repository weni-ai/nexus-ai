from abc import ABC


class TeamRepository(ABC):
    def get_team(self, project_uuid: str) -> dict:
        pass
