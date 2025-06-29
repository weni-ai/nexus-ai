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
            "instruction": cls._get_supervisor_instructions(project=project, supervisor=supervisor),
            "action_groups": cls._get_action_groups(project=project, supervisor=supervisor),
            "foundation_model": cls.get_foundation_model(project_uuid=project_uuid, supervisor=supervisor),
            "knowledge_bases": supervisor.knowledge_bases,
            "agent_collaboration": cls._get_agent_collaboration(project=project),
        }

        return supervisor_dict

    @classmethod
    def get_foundation_model(cls, project_uuid: str, supervisor: Supervisor) -> str:
        from nexus.projects.models import Project

        project = Project.objects.get(uuid=project_uuid)
        supervisor_default_model = supervisor.foundation_model
        custom_project_model = project.default_supervisor_foundation_model

        if custom_project_model:
            return custom_project_model

        return supervisor_default_model

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

    @classmethod
    def _get_supervisor_instructions(cls, project, supervisor) -> str:
        if project.use_components and project.human_support:
            return supervisor.components_human_support_prompt
        elif project.use_components:
            return supervisor.components_prompt
        elif project.human_support:
            return supervisor.human_support_prompt
        else:
            return supervisor.instruction
