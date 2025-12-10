import ast
import json

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
                skills = agent.current_version.skills
                if isinstance(skills, (bytes, bytearray)):
                    try:
                        skills = skills.decode("utf-8")
                    except Exception:
                        skills = "[]"
                # Robust normalization: ensure skills is always a list
                if isinstance(skills, str):
                    try:
                        skills = json.loads(skills)
                    except Exception:
                        try:
                            skills = ast.literal_eval(skills)
                        except Exception:
                            skills = []
                elif not isinstance(skills, list):
                    skills = []
                try:
                    print(
                        "[DBG] skills type:", type(skills), "len:", len(skills) if hasattr(skills, "__len__") else None
                    )
                except Exception:
                    pass
                normalized_skills = []
                for skill in skills:
                    try:
                        print("[DBG] skill type:", type(skill))
                    except Exception:
                        pass
                    if isinstance(skill, str):
                        try:
                            try:
                                skill = json.loads(skill)
                            except Exception:
                                skill = json.loads(skill.replace("'", '"'))
                        except Exception:
                            continue
                    if not isinstance(skill, dict):
                        continue
                    func_schema = skill.get("functionSchema")
                    if isinstance(func_schema, str):
                        try:
                            func_schema = json.loads(func_schema)
                        except Exception:
                            func_schema = {}
                    functions = (func_schema or {}).get("functions") or []
                    for function in functions:
                        if "parameters" in function and isinstance(function["parameters"], list):
                            parametros_combinados = {}
                            for param_dict in function["parameters"]:
                                for key, value in param_dict.items():
                                    parametros_combinados[key] = value
                            function["parameters"] = parametros_combinados
                        elif function.get("parameters") is None:
                            function["parameters"] = {}
                        elif isinstance(function.get("parameters"), dict):
                            pass
                        else:
                            function["parameters"] = {}
                    processed_skill = {
                        "actionGroupName": slugify(skill.get("actionGroupName", "")),
                        "functionSchema": {"functions": functions},
                    }
                    normalized_skills.append(processed_skill)

                agent_dict = {
                    "agentName": agent.slug,
                    "instruction": agent.instruction,
                    "actionGroups": normalized_skills,
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
