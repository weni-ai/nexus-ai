from inline_agents.team.repository import TeamRepository

from nexus.inline_agents.models import IntegratedAgent as ORMIntegratedAgent

from .exceptions import TeamDoesNotExist


#  Montar dict e retornar para o bedrock, pegar o integrated do projeto
class ORMTeamRepository(TeamRepository):
    def get_team(self, project_uuid: str) -> list[dict]:
        try:
            orm_team = ORMIntegratedAgent.objects.filter(project__uuid=project_uuid)
            agents = []

            for integrated_agent in orm_team:
                agent = integrated_agent.agent

                agent_dict = {
                    "agentName": agent.name,
                    "instruction": agent.instruction,
                    "actionGroups": agent.current_version.skills,
                    "foundationModel": agent.foundation_model,
                    "agentCollaboration": "DISABLED",
                    "collaborator_configurations": agent.collaborator_configurations,
                }
                agents.append(agent_dict)

            return agents
        except ORMIntegratedAgent.DoesNotExist:
            raise TeamDoesNotExist(f"Team with project uuid: {project_uuid} does not exist")
