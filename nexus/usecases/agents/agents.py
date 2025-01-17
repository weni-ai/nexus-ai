from typing import Dict, List, Tuple
from dataclasses import dataclass

from nexus.agents.models import Agent, ActiveAgent, Team
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase, BedrockSubAgent


@dataclass
class AgentDTO:
    slug: str
    name: str
    description: str
    instructions: List[str]
    guardrails: List[str]
    skills: List[Dict]
    model: List[str]


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

    def wait_agent_status_update(self, external_id: str):
        self.agent_for_amazon_bedrock.wait_agent_status_update(external_id)
