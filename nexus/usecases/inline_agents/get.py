from nexus.inline_agents.models import (
    Agent,
    IntegratedAgent,
    AgentCredential
)
from nexus.usecases.inline_agents.bedrock import BedrockClient


class GetInlineAgentsUsecase:
    def get_active_agents(self, project_uuid: str) -> list[Agent]:
        return IntegratedAgent.objects.filter(project__uuid=project_uuid)


class GetInlineCredentialsUsecase:
    def get_credentials_by_project(self, project_uuid: str) -> tuple[list[AgentCredential], list[AgentCredential]]:
        active_agents = IntegratedAgent.objects.filter(project__uuid=project_uuid)
        active_agent_ids = active_agents.values_list('agent_id', flat=True)
        credentials = AgentCredential.objects.filter(
            project__uuid=project_uuid,
            agents__in=active_agent_ids
        )

        official_credentials = credentials.filter(agents__is_official=True).distinct()
        custom_credentials = credentials.filter(agents__is_official=False).distinct()

        return official_credentials, custom_credentials


class GetLogGroupUsecase:
    def __init__(self, log_group_client = BedrockClient):
        self.log_group_client = log_group_client()

    def get_log_group(self, project_uuid: str, agent_key: str, tool_key: str) -> str:
        agent = Agent.objects.get(slug=agent_key, project__uuid=project_uuid)
        log_group = self.log_group_client.get_log_group(f'{tool_key}-{agent.id}')
        return log_group
