from nexus.inline_agents.models import Agent
from nexus.projects.models import Project
from django.template.defaultfilters import slugify
from typing import Dict, List
from io import BytesIO
import boto3
from django.conf import settings


class BedrockClient:
    def __init__(self):
        self.lambda_client = boto3.client(
            "lambda",
            region_name=settings.AWS_BEDROCK_REGION_NAME
        )

    def create_lambda_function(
            self,
            lambda_name: str,
            lambda_role: str,
            skill_handler: str,
            zip_buffer: BytesIO
        ) -> Dict[str, str]:

        lambda_function = self.lambda_client.create_function(
            FunctionName=lambda_name,
            Runtime='python3.12',
            Timeout=180,
            Role=lambda_role,
            Code={'ZipFile': zip_buffer.getvalue()},
            Handler=skill_handler
        )
        lambda_arn = lambda_function.get("FunctionArn")

        return lambda_arn


class CreateAgentUseCase:
    def __init__(self, agent_backend_client: BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def create_agent(self, agent: dict, project: Project, files: dict):
        print(agent)
        # raise ZeroDivisionError
        instructions_guardrails = agent["instructions"] + agent["guardrails"]
        instructions = "\n".join(instructions_guardrails)
        agent_obj = Agent.objects.create(
            name=agent["name"],
            slug=slugify(agent["name"]),
            collaboration_instructions=agent["description"],
            project=project,
            instruction=instructions,
            foundation_model="",
        )
        self.create_skills(agent_obj, project, agent["skills"], files, str(project.uuid))
        return agent

    def create_contact_field(self, parameter: Dict):
        # TODO: Create contact field
        return parameter

    def create_lambda_function(self, skill: Dict, skill_file, project_uuid: str, skill_name: str) -> Dict[str, str]:
        zip_buffer = BytesIO(skill_file.read())
        lambda_role = settings.AGENT_RESOURCE_ROLE_ARN
        skill_handler = skill.get("source").get("entrypoint")
        lambda_name = skill_name

        lambda_arn = self.agent_backend_client.create_lambda_function(
            lambda_name=lambda_name,
            lambda_role=lambda_role,
            skill_handler=skill_handler,
            zip_buffer=zip_buffer
        )

        return {
            "lambda": lambda_arn
        }

    def handle_parameters(self, parameters: List[Dict]) -> Dict:
        for parameter in parameters:
            field_name = list(parameter.keys())[0]
            parameter = parameter[field_name]
            contact_field = parameter["contact_field"]
            if contact_field:
                self.create_contact_field(parameter)
            parameter.pop("contact_field", None)
        return parameters

    def create_skills(self, agent: Agent, project: Project, agent_skills: List[Dict], files: dict, project_uuid: str):
        skills = []
        display_skills = []

        for agent_skill in agent_skills:

            skill_file = files[f"{agent.slug}:{agent_skill['slug']}"]
            skill_name = f'{agent_skill.get("slug")}-{agent.id}'

            action_group_executor: Dict[str, str] = self.create_lambda_function(agent_skill, skill_file, project_uuid, skill_name)
            parameters: List[Dict] = self.handle_parameters(agent_skill["parameters"])

            function = {
                "name": skill_name,
                "parameters": parameters,
                "requireConfirmation": "DISABLED"
            }

            skill = {
                "actionGroupExecutor": action_group_executor,
                "actionGroupName":skill_name,
                "functionSchema": {
                    "functions": [function]
                }
            }
            skills.append(skill)
            display_skills.append(
                {
                    "icon": "",
                    "name": agent_skill["name"],
                }
            )

        agent.versions.create(
            skills=skills,
            display_skills=display_skills,
        )