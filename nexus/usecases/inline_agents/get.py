from nexus.inline_agents.models import Agent, AgentCredential, IntegratedAgent
from nexus.usecases.inline_agents.bedrock import BedrockClient


class GetInlineAgentsUsecase:
    _agent_group_prefetch = ("agent", "agent__group", "agent__group__modal")

    def get_active_agents(self, project_uuid: str):
        return IntegratedAgent.objects.filter(project__uuid=project_uuid, is_active=True).select_related(
            *self._agent_group_prefetch
        )

    def get_integrated_agents(self, project_uuid: str):
        """Return all integrated agents for the project, regardless of is_active."""
        return IntegratedAgent.objects.filter(project__uuid=project_uuid).select_related(*self._agent_group_prefetch)


class GetInlineCredentialsUsecase:
    def get_credentials_by_project(self, project_uuid: str) -> tuple[list[AgentCredential], list[AgentCredential]]:
        active_agents = IntegratedAgent.objects.filter(project__uuid=project_uuid, is_active=True)
        active_agent_ids = active_agents.values_list("agent_id", flat=True)
        credentials = AgentCredential.objects.filter(project__uuid=project_uuid, agents__in=active_agent_ids).distinct()

        official_credentials = []
        custom_credentials = []

        for credential in credentials:
            # Check if any agent associated with this credential is official
            has_official_agent = credential.agents.filter(is_official=True).exists()
            if has_official_agent:
                official_credentials.append(credential)
            else:
                custom_credentials.append(credential)

        return official_credentials, custom_credentials

    def get_credentials_by_project_all_integrated(
        self, project_uuid: str
    ) -> tuple[list[AgentCredential], list[AgentCredential]]:
        """Return credentials for all integrated agents in the project, regardless of is_active."""
        integrated_agents = IntegratedAgent.objects.filter(project__uuid=project_uuid)
        agent_ids = integrated_agents.values_list("agent_id", flat=True)
        credentials = AgentCredential.objects.filter(project__uuid=project_uuid, agents__in=agent_ids).distinct()

        official_credentials = []
        custom_credentials = []

        for credential in credentials:
            has_official_agent = credential.agents.filter(is_official=True).exists()
            if has_official_agent:
                official_credentials.append(credential)
            else:
                custom_credentials.append(credential)

        return official_credentials, custom_credentials


class GetLogGroupUsecase:
    def __init__(self, log_group_client=BedrockClient):
        self.log_group_client = log_group_client()

    def get_log_group(self, project_uuid: str, agent_key: str, tool_key: str) -> str:
        agent = Agent.objects.get(slug=agent_key, project__uuid=project_uuid)
        log_group = self.log_group_client.get_log_group(f"{tool_key}-{agent.id}")
        return log_group
