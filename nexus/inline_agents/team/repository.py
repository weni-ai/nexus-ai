from django.utils.text import slugify

from inline_agents.team.repository import TeamRepository
from nexus.inline_agents.models import IntegratedAgent as ORMIntegratedAgent
from nexus.projects.models import Project

from .exceptions import TeamDoesNotExist


#  Montar dict e retornar para o bedrock, pegar o integrated do projeto
class ORMTeamRepository(TeamRepository):
    def __init__(self, agents_backend: str = "BedrockBackend", project: Project = None):
        self.agents_backend = agents_backend
        self.project = project

    def get_team(self, project_uuid: str) -> list[dict]:
        try:
            orm_team = (
                ORMIntegratedAgent.objects.filter(project__uuid=project_uuid)
                .select_related("agent")
                .prefetch_related("agent__versions")
            )
            agents = []

            for integrated_agent in orm_team:
                agent = integrated_agent.agent
                skills = []

                skills = agent.current_version.skills or []
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
                    "foundationModel": agent.current_foundation_model(self.agents_backend, self.project),
                    "agentCollaboration": "DISABLED",
                    "collaborator_configurations": agent.collaboration_instructions,
                }

                if self.agents_backend == "OpenAIBackend":
                    agent_dict["agentDisplayName"] = agent.name

                agents.append(agent_dict)
            return agents
        except ORMIntegratedAgent.DoesNotExist as e:
            raise TeamDoesNotExist(f"Team with project uuid: {project_uuid} does not exist") from e
