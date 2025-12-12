import logging
from io import BytesIO
from typing import Dict, List, Tuple

from django.conf import settings

from nexus.inline_agents.models import Agent, ContactField
from nexus.internals.flows import FlowsRESTClient
from nexus.projects.models import Project
from nexus.usecases.inline_agents.bedrock import BedrockClient


class ToolsUseCase:
    # skills will be renamed to tools

    TOOL_NAME_FORMAT = "{tool_key}-{agent_id}"

    def __init__(self, agent_backend_client=BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def create_lambda_function(self, tool: Dict, tool_file, project_uuid: str, tool_name: str) -> Dict[str, str]:
        logging.getLogger(__name__).info("Creating lambda function", extra={"tool_name": tool_name})
        zip_buffer = BytesIO(tool_file.read())
        lambda_role = settings.AGENT_RESOURCE_ROLE_ARN
        skill_handler = tool.get("source").get("entrypoint")
        lambda_name = tool_name

        lambda_arn = self.agent_backend_client.create_lambda_function(
            lambda_name=lambda_name, lambda_role=lambda_role, skill_handler=skill_handler, zip_buffer=zip_buffer
        )

        return {"lambda": lambda_arn}

    def delete_lambda_function(self, function_name: str):
        self.agent_backend_client.delete_lambda_function(function_name)

    def update_lambda_function(self, tool: Dict, tool_file, project_uuid: str, tool_name: str) -> Dict[str, str]:
        zip_buffer = BytesIO(tool_file.read())
        lambda_name = tool_name

        lambda_arn = self.agent_backend_client.update_lambda_function(lambda_name=lambda_name, zip_buffer=zip_buffer)

        return lambda_arn

    def create_tool(
        self,
        agent: Agent,
        project: Project,
        agent_tool: Dict,
        tool_file,
        tool_name: str,
    ) -> Tuple[Dict, Dict]:
        project_uuid = str(project.uuid)
        action_group_executor: Dict[str, str] = self.create_lambda_function(
            agent_tool, tool_file, project_uuid, tool_name
        )
        parameters: List[Dict] = self.handle_parameters(agent, project, agent_tool.get("parameters", []), project_uuid)
        response = self._format_tool_response(agent_tool, tool_name, parameters, action_group_executor, str(agent.uuid))
        return response

    def delete_tool(
        self, agent: Agent, project: Project, agent_tool: Dict, tool_file, tool_name: str
    ) -> Tuple[Dict, Dict]:
        project_uuid = str(project.uuid)
        self.handle_parameters(agent, project, agent_tool.get("parameters", []), project_uuid)
        self.delete_lambda_function(tool_name)
        return

    def update_tool(
        self, agent: Agent, project: Project, agent_tool: Dict, tool_file, tool_name: str
    ) -> Tuple[Dict, Dict]:
        project_uuid = str(project.uuid)
        action_group_executor = self.update_lambda_function(agent_tool, tool_file, project_uuid, tool_name)
        parameters: List[Dict] = self.handle_parameters(agent, project, agent_tool.get("parameters", []), project_uuid)
        response = self._format_tool_response(agent_tool, tool_name, parameters, action_group_executor, str(agent.uuid))
        return response

    def create_contact_field(
        self, agent: Agent, project: Project, field_name: str, parameter: Dict, external_create: bool = True
    ):
        types = {
            "string": "text",
            "boolean": "text",
            "array": "text",
            "number": "numeric",
            "integer": "numeric",
        }

        project_uuid = str(project.uuid)

        ContactField.objects.create(
            agent=agent, project=project, key=field_name, value_type=types.get(parameter.get("type"), "text")
        )
        if external_create:
            flows_client = FlowsRESTClient()
            flows_client.create_project_contact_field(
                project_uuid=project_uuid, key=field_name, value_type=types.get(parameter.get("type"), "text")
            )

        return parameter

    def __format_action_group_name(self, action_group_name: str) -> str:
        words = action_group_name.replace("_", "-").split("-")
        pascal_case = "".join(word.capitalize() for word in words)
        return pascal_case

    def _format_tool_response(
        self,
        agent_tool: Dict,
        tool_name: str,
        parameters: List[Dict],
        action_group_executor: Dict[str, str],
        agent_uuid: str,
    ) -> Tuple[Dict, Dict]:
        logging.getLogger(__name__).debug("Formatting tool response", extra={"tool_name": tool_name})
        logging.getLogger(__name__).debug("Tool parameters", extra={"params_keys": list(agent_tool.keys())})
        function = {"name": tool_name, "parameters": parameters, "requireConfirmation": "DISABLED"}
        skill = {
            "actionGroupExecutor": action_group_executor,
            "actionGroupName": self.__format_action_group_name(agent_tool.get("slug")),
            "functionSchema": {"functions": [function]},
            "description": agent_tool.get("description"),
        }
        display_skill = {"icon": "", "name": agent_tool["name"], "unique_name": tool_name, "agent": agent_uuid}
        return skill, display_skill

    def handle_parameters(self, agent_obj: Agent, project: Project, parameters: List[Dict], project_uuid: str) -> Dict:
        flows_client = FlowsRESTClient()
        flows_contact_fields = flows_client.list_project_contact_fields(project_uuid)
        db_existing_fields = ContactField.objects.filter(agent=agent_obj, project=project).values_list("key", flat=True)

        existing_field_keys = []
        if flows_contact_fields:
            existing_field_keys = [field["key"] for field in flows_contact_fields.get("results", [])]

        fields_to_keep = []
        if parameters:
            for parameter in parameters:
                field_name = list(parameter.keys())[0]
                field_data = parameter[field_name]
                contact_field = field_data.get("contact_field")

                if contact_field:
                    fields_to_keep.append(field_name)
                    if field_name not in existing_field_keys and field_name not in db_existing_fields:
                        logging.getLogger(__name__).info("Creating contact field", extra={"field_name": field_name})
                        self.create_contact_field(agent_obj, project, field_name, parameter, external_create=True)
                    elif field_name in existing_field_keys and field_name not in db_existing_fields:
                        logging.getLogger(__name__).info("Creating contact field", extra={"field_name": field_name})
                        self.create_contact_field(agent_obj, project, field_name, parameter, external_create=False)

                field_data.pop("contact_field", None)

        self.delete_contact_fields(agent_obj, project, fields_to_keep, project_uuid)
        return parameters

    def delete_contact_fields(self, agent: Agent, project: Project, fields_to_keep: List[str], project_uuid: str):
        # flows_client = FlowsRESTClient()
        existing_contact_fields = ContactField.objects.filter(agent=agent, project=project)
        for field in existing_contact_fields:
            if field.key not in fields_to_keep:
                logging.getLogger(__name__).info("Deleting contact field", extra={"field_name": field.key})
                field.delete()
                # flows_client.delete_project_contact_field(project_uuid, field.key)

    def handle_tools(self, agent: Agent, project: Project, agent_tools: List[Dict], files: dict, project_uuid: str):
        logging.getLogger(__name__).info("Handling tools for agent", extra={"agent_slug": agent.slug})
        display_skills = []
        existing_skills = []

        skills_to_create = []
        skills_to_update = []
        skills_to_delete = []

        new_skill_names = [
            self.TOOL_NAME_FORMAT.format(
                tool_key=skill.get("key"),
                agent_id=agent.id,
            )
            for skill in agent_tools
        ]
        skills_to_create = new_skill_names

        new_agent_tools = []
        new_agent_display_tools = []

        agent_current_version = agent.current_version

        if agent_current_version:
            display_skills = agent_current_version.display_skills
            existing_skills = [skill.get("unique_name") for skill in display_skills]

            skills_to_delete = [skill for skill in existing_skills if skill not in new_skill_names]
            skills_to_create = [skill for skill in new_skill_names if skill not in existing_skills]
            skills_to_update = [skill for skill in existing_skills if skill in new_skill_names]

        for agent_skill in agent_tools:
            skill_name = self.TOOL_NAME_FORMAT.format(tool_key=agent_skill.get("key"), agent_id=agent.id)
            skill_file = files[f"{agent.slug}:{agent_skill['key']}"]

            if skill_name in skills_to_create:
                logging.getLogger(__name__).info("Creating tool", extra={"skill_name": skill_name})
                skill_file = files[f"{agent.slug}:{agent_skill['key']}"]
                tool, display_tool = self.create_tool(agent, project, agent_skill, skill_file, skill_name)

                new_agent_tools.append(tool)
                new_agent_display_tools.append(display_tool)

            elif skill_name in skills_to_update:
                logging.getLogger(__name__).info("Updating tool", extra={"skill_name": skill_name})
                tool, display_tool = self.update_tool(agent, project, agent_skill, skill_file, skill_name)
                new_agent_tools.append(tool)
                new_agent_display_tools.append(display_tool)

        for skill_name in skills_to_delete:
            logging.getLogger(__name__).info("Deleting tool", extra={"skill_name": skill_name})
            self.delete_tool(agent, project, agent_skill, skill_file, skill_name)

        agent.versions.create(
            skills=new_agent_tools,
            display_skills=new_agent_display_tools,
        )
