

from inline_agents.repository import SupervisorRepository
from nexus.inline_agents.backends.openai.models import (
    OpenAISupervisor as Supervisor,
)
from nexus.inline_agents.models import Agent
from nexus.projects.models import Project


class OpenAISupervisorRepository(SupervisorRepository):
    @classmethod
    def get_supervisor(
        cls,
        project: Project,
        foundation_model: str = None,
    ) -> Agent:

        supervisor = Supervisor.objects.order_by('id').last()

        if not supervisor:
            raise Supervisor.DoesNotExist()

        supervisor_dict = {
            "instruction": cls._get_supervisor_instructions(project=project, supervisor=supervisor),
            "use_components": project.use_components,
            "use_human_support": project.human_support,
            "components_instructions": supervisor.components_prompt,
            "formatter_agent_components_instructions": supervisor.components_human_support_prompt,
            "components_instructions_up": supervisor.components_instructions_up_prompt,
            "human_support_instructions": supervisor.human_support_prompt,
            "tools": cls._get_supervisor_tools(project=project, supervisor=supervisor),
            "foundation_model": cls.get_foundation_model(project=project, supervisor=supervisor, foundation_model=foundation_model),
            "knowledge_bases": supervisor.knowledge_bases,
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "default_instructions_for_collaborators": supervisor.default_instructions_for_collaborators,
            "max_tokens": supervisor.max_tokens,
            "exclude_tools_from_audio_orchestration": supervisor.exclude_tools_from_audio_orchestration,
            "exclude_tools_from_text_orchestration": supervisor.exclude_tools_from_text_orchestration,
            "transcription_instructions": supervisor.transcription_prompt,
        }

        return supervisor_dict

    @classmethod
    def _get_supervisor_instructions(cls, project, supervisor) -> str:
        return supervisor.instruction

    @classmethod
    def _get_supervisor_tools(cls, project, supervisor) -> list[dict]:
        if project.human_support:
            return supervisor.human_support_action_groups
        return supervisor.action_groups
