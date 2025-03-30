from nexus.inline_agents.models import Team as ORMTeam

from inline_agents.team import TeamRepository, Team

from .exceptions import TeamDoesNotExist


class ORMTeamRepository(TeamRepository):
    def get_team(self, project_uuid: str) -> Team:
        try: 
            orm_team = ORMTeam.objects.get(project_uuid=project_uuid)
        except ORMTeam.DoesNotExist:
            raise TeamDoesNotExist(f"Team with project uuid: {project_uuid} does not exist")
        # TODO: Create conversion logic from ORMTeam to Team
