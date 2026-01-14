from typing import Any, Dict, List, Optional

from inline_agents.repository import SupervisorRepository
from nexus.inline_agents.backends.openai.models import (
    OpenAISupervisor as Supervisor,
)
from nexus.inline_agents.backends.openai.models import SupervisorAgent
from nexus.inline_agents.models import Agent


class OpenAISupervisorRepository(SupervisorRepository):
    _cache_service = None

    @classmethod
    def _get_cache_service(cls, project_uuid: str, supervisor_uuid: Optional[str] = None):
        """Get or create the cache service instance."""
        if cls._cache_service is None:
            from router.services.openai_supervisor_cache_service import SupervisorAgentCacheService

            cls._cache_service = SupervisorAgentCacheService(project_uuid=project_uuid, supervisor_uuid=supervisor_uuid)
        return cls._cache_service

    @classmethod
    def get_supervisor(
        cls,
        project_uuid: str,
        human_support: Optional[bool] = None,
        use_components: Optional[bool] = None,
        supervisor_uuid: Optional[str] = None,
    ) -> dict:
        def get_supervisor_object(project_uuid: str) -> SupervisorAgent:
            try:
                return SupervisorAgent.objects.get(project__uuid=project_uuid)
            except SupervisorAgent.DoesNotExist:
                return SupervisorAgent.objects.filter(default=True, public=True).order_by("created_on").last()

        cache_service = cls._get_cache_service(project_uuid, supervisor_uuid)
        supervisor_data = cache_service.get_supervisor_config(
            project_uuid=project_uuid, fetch_func=get_supervisor_object
        )
        use_human_support: bool = human_support
        use_components: bool = use_components

        user_model_credentials = (
            {
                "api_key": supervisor_data["api_key"],
                "api_base": supervisor_data["api_base"],
                "api_version": supervisor_data["api_version"],
            }
            if supervisor_data["api_key"]
            else {}
        )

        model_settings: Dict[str, Any] = {
            "model_has_reasoning": supervisor_data["model_has_reasoning"],
            "reasoning_effort": supervisor_data["reasoning_effort"],
            "reasoning_summary": supervisor_data["reasoning_summary"],
        }

        supervisor_dict = {
            "instruction": supervisor_data["base_prompt"],
            "use_components": use_components,
            "use_human_support": use_human_support,
            "components_instructions_up": supervisor_data["header_components_prompt"],
            "components_instructions": supervisor_data["footer_components_prompt"],
            "formatter_agent_components_instructions": supervisor_data["formatter_agent_prompt"],
            "human_support_instructions": supervisor_data["human_support_prompt"],
            "tools": cls._get_supervisor_agent_tools(supervisor=supervisor_data, use_human_support=use_human_support),
            "foundation_model": supervisor_data["foundation_model"],
            "model_settings": model_settings,
            "knowledge_bases": supervisor_data["knowledge_bases"],
            "max_tokens": {
                "supervisor": supervisor_data["max_tokens"],
                "collaborator": supervisor_data["collaborator_max_tokens"],
                "audio_orchestration": supervisor_data["audio_orchestration_max_tokens"],
                "audio_orchestration_collaborator": supervisor_data["audio_orchestration_collaborator_max_tokens"],
            },
            "formatter_agent_configurations": {
                "formatter_agent_prompt": supervisor_data["formatter_agent_prompt"],
                "formatter_agent_reasoning_effort": supervisor_data["formatter_agent_reasoning_effort"],
                "formatter_agent_reasoning_summary": supervisor_data["formatter_agent_reasoning_summary"],
                "formatter_agent_send_only_assistant_message": supervisor_data[
                    "formatter_agent_send_only_assistant_message"
                ],
                "formatter_agent_tools_descriptions": supervisor_data["formatter_agent_tools_descriptions"],
                "formatter_agent_foundation_model": supervisor_data["formatter_agent_foundation_model"],
                "formatter_agent_model_has_reasoning": supervisor_data["formatter_agent_model_has_reasoning"],
                "formatter_tools_descriptions": supervisor_data["formatter_tools_descriptions"],
            },
            "user_model_credentials": user_model_credentials,
            "collaborator_configurations": {
                "override_collaborators_foundation_model": supervisor_data["override_collaborators_foundation_model"],
                "collaborators_foundation_model": supervisor_data["collaborators_foundation_model"],
                "default_instructions_for_collaborators": supervisor_data["default_instructions_for_collaborators"],
            },
        }

        return supervisor_dict

    @classmethod
    def _get_supervisor(  # deprecated
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
                supervisor=supervisor,
                foundation_model=foundation_model,
                default_supervisor_foundation_model=default_supervisor_foundation_model_value,
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
    def _get_supervisor_agent_tools(
        cls, supervisor: Dict[str, Any], use_human_support: bool = None
    ) -> List[Dict[str, Any]]:
        if use_human_support:
            return supervisor["human_support_tools"]
        return supervisor["tools"]

    @classmethod
    def _get_supervisor_tools(cls, supervisor=None, use_human_support: bool = None) -> list[dict]:
        if use_human_support:
            return supervisor.human_support_action_groups
        return supervisor.action_groups
