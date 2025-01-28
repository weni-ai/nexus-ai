from typing import Dict, List, Tuple
from dataclasses import dataclass, field

from django.conf import settings
from django.template.defaultfilters import slugify

from nexus.agents.models import Agent, ActiveAgent, Team
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase, BedrockSubAgent
from nexus.task_managers.tasks_bedrock import run_create_lambda_function

from nexus.usecases.agents.exceptions import (
    AgentInstructionsTooShort,
    AgentNameTooLong,
    SkillNameTooLong,
    AgentAttributeNotAllowed
)


@dataclass
class AgentDTO:
    slug: str
    name: str
    description: str
    instructions: List[str]
    guardrails: List[str]
    skills: List[Dict]
    model: List[str]
    tags: Dict = field(default_factory=dict)
    prompt_override_configuration: Dict = field(default_factory=dict)
    memory_configuration: Dict = field(default_factory=dict)
    idle_session_tll_in_seconds: int = 1800


class AgentUsecase:
    def __init__(self, external_agent_client=BedrockFileDatabase):
        self.external_agent_client = external_agent_client()

    def assign_agent(self, agent_uuid: str, project_uuid: str, created_by):
        agent: Agent = self.get_agent_object(uuid=agent_uuid)
        team: Team = self.get_team_object(project__uuid=project_uuid)

        sub_agent = BedrockSubAgent(
            display_name=agent.display_name,
            slug=agent.slug,
            external_id=agent.external_id,
            alias_arn=agent.metadata.get("agent_alias_arn"),
        )

        self.external_agent_client.associate_sub_agents(
            supervisor_id=team.external_id,
            agents_list=[sub_agent]
        )

        active_agent, created = ActiveAgent.objects.get_or_create(
            agent=agent,
            team=team,
            is_official=agent.is_official,
            created_by=created_by,
        )
        return active_agent

    def create_agent(self, user, agent_dto: AgentDTO, project_uuid: str, alias_name: str = "v1"):

        def format_instructions(instructions: List[str]):
            return "\n".join(instructions)

        external_id = self.create_external_agent(
            agent_name=f"{agent_dto.slug}-project-{project_uuid}",
            agent_description=agent_dto.description,
            agent_instructions=format_instructions(agent_dto.instructions),
            idle_session_tll_in_seconds=agent_dto.idle_session_tll_in_seconds,
            memory_configuration=agent_dto.memory_configuration,
            prompt_override_configuration=agent_dto.prompt_override_configuration,
            tags=agent_dto.tags,
            model_id=agent_dto.model[0],
        )

        self.external_agent_client.agent_for_amazon_bedrock.wait_agent_status_update(external_id)

        self.prepare_agent(external_id)

        self.external_agent_client.agent_for_amazon_bedrock.wait_agent_status_update(external_id)

        sub_agent_alias_id, sub_agent_alias_arn = self.create_external_agent_alias(
            agent_id=external_id, alias_name=alias_name
        )

        agent_version = self.external_agent_client.get_agent_version(external_id)

        agent = Agent.objects.create(
            created_by=user,
            project_id=project_uuid,
            external_id=external_id,
            slug=agent_dto.slug,
            display_name=agent_dto.name,
            model=agent_dto.model,
            description=agent_dto.description,
            metadata={
                "engine": "BEDROCK",
                "external_id": external_id,
                "agent_alias_id": sub_agent_alias_id,
                "agent_alias_arn": sub_agent_alias_arn,
                "agentVersion": str(agent_version),
            }
        )
        return agent

    def create_external_agent(
        self,
        agent_name: str,
        agent_description: str,
        agent_instructions: str,
        model_id: str = None,
        idle_session_tll_in_seconds: int = 1800,
        memory_configuration: Dict = {},
        tags: Dict = {},
        prompt_override_configuration: List[Dict] = []
    ):
        return self.external_agent_client.create_agent(
            agent_name,
            agent_description,
            agent_instructions,
            model_id,
            idle_session_tll_in_seconds,
            memory_configuration,
            tags,
            prompt_override_configuration,
        )

    def create_external_agent_alias(self, agent_id: str, alias_name: str) -> Tuple[str, str]:
        agent_alias_id, agent_alias_arn = self.external_agent_client.create_agent_alias(
            agent_id=agent_id, alias_name=alias_name
        )
        return agent_alias_id, agent_alias_arn

    def create_supervisor(
        self,
        project_uuid: str,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str
    ):
        external_id, alias_name = self.create_external_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
        )

        self.external_agent_client.wait_agent_status_update(external_id)
        team: Team = self.create_team_object(
            project_uuid=project_uuid,
            external_id=external_id
        )
        return team

    def create_external_supervisor(
        self,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
    ) -> Tuple[str, str]:
        return self.external_agent_client.create_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
        )

    def create_skill(
        self,
        file_name: str,
        agent_external_id: str,
        agent_version: str,
        file: bytes,
        function_schema: List[Dict],
    ):
        # TODO - this should use delay()
        run_create_lambda_function(
            agent_external_id=agent_external_id,
            lambda_name=file_name,
            agent_version=agent_version,
            zip_content=file,
            function_schema=function_schema,
        )

    def create_team_object(self, project_uuid: str, external_id: str) -> Team:
        return Team.objects.create(
            project_id=project_uuid,
            external_id=external_id
        )

    def get_agent_object(self, **kwargs) -> Agent:
        """
        external_id: str
        uuid: str
        """
        agent = Agent.objects.get(**kwargs)
        return agent

    def get_team_object(self, **kwargs) -> Team:
        return Team.objects.get(**kwargs)

    def invoke_supervisor(self, session_id, supervisor_id, supervisor_alias_id, prompt, content_base_uuid):
        response = self.external_agent_client.invoke_supervisor(
            supervisor_id=supervisor_id,
            supervisor_alias_id=supervisor_alias_id,
            session_id=session_id,
            prompt=prompt,
            content_base_uuid=content_base_uuid,
        )
        return response

    def invoke_supervisor_stream(self, session_id, supervisor_id, supervisor_alias_id, prompt, content_base_uuid):
        for chunk in self.external_agent_client.invoke_supervisor_stream(
            supervisor_id=supervisor_id,
            supervisor_alias_id=supervisor_alias_id,
            session_id=session_id,
            prompt=prompt,
            content_base_uuid=content_base_uuid,
        ):
            yield chunk

    def prepare_agent(self, agent_id: str):
        self.external_agent_client.prepare_agent(agent_id)
        return

    def unassign_agent(self, agent_uuid, project_uuid):
        agent: Agent = self.get_agent_object(uuid=agent_uuid)
        team: Team = self.get_team_object(project__uuid=project_uuid)
        sub_agent_id = ""

        supervisor_id: str = team.external_id
        collaborators = BedrockFileDatabase().bedrock_agent.list_agent_collaborators(
            agentId=supervisor_id,
            agentVersion='DRAFT'
        )
        summaries = collaborators["agentCollaboratorSummaries"]
        for agent_descriptor in summaries:
            if agent.external_id in agent_descriptor["agentDescriptor"]["aliasArn"]:
                sub_agent_id = agent_descriptor["collaboratorId"]

        if sub_agent_id:
            self.external_agent_client.disassociate_sub_agent(
                supervisor_id=supervisor_id,
                supervisor_version='DRAFT',
                sub_agent_id=sub_agent_id,
            )

    def validate_agent_dto(
        self,
        agent_dto: AgentDTO,
        user_email: str,
    ):
        allowed_users: List[str] = settings.AGENT_CONFIGURATION_ALLOWED_USERS
        if len(agent_dto.slug) > 128:
            raise AgentNameTooLong

        for instruction in agent_dto.instructions:
            if len(instruction) < 40:
                raise AgentInstructionsTooShort

        for guardrail in agent_dto.guardrails:
            if len(guardrail) < 40:
                raise AgentInstructionsTooShort

        for skill in agent_dto.skills:
            if len(skill.get('slug')) > 53:
                raise SkillNameTooLong

        agent_attributes = agent_dto.prompt_override_configuration or agent_dto.memory_configuration
        if agent_attributes and user_email not in allowed_users:
            raise AgentAttributeNotAllowed

        agents_model: List[str] = settings.AWS_BEDROCK_AGENTS_MODEL_ID
        if not set(agent_dto.model).issubset(agents_model) and user_email not in allowed_users:
            raise AgentAttributeNotAllowed

        return agent_dto

    def yaml_dict_to_dto(
        self,
        yaml: dict,
        user_email: str
    ) -> list[AgentDTO]:

        agents = []

        for agent_key, agent_value in yaml.get("agents", {}).items():
            model = agent_value.get("foundationModel")
            agents.append(
                AgentDTO(
                    slug=slugify(agent_value.get('name')),
                    name=agent_value.get("name"),
                    description=agent_value.get("description"),
                    instructions=agent_value.get("instructions"),
                    guardrails=agent_value.get("guardrails"),
                    skills=agent_value.get("skills"),
                    model=model if model else settings.AWS_BEDROCK_AGENTS_MODEL_ID,
                    prompt_override_configuration=agent_value.get("prompt_override_configuration"),
                    memory_configuration=agent_value.get("memory_configuration"),
                    tags=agent_value.get("tags"),
                )
            )
        validate_agents = [self.validate_agent_dto(agent, user_email) for agent in agents]
        return validate_agents

    def wait_agent_status_update(self, external_id: str):
        self.agent_for_amazon_bedrock.wait_agent_status_update(external_id)
