from typing import Any, Callable, Dict, List, Optional

from router.repositories import Repository


class CacheService:
    """Service for caching configuration data with TTL management and hybrid caching strategy."""

    # TTL constants - Long TTLs since config rarely changes
    PROJECT_DATA_TTL = 86400  # 24 hours
    CONTENT_BASE_TTL = 86400  # 24 hours
    TEAM_DATA_TTL = 86400  # 24 hours
    INLINE_AGENT_CONFIG_TTL = 86400  # 24 hours
    GUARDRAILS_TTL = 86400  # 24 hours
    INSTRUCTIONS_TTL = 86400  # 24 hours
    AGENT_DATA_TTL = 86400  # 24 hours
    WORKFLOW_CACHE_TTL = 600  # 10 minutes

    # Cache type configuration - makes it easy to add new cache types
    CACHE_TYPES = {
        "data": {"ttl": PROJECT_DATA_TTL, "key_suffix": "data"},
        "content_base": {"ttl": CONTENT_BASE_TTL, "key_suffix": "content_base"},
        "team": {"ttl": TEAM_DATA_TTL, "key_suffix": "team", "requires_backend": True},
        "guardrails": {"ttl": GUARDRAILS_TTL, "key_suffix": "guardrails"},
        "inline_agent_config": {"ttl": INLINE_AGENT_CONFIG_TTL, "key_suffix": "inline_agent_config"},
        "instructions": {"ttl": INSTRUCTIONS_TTL, "key_suffix": "instructions"},
        "agent": {"ttl": AGENT_DATA_TTL, "key_suffix": "agent"},
    }

    # Required cache types for composite cache
    REQUIRED_FOR_COMPOSITE = ["data", "content_base", "team", "guardrails"]
    OPTIONAL_FOR_COMPOSITE = ["inline_agent_config"]

    def __init__(self, cache_repository: Optional[Repository] = None):
        if cache_repository is None:
            from router.repositories.redis.cache import CacheRepository

            cache_repository = CacheRepository()
        self.cache_repository = cache_repository

    def _get_cache_key(self, project_uuid: str, cache_type: str, agents_backend: Optional[str] = None) -> str:
        """Generate cache key for a project cache type."""
        suffix = self.CACHE_TYPES[cache_type]["key_suffix"]
        if agents_backend and self.CACHE_TYPES[cache_type].get("requires_backend"):
            return f"project:{project_uuid}:{suffix}:{agents_backend}"
        return f"project:{project_uuid}:{suffix}"

    def _get_or_create(
        self,
        cache_key: str,
        fetch_func: Callable,
        ttl: int,
        *fetch_args,
    ) -> Any:
        """Generic get_or_create pattern for caching."""
        cached = self.cache_repository.get(cache_key)
        if cached:
            return cached

        data = fetch_func(*fetch_args)
        self.cache_repository.set(cache_key, data, ttl)
        return data

    def get_all_project_data(
        self,
        project_uuid: str,
        agents_backend: Optional[str],
        fetch_funcs: Dict[str, Callable],
    ) -> Dict:
        """Get all project data in one cache operation (composite key)."""
        composite_key = f"project:{project_uuid}:all"
        cached = self.cache_repository.get(composite_key)
        if cached:
            return cached

        # Cache miss - fetch all data
        # Support both "project" and "data" keys for backward compatibility
        project_key = "project" if "project" in fetch_funcs else "data"
        project_data = fetch_funcs[project_key](project_uuid)

        if agents_backend is None:
            agents_backend = project_data.get("agents_backend")
            if not agents_backend:
                raise ValueError(f"agents_backend not provided and not found in project data for {project_uuid}")

        # Fetch all required data
        all_data = {
            "data": project_data,
            "project": project_data,  # Backward compatibility
            "content_base": fetch_funcs["content_base"](project_uuid),
            "team": fetch_funcs["team"](project_uuid, agents_backend),
            "guardrails": fetch_funcs["guardrails"](project_uuid),
        }

        # Add optional data
        if "inline_agent_config" in fetch_funcs:
            all_data["inline_agent_config"] = fetch_funcs["inline_agent_config"](project_uuid)

        # Cache composite
        self.cache_repository.set(composite_key, all_data, self.PROJECT_DATA_TTL)

        # Cache individually
        for cache_type in self.CACHE_TYPES:
            if cache_type in all_data:
                key = self._get_cache_key(project_uuid, cache_type, agents_backend)
                ttl = self.CACHE_TYPES[cache_type]["ttl"]
                self.cache_repository.set(key, all_data[cache_type], ttl)

        return all_data

    def get_project_data(self, project_uuid: str, fetch_func: Callable[[str], Dict]) -> Dict:
        """Get project data from cache or fetch and cache."""
        cache_key = self._get_cache_key(project_uuid, "data")
        return self._get_or_create(cache_key, fetch_func, self.PROJECT_DATA_TTL, project_uuid)

    def get_content_base_data(self, project_uuid: str, fetch_func: Callable[[str], Dict]) -> Dict:
        """Get content base data from cache or fetch and cache."""
        cache_key = self._get_cache_key(project_uuid, "content_base")
        return self._get_or_create(cache_key, fetch_func, self.CONTENT_BASE_TTL, project_uuid)

    def get_team_data(
        self,
        project_uuid: str,
        agents_backend: str,
        fetch_func: Callable[[str, str], List[Dict]],
    ) -> List[Dict]:
        """Get team data from cache or fetch and cache."""
        cache_key = self._get_cache_key(project_uuid, "team", agents_backend)
        return self._get_or_create(cache_key, fetch_func, self.TEAM_DATA_TTL, project_uuid, agents_backend)

    def get_guardrails_config(self, project_uuid: str, fetch_func: Callable[[str], Dict]) -> Dict:
        """Get guardrails configuration from cache or fetch and cache."""
        cache_key = self._get_cache_key(project_uuid, "guardrails")
        return self._get_or_create(cache_key, fetch_func, self.GUARDRAILS_TTL, project_uuid)

    def get_inline_agent_config(self, project_uuid: str, fetch_func: Callable[[str], Dict]) -> Optional[Dict]:
        """Get inline agent configuration from cache or fetch and cache."""
        cache_key = self._get_cache_key(project_uuid, "inline_agent_config")
        cached = self.cache_repository.get(cache_key)
        if cached:
            return cached

        data = fetch_func(project_uuid)
        if data:
            self.cache_repository.set(cache_key, data, self.INLINE_AGENT_CONFIG_TTL)
        return data

    def get_instructions_data(self, project_uuid: str, fetch_func: Callable[[str], List[str]]) -> List[str]:
        """Get content base instructions from cache or fetch and cache."""
        cache_key = self._get_cache_key(project_uuid, "instructions")
        return self._get_or_create(cache_key, fetch_func, self.INSTRUCTIONS_TTL, project_uuid)

    def get_agent_data(self, project_uuid: str, fetch_func: Callable[[str], Optional[Dict]]) -> Optional[Dict]:
        """Get content base agent data from cache or fetch and cache."""
        cache_key = self._get_cache_key(project_uuid, "agent")
        cached = self.cache_repository.get(cache_key)
        if cached:
            return cached

        data = fetch_func(project_uuid)
        if data:
            self.cache_repository.set(cache_key, data, self.AGENT_DATA_TTL)
        return data

    def cache_workflow_data(self, workflow_id: str, data_type: str, data: Any, ttl: Optional[int] = None) -> None:
        """Cache data for a specific workflow."""
        cache_key = f"workflow:{workflow_id}:{data_type}"
        self.cache_repository.set(cache_key, data, ttl or self.WORKFLOW_CACHE_TTL)

    def get_workflow_data(self, workflow_id: str, data_type: str) -> Optional[Any]:
        """Get cached data for a workflow."""
        return self.cache_repository.get(f"workflow:{workflow_id}:{data_type}")

    def clear_workflow_cache(self, workflow_id: str) -> None:
        """Clear all cached data for a workflow."""
        self.cache_repository.delete_pattern(f"workflow:{workflow_id}:*")

    def _refresh_composite_cache_from_individual(self, project_uuid: str, agents_backend: str) -> Optional[Dict]:
        """Refresh composite cache from existing individual caches if available."""
        all_data = {}

        # Get all required cache types
        for cache_type in self.REQUIRED_FOR_COMPOSITE:
            key = self._get_cache_key(project_uuid, cache_type, agents_backend)
            data = self.cache_repository.get(key)
            if data is None:
                return None
            all_data[cache_type] = data

        # Get optional cache types
        for cache_type in self.OPTIONAL_FOR_COMPOSITE:
            key = self._get_cache_key(project_uuid, cache_type, agents_backend)
            data = self.cache_repository.get(key)
            if data:
                all_data[cache_type] = data

        # Add backward compatibility key
        if "data" in all_data:
            all_data["project"] = all_data["data"]

        # Update composite cache with fresh TTL
        composite_key = f"project:{project_uuid}:all"
        self.cache_repository.set(composite_key, all_data, self.PROJECT_DATA_TTL)
        return all_data

    def _invalidate_cache_type(
        self,
        project_uuid: str,
        cache_type: str,
        fetch_func: Optional[Callable] = None,
        agents_backend: Optional[str] = None,
    ) -> None:
        """Generic invalidation method for a specific cache type."""
        # Map cache types to their get methods
        get_methods = {
            "data": lambda: self.get_project_data(project_uuid, fetch_func),
            "content_base": lambda: self.get_content_base_data(project_uuid, fetch_func),
            "team": lambda: self.get_team_data(project_uuid, agents_backend, fetch_func) if agents_backend else None,
            "guardrails": lambda: self.get_guardrails_config(project_uuid, fetch_func),
            "inline_agent_config": lambda: self.get_inline_agent_config(project_uuid, fetch_func),
            "instructions": lambda: self.get_instructions_data(project_uuid, fetch_func),
            "agent": lambda: self.get_agent_data(project_uuid, fetch_func),
        }

        if fetch_func:
            # Refresh individual cache
            if cache_type in get_methods:
                get_methods[cache_type]()

            # Try to rebuild composite cache
            if agents_backend:
                self._refresh_composite_cache_from_individual(project_uuid, agents_backend)
        else:
            # Delete individual key
            key = self._get_cache_key(project_uuid, cache_type, agents_backend)
            self.cache_repository.delete(key)

            # Try to rebuild composite or delete it
            if agents_backend:
                if not self._refresh_composite_cache_from_individual(project_uuid, agents_backend):
                    self.cache_repository.delete(f"project:{project_uuid}:all")
            else:
                self.cache_repository.delete(f"project:{project_uuid}:all")

    def invalidate_project_cache(
        self,
        project_uuid: str,
        fetch_funcs: Optional[Dict[str, Callable]] = None,
        agents_backend: Optional[str] = None,
    ) -> None:
        """Invalidate and refresh all project-level caches."""
        if fetch_funcs and agents_backend:
            self.get_all_project_data(project_uuid, agents_backend, fetch_funcs)
        else:
            self.cache_repository.delete(f"project:{project_uuid}:all")
            self.cache_repository.delete_pattern(f"project:{project_uuid}:*")

    def invalidate_content_base_cache(
        self,
        project_uuid: str,
        fetch_func: Optional[Callable[[str], Dict]] = None,
        agents_backend: Optional[str] = None,
    ) -> None:
        """Invalidate and refresh content base cache."""
        self._invalidate_cache_type(project_uuid, "content_base", fetch_func, agents_backend)

    def invalidate_instructions_cache(
        self,
        project_uuid: str,
        fetch_func: Optional[Callable[[str], List[str]]] = None,
        agents_backend: Optional[str] = None,
    ) -> None:
        """Invalidate and refresh instructions cache."""
        self._invalidate_cache_type(project_uuid, "instructions", fetch_func, agents_backend)

    def invalidate_agent_cache(
        self,
        project_uuid: str,
        fetch_func: Optional[Callable[[str], Optional[Dict]]] = None,
        agents_backend: Optional[str] = None,
    ) -> None:
        """Invalidate and refresh agent cache."""
        self._invalidate_cache_type(project_uuid, "agent", fetch_func, agents_backend)

    def invalidate_team_cache(
        self,
        project_uuid: str,
        agents_backend: Optional[str] = None,
        fetch_func: Optional[Callable[[str, str], List[Dict]]] = None,
    ) -> None:
        """Invalidate and refresh team cache."""
        if not agents_backend and not fetch_func:
            # Delete all team caches for this project
            self.cache_repository.delete_pattern(f"project:{project_uuid}:team:*")
            self.cache_repository.delete(f"project:{project_uuid}:all")
        else:
            self._invalidate_cache_type(project_uuid, "team", fetch_func, agents_backend)

    def invalidate_guardrails_cache(
        self,
        project_uuid: str,
        fetch_func: Optional[Callable[[str], Dict]] = None,
        agents_backend: Optional[str] = None,
    ) -> None:
        """Invalidate and refresh guardrails cache."""
        self._invalidate_cache_type(project_uuid, "guardrails", fetch_func, agents_backend)

    def invalidate_inline_agent_config_cache(
        self,
        project_uuid: str,
        fetch_func: Optional[Callable[[str], Dict]] = None,
        agents_backend: Optional[str] = None,
    ) -> None:
        """Invalidate and refresh inline agent configuration cache."""
        self._invalidate_cache_type(project_uuid, "inline_agent_config", fetch_func, agents_backend)
