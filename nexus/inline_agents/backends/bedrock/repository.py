from nexus.inline_agents.backends import Supervisor


class BedrockSupervisorRepository():

    @classmethod
    def get_supervisor(
        cls,
        project_uuid: str
    ) -> dict:
        from nexus.projects.models import Project

        project = Project.objects.get(uuid=project_uuid)
        supervisor = Supervisor.objects.order_by('id').last()

        if not supervisor:
            raise Supervisor.DoesNotExist()

        supervisor_dict = {
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "instruction": supervisor.instruction,
            "action_groups": cls._get_action_groups(project=project, supervisor=supervisor),
            "foundation_model": supervisor.foundation_model,
            "knowledge_bases": supervisor.knowledge_bases,
            "agent_collaboration": cls._get_agent_collaboration(project=project),
        }

        return supervisor_dict

    @classmethod
    def _get_agent_collaboration(cls, project) -> str:
        # if there is agents in the team return "SUPERVISOR"
        if project.integrated_agents.exists():
            return "SUPERVISOR"

        return "DISABLED"

    @classmethod
    def _get_action_groups(cls, project, supervisor) -> list[dict]:
        if not project.human_support:
            return supervisor.action_groups

        return supervisor.human_support_action_groups
