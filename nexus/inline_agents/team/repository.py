from django.utils.text import slugify

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
                skills = []

                skills=agent.current_version.skills
                for index, skill in enumerate(skills):
                    for function in skill["functionSchema"]["functions"]:
                        if "parameters" in function and isinstance(function["parameters"], list):
                            parametros_combinados = {}
                            for param_dict in function["parameters"]:
                                for key, value in param_dict.items():
                                    parametros_combinados[key] = value
                            function["parameters"] = parametros_combinados
                        elif function.get("parameters") is None:
                            function["parameters"] = {}
                    skills[index]["actionGroupName"] = slugify(skill["actionGroupName"])

                agent_dict = {
                    "agentName": agent.slug,
                    "instruction": agent.instruction,
                    "actionGroups": skills,
                    "foundationModel": agent.foundation_model,
                    "agentCollaboration": "DISABLED",
                    "collaborator_configurations": agent.collaboration_instructions,
                }
                agents.append(agent_dict)
            return agents
        except ORMIntegratedAgent.DoesNotExist:
            raise TeamDoesNotExist(f"Team with project uuid: {project_uuid} does not exist")


