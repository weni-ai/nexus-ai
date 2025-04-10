from nexus.inline_agents.models import Agent, IntegratedAgent


class GetInlineAgentsUsecase:
    def get_active_agents(self, project_uuid: str) -> list[Agent]:
        return IntegratedAgent.objects.filter(project__uuid=project_uuid)
