from nexus.inline_agents.models import (
    Agent,
    IntegratedAgent,
    AgentCredential
)


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
