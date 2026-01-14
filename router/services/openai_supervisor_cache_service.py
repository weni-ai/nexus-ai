import logging
from typing import Any, Callable, Dict, Optional

from nexus.inline_agents.backends.openai.models import SupervisorAgent
from router.repositories import Repository

logger = logging.getLogger(__name__)


class SupervisorAgentCacheService:
    SUPERVISOR_TTL = 86400  # 24 hours

    CACHE_KEY = "supervisor_agent:config"

    def __init__(
        self, project_uuid: str, supervisor_uuid: Optional[str] = None, cache_repository: Optional[Repository] = None
    ):
        if cache_repository is None:
            from router.repositories.redis.cache import CacheRepository

            cache_repository = CacheRepository()

        self.cache_repository = cache_repository
        self.project_uuid = project_uuid
        self.cache_key = self.get_cache_key(project_uuid, supervisor_uuid)

    def get_cache_key(self, project_uuid: str, supervisor_uuid: Optional[str] = None) -> str:
        if supervisor_uuid:
            return f"{self.CACHE_KEY}:{project_uuid}"
        return f"{self.CACHE_KEY}:default"

    def _supervisor_to_dict(self, supervisor: SupervisorAgent) -> Dict[str, Any]:
        supervisor_dict = supervisor.__dict__
        supervisor_dict.pop("_state")
        return supervisor_dict

    def get_supervisor_config(
        self,
        project_uuid: str,
        fetch_func: Callable[[str], Any],
    ) -> Optional[Dict[str, Any]]:
        # temporary disable cache
        cached = False
        # cached = self.cache_repository.get(self.cache_key)

        if cached:
            logger.debug("OpenAI Supervisor config loaded from cache")
            return cached

        supervisor = fetch_func(project_uuid)

        if not supervisor:
            logger.warning("No OpenAI Supervisor found in database")
            raise SupervisorAgent.DoesNotExist()

        supervisor_dict = self._supervisor_to_dict(supervisor)
        # self.cache_repository.set(self.cache_key, supervisor_dict, self.SUPERVISOR_TTL)
        logger.info(f"OpenAI Supervisor config cached (ID: {supervisor.id})")

        return supervisor_dict

    def invalidate_cache(self) -> None:
        self.cache_repository.delete(self.cache_key)
        logger.info("OpenAI Supervisor cache invalidated")

    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about the current cache state.

        Returns:
            Dictionary with cache information.
        """
        cached = self.cache_repository.get(self.cache_key)

        info = {
            "is_cached": cached is not None,
            "cache_key": self.cache_key,
            "ttl_seconds": self.SUPERVISOR_TTL,
        }

        if cached:
            info["supervisor_id"] = cached.get("id")
            info["supervisor_name"] = cached.get("name")
            info["action_groups_count"] = len(cached.get("action_groups") or [])
            info["human_support_action_groups_count"] = len(cached.get("human_support_action_groups") or [])

            # Get TTL from Redis
            try:
                ttl = self.cache_repository.redis_client.ttl(self.cache_key)
                if ttl > 0:
                    info["ttl_remaining_seconds"] = ttl
                    info["ttl_remaining_hours"] = round(ttl / 3600, 2)
            except Exception:
                pass

        return info
