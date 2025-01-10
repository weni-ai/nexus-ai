from typing import List, Dict, Tuple
from dataclasses import dataclass

from nexus.agents.models import Agent, Team, ActiveAgent
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase, run_create_lambda_function, BedrockSubAgent

from nexus.usecases.agents.exceptions import AgentInstructionsTooShort


@dataclass
class AgentDTO:
    slug: str
    name: str
    description: str
    instructions: List[str]
    guardrails: List[str]
    skills: List[Dict]
    model: str


class AgentUsecase:
    def __init__(self, external_agent_client=BedrockFileDatabase):
        self.external_agent_client = external_agent_client()

    def prepare_agent(self, agent_id: str):
        self.external_agent_client.prepare_agent(agent_id)
        return

    def create_external_supervisor(
        self,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
    ) -> str:
        return self.external_agent_client.create_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
        )

    def create_external_agent(self, agent_name: str, agent_description: str, agent_instructions: str):
        return self.external_agent_client.create_agent(
            agent_name,
            agent_description,
            agent_instructions
        )

    def create_external_agent_alias(self, agent_id: str, alias_name: str) -> Tuple[str, str]:
        agent_alias_id, agent_alias_arn = self.external_agent_client.create_agent_alias(
            agent_id=agent_id, alias_name=alias_name
        )
        return agent_alias_id, agent_alias_arn

    def create_agent(self, user, agent_dto: AgentDTO, project_uuid: str, alias_name: str = "v1"):

        def format_instructions(instructions: List[str]):
            return "\n".join(instructions)

        external_id, _agent_alias_id, _agent_alias_arn = self.create_external_agent(
            agent_name=agent_dto.slug,
            agent_description=agent_dto.description,
            agent_instructions=format_instructions(agent_dto.instructions),
        )

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
                "_agent_alias_id": _agent_alias_id,
                "_agent_alias_arn": _agent_alias_arn,
                "agent_alias_id": sub_agent_alias_id,
                "agent_alias_arn": sub_agent_alias_arn,
                "agentVersion": str(agent_version),
            }
        )
        return agent

    def create_supervisor(
        self,
        project_uuid: str,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str
    ):
        external_id = self.create_external_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
        )

        Team.objects.create(
            project_id=project_uuid,
            external_id=external_id
        )
        return

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

    def validate_agent_dto(
        self,
        agent_dto: AgentDTO
    ):
        # TODO - Validate slug length to endorse _create_lambda_iam_role policies
        for instruction in agent_dto.instructions:
            if len(instruction) < 40:
                raise AgentInstructionsTooShort

        for guardrail in agent_dto.guardrails:
            if len(guardrail) < 40:
                raise AgentInstructionsTooShort
        return agent_dto

    def yaml_dict_to_dto(
        self,
        yaml: dict
    ) -> list[AgentDTO]:

        agents = []

        for agent_key, agent_value in yaml.get("agents", {}).items():
            agents.append(
                AgentDTO(
                    slug=agent_key,
                    name=agent_value.get("name"),
                    description=agent_value.get("description"),
                    instructions=agent_value.get("instructions"),
                    guardrails=agent_value.get("guardrails"),
                    skills=agent_value.get("skills"),
                    model=agent_value.get("model")
                )
            )
        validate_agents = [self.validate_agent_dto(agent) for agent in agents]
        return validate_agents

    def assign_agent(self, agent_uuid: str, project_uuid: str, created_by):
        agent = Agent.objects.get(uuid=agent_uuid)
        team = Team.objects.get(project__uuid=project_uuid)

        sub_agent = BedrockSubAgent(
            display_name=agent.display_name,
            slug=agent.slug,
            external_id=agent.external_id,
            alias_arn=agent.metadata.get("agent_alias_arn"),
        )

        # TODO temporary solution for testing
        # supervisor_agent_alias_id, supervisor_agent_alias_arn = self.external_agent_client.associate_sub_agents(
        #     supervisor_id=team.external_id,
        #     agents_list=[sub_agent]
        # )

        active_agent, created = ActiveAgent.objects.get_or_create(
            agent=agent,
            team=team,
            is_official=agent.is_official,
            created_by=created_by,
            metadata={
                "supervisor_agent_alias_id": "supervisor_agent_alias_id",
                "supervisor_agent_alias_arn": "supervisor_agent_alias_arn",
            }
        )
        return active_agent

    def unassign_agent(self, agent_uuid: str, project_uuid: str):
        agent = Agent.objects.get(uuid=agent_uuid)
        team = Team.objects.get(project__uuid=project_uuid)

        active_agent = ActiveAgent.objects.get(
            agent=agent,
            team=team
        )

        active_agent.delete()
