import logging
from typing import Any, Callable, Dict, Optional

from router.repositories import Repository

logger = logging.getLogger(__name__)


class OpenAISupervisorCacheService:
    """
    Service for caching OpenAI Supervisor configuration data.
    
    Unlike project-specific caches, the OpenAI Supervisor is a GLOBAL configuration.
    There's only one active supervisor (the last one by ID).
    
    Cache key: "openai_supervisor:config"
    """

    # TTL constant - Long TTL since config rarely changes
    SUPERVISOR_TTL = 86400  # 24 hours

    # Cache key for the supervisor configuration
    CACHE_KEY = "openai_supervisor:config"

    def __init__(self, cache_repository: Optional[Repository] = None):
        if cache_repository is None:
            from router.repositories.redis.cache import CacheRepository

            cache_repository = CacheRepository()
        self.cache_repository = cache_repository

    def _supervisor_to_dict(self, supervisor) -> Dict[str, Any]:
        """Convert OpenAISupervisor model to dictionary for caching."""
        return {
            "id": supervisor.id,
            "name": supervisor.name,
            "instruction": supervisor.instruction,
            "foundation_model": supervisor.foundation_model,
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "action_groups": supervisor.action_groups,
            "knowledge_bases": supervisor.knowledge_bases,
            "human_support_prompt": supervisor.human_support_prompt,
            "human_support_action_groups": supervisor.human_support_action_groups,
            "components_prompt": supervisor.components_prompt,
            "components_human_support_prompt": supervisor.components_human_support_prompt,
            "components_instructions_up_prompt": supervisor.components_instructions_up_prompt,
            "default_instructions_for_collaborators": supervisor.default_instructions_for_collaborators,
            "max_tokens": supervisor.max_tokens,
            "max_tokens_collaborator": supervisor.max_tokens_collaborator,
            "audio_orchestration_max_tokens": supervisor.audio_orchestration_max_tokens,
            "audio_orchestration_max_tokens_collaborator": supervisor.audio_orchestration_max_tokens_collaborator,
            "exclude_tools_from_audio_orchestration": supervisor.exclude_tools_from_audio_orchestration,
            "exclude_tools_from_text_orchestration": supervisor.exclude_tools_from_text_orchestration,
            "transcription_prompt": supervisor.transcription_prompt,
        }

    def get_supervisor_config(
        self,
        fetch_func: Optional[Callable[[], Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get OpenAI Supervisor configuration from cache or fetch and cache.

        Args:
            fetch_func: Optional function to fetch supervisor from DB.
                        If not provided, will fetch from DB directly.

        Returns:
            Dictionary with supervisor configuration, or None if not found.
        """
        # Try to get from cache first
        cached = self.cache_repository.get(self.CACHE_KEY)
        if cached:
            logger.debug("OpenAI Supervisor config loaded from cache")
            return cached

        # Cache miss - fetch from DB
        if fetch_func:
            supervisor = fetch_func()
        else:
            from nexus.inline_agents.backends.openai.models import OpenAISupervisor

            supervisor = OpenAISupervisor.objects.order_by("id").last()

        if not supervisor:
            logger.warning("No OpenAI Supervisor found in database")
            return None

        # Convert to dict and cache
        supervisor_dict = self._supervisor_to_dict(supervisor)
        self.cache_repository.set(self.CACHE_KEY, supervisor_dict, self.SUPERVISOR_TTL)
        logger.info(f"OpenAI Supervisor config cached (ID: {supervisor.id})")

        return supervisor_dict

    def invalidate_cache(self, refresh: bool = True) -> None:
        """
        Invalidate the OpenAI Supervisor cache.

        Args:
            refresh: If True, immediately refresh the cache with fresh data.
        """
        # Delete existing cache
        self.cache_repository.delete(self.CACHE_KEY)
        logger.info("OpenAI Supervisor cache invalidated")

        # Optionally refresh the cache
        if refresh:
            self.get_supervisor_config()

    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about the current cache state.

        Returns:
            Dictionary with cache information.
        """
        cached = self.cache_repository.get(self.CACHE_KEY)

        info = {
            "is_cached": cached is not None,
            "cache_key": self.CACHE_KEY,
            "ttl_seconds": self.SUPERVISOR_TTL,
        }

        if cached:
            info["supervisor_id"] = cached.get("id")
            info["supervisor_name"] = cached.get("name")
            info["action_groups_count"] = len(cached.get("action_groups") or [])
            info["human_support_action_groups_count"] = len(cached.get("human_support_action_groups") or [])

            # Get TTL from Redis
            try:
                ttl = self.cache_repository.redis_client.ttl(self.CACHE_KEY)
                if ttl > 0:
                    info["ttl_remaining_seconds"] = ttl
                    info["ttl_remaining_hours"] = round(ttl / 3600, 2)
            except Exception:
                pass

        return info
