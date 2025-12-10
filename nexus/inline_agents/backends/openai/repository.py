from inline_agents.repository import SupervisorRepository
from nexus.inline_agents.backends.openai.models import (
    OpenAISupervisor as Supervisor,
)
from nexus.inline_agents.models import Agent


class OpenAISupervisorRepository(SupervisorRepository):
    @classmethod
    def get_supervisor(
        cls,
        foundation_model: str = None,
        # Cached data parameters (always provided from start_inline_agents)
        use_components: bool = None,
        human_support: bool = None,
        default_supervisor_foundation_model: str = None,
    ) -> Agent:
        supervisor = Supervisor.objects.order_by("id").last()

        if not supervisor:
            raise Supervisor.DoesNotExist()

        use_components_value = use_components if use_components is not None else False
        human_support_value = human_support if human_support is not None else False
        default_supervisor_foundation_model_value = default_supervisor_foundation_model

        supervisor_dict = {
            "instruction": cls._get_supervisor_instructions(supervisor=supervisor),
            "use_components": use_components_value,
            "use_human_support": human_support_value,
            "components_instructions": supervisor.components_prompt,
            "formatter_agent_components_instructions": supervisor.components_human_support_prompt,
            "components_instructions_up": supervisor.components_instructions_up_prompt,
            "human_support_instructions": supervisor.human_support_prompt,
            "tools": cls._get_supervisor_tools(supervisor=supervisor, human_support=human_support_value),
            "foundation_model": cls.get_foundation_model(
                supervisor=supervisor, foundation_model=foundation_model, default_supervisor_foundation_model=default_supervisor_foundation_model_value
            ),
            "knowledge_bases": supervisor.knowledge_bases,
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "default_instructions_for_collaborators": supervisor.default_instructions_for_collaborators,
            "max_tokens": supervisor.max_tokens,
        }

        return supervisor_dict

    @classmethod
    def _get_supervisor_instructions(cls, supervisor) -> str:
        return supervisor.instruction

    @classmethod
    def _get_supervisor_tools(cls, supervisor=None, human_support: bool = None) -> list[dict]:
        human_support_value = human_support if human_support is not None else False
        if human_support_value:
            return supervisor.human_support_action_groups
        return supervisor.action_groups
