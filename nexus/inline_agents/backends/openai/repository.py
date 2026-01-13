from typing import Any, Dict, Union

from inline_agents.repository import SupervisorRepository
from nexus.inline_agents.backends.openai.models import (
    OpenAISupervisor as Supervisor,
)


class OpenAISupervisorRepository(SupervisorRepository):
    """
    Repository for OpenAI Supervisor configuration.

    The supervisor data is cached using OpenAISupervisorCacheService.
    Cache is invalidated when supervisor is updated in Django admin.
    """

    _cache_service = None

    @classmethod
    def _get_cache_service(cls):
        """Get or create the cache service instance."""
        if cls._cache_service is None:
            from router.services.openai_supervisor_cache_service import OpenAISupervisorCacheService

            cls._cache_service = OpenAISupervisorCacheService()
        return cls._cache_service

    @classmethod
    def get_supervisor(
        cls,
        foundation_model: str = None,
        # Cached data parameters (always provided from start_inline_agents)
        use_components: bool = None,
        human_support: bool = None,
        default_supervisor_foundation_model: str = None,
    ) -> Dict[str, Any]:
        """
        Get the OpenAI Supervisor configuration.

        Uses cache by default. Falls back to DB if cache is empty.
        """
        # Get supervisor data from cache (or DB if cache miss)
        cache_service = cls._get_cache_service()
        supervisor_data = cache_service.get_supervisor_config()

        if not supervisor_data:
            raise Supervisor.DoesNotExist()

        use_components_value = use_components if use_components is not None else False
        human_support_value = human_support if human_support is not None else False
        default_supervisor_foundation_model_value = default_supervisor_foundation_model

        supervisor_dict = {
            "instruction": cls._get_supervisor_instructions(supervisor=supervisor_data),
            "use_components": use_components_value,
            "use_human_support": human_support_value,
            "components_instructions": supervisor_data.get("components_prompt"),
            "formatter_agent_components_instructions": supervisor_data.get("components_human_support_prompt"),
            "components_instructions_up": supervisor_data.get("components_instructions_up_prompt"),
            "human_support_instructions": supervisor_data.get("human_support_prompt"),
            "tools": cls._get_supervisor_tools(supervisor=supervisor_data, human_support=human_support_value),
            "foundation_model": cls.get_foundation_model(
                supervisor=supervisor_data,
                foundation_model=foundation_model,
                default_supervisor_foundation_model=default_supervisor_foundation_model_value,
            ),
            "knowledge_bases": supervisor_data.get("knowledge_bases"),
            "prompt_override_configuration": supervisor_data.get("prompt_override_configuration"),
            "default_instructions_for_collaborators": supervisor_data.get("default_instructions_for_collaborators"),
            "max_tokens": supervisor_data.get("max_tokens"),
        }

        return supervisor_dict

    @classmethod
    def _get_supervisor_instructions(cls, supervisor: Union[Supervisor, Dict[str, Any]]) -> str:
        """Get supervisor instructions from model or dict."""
        if isinstance(supervisor, dict):
            return supervisor.get("instruction", "")
        return supervisor.instruction

    @classmethod
    def _get_supervisor_tools(
        cls, supervisor: Union[Supervisor, Dict[str, Any]] = None, human_support: bool = None
    ) -> list[dict]:
        """Get supervisor tools (action_groups) from model or dict."""
        human_support_value = human_support if human_support is not None else False

        if isinstance(supervisor, dict):
            if human_support_value:
                return supervisor.get("human_support_action_groups") or []
            return supervisor.get("action_groups") or []

        # Legacy support for model instance
        if human_support_value:
            return supervisor.human_support_action_groups
        return supervisor.action_groups

    @classmethod
    def invalidate_cache(cls) -> None:
        """Invalidate the supervisor cache. Called when supervisor is updated."""
        cache_service = cls._get_cache_service()
        cache_service.invalidate_cache(refresh=True)
