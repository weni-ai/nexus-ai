from nexus.inline_agents.backends import Supervisor
from django.conf import settings

class BedrockSupervisorRepository():

    @classmethod
    def get_supervisor(
        cls,
        project_uuid: str,
        foundation_model: str = None,
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
            "foundation_model": cls.get_foundation_model(project=project, supervisor=supervisor, foundation_model=foundation_model),
            "knowledge_bases": supervisor.knowledge_bases,
            "agent_collaboration": cls._get_agent_collaboration(project=project),
        }

        return supervisor_dict

    @classmethod
    def get_foundation_model(cls, project, supervisor: Supervisor, foundation_model: str = None) -> str:
        if foundation_model in settings.LOCKED_FOUNDATION_MODELS:
            return foundation_model

        custom_project_model = project.default_supervisor_foundation_model
        if custom_project_model:
            return custom_project_model


        supervisor_default_model = supervisor.foundation_model

        if foundation_model:
            supervisor_default_model = foundation_model

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
