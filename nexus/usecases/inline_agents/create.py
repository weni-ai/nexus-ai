import boto3

from django.conf import settings
from django.template.defaultfilters import slugify

from io import BytesIO

from nexus.inline_agents.models import Agent, AgentCredential, ContactField
from nexus.projects.models import Project
from typing import Dict, List
from nexus.internals.flows import FlowsRESTClient


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
    def __init__(self, agent_backend_client = BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def create_agent(self, agent_key: str, agent: dict, project: Project, files: dict):
        instructions_guardrails = agent["instructions"] + agent["guardrails"]
        instructions = "\n".join(instructions_guardrails)
        agent_obj = Agent.objects.create(
            name=agent["name"],
            slug=agent_key,
            collaboration_instructions=agent["description"],
            project=project,
            instruction=instructions,
            foundation_model=settings.AWS_BEDROCK_AGENTS_MODEL_ID,
        )
        self.create_skills(agent_obj, project, agent["tools"], files, str(project.uuid))
        self.create_credentials(agent_obj, project, agent["credentials"])
        return agent

    def create_credentials(self, agent: Agent, project: Project, credentials: Dict):
        if not credentials:
            return
            
        for key, credential in credentials.items():
            is_confidential = credential.get('is_confidential', True)
            
            AgentCredential.objects.create(
                agent=agent,
                project=project,
                key=key,
                label=credential.get('label', key),
                placeholder=credential.get('placeholder', ''),
                is_confidential=is_confidential
            )

    def create_contact_field(self, agent: Agent, project: Project, field_name: str, parameter: Dict):
        types = {
            "string": "text",
            "boolean": "text",
            "array": "text",
            "number": "numeric",
            "integer": "numeric",
        }

        project_uuid = str(project.uuid)

        ContactField.objects.create(
            agent=agent,
            project=project,
            key=field_name,
            value_type=types.get(parameter.get("type"), "text")
        )

        flows_client = FlowsRESTClient()
        flows_client.create_project_contact_field(
            project_uuid=project_uuid,
            key=field_name,
            value_type=types.get(parameter.get("type"), "text")
        )

        flows_client = FlowsRESTClient()
        flows_contact_fields = flows_client.list_project_contact_fields(project_uuid)
        print(f"Created: {field_name} : {flows_contact_fields}")

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
    
    def handle_parameters(self, agent_obj: Agent, project: Project, parameters: List[Dict], project_uuid: str) -> Dict:
        flows_client = FlowsRESTClient()
        flows_contact_fields = flows_client.list_project_contact_fields(project_uuid)

        existing_field_keys = []

        if flows_contact_fields:
            existing_field_keys = [field['key'] for field in flows_contact_fields.get('results', [])]

        for parameter in parameters:
            field_name = list(parameter.keys())[0]
            field_data = parameter[field_name]
            contact_field = field_data.get("contact_field")

            if contact_field and field_name not in existing_field_keys:
                print(f"Creating contact field: {field_name}")
                self.create_contact_field(agent_obj, project, field_name, parameter)
            field_data.pop("contact_field", None)

        return parameters


    def create_skills(self, agent: Agent, project: Project, agent_skills: List[Dict], files: dict, project_uuid: str):
        skills = []
        display_skills = []

        for agent_skill in agent_skills:

            skill_file = files[f"{agent.slug}:{agent_skill['key']}"]
            skill_name = f'{agent_skill.get("key")}-{agent.id}-{slugify(project.name)}'

            action_group_executor: Dict[str, str] = self.create_lambda_function(agent_skill, skill_file, project_uuid, skill_name)
            parameters: List[Dict] = self.handle_parameters(agent, project, agent_skill["parameters"], project_uuid)

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
                    "unique_name": skill_name,
                    "agent": str(agent.uuid)
                }
            )

        agent.versions.create(
            skills=skills,
            display_skills=display_skills,
        )
