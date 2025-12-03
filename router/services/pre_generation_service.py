"""
Pre-Generation service for fetching and caching project data.

This service handles the cache-aware fetching of all data needed for
inline agent processing. It uses CacheService to minimize database queries.

Currently called directly from start_inline_agents, but designed to be
easily refactored into a separate Celery task when workflow orchestrator
is implemented.
"""
import logging
from typing import Dict, List, Optional, Tuple

from router.services.cache_service import CacheService

logger = logging.getLogger(__name__)


class PreGenerationService:
    """Service for pre-generation data fetching with caching."""

    def __init__(self, cache_service: Optional[CacheService] = None):
        """Initialize with optional cache service (for testing)."""
        self.cache_service = cache_service or CacheService()

    def _project_to_dict(self, project) -> Dict:
        """Convert Project model to dictionary for caching."""
        return {
            "uuid": str(project.uuid),
            "agents_backend": project.agents_backend,
            "use_components": project.use_components,
            "rationale_switch": project.rationale_switch,
            "use_prompt_creation_configurations": project.use_prompt_creation_configurations,
            "conversation_turns_to_include": project.conversation_turns_to_include,
            "exclude_previous_thinking_steps": project.exclude_previous_thinking_steps,
            "default_supervisor_foundation_model": project.default_supervisor_foundation_model,
            "human_support": project.human_support,
            "human_support_prompt": project.human_support_prompt,
        }

    def _content_base_to_dict(self, content_base) -> Dict:
        """Convert ContentBase model to dictionary for caching."""
        return {
            "uuid": str(content_base.uuid),
            "title": content_base.title,
            "intelligence_uuid": str(content_base.intelligence.uuid),
        }

    def _get_inline_agent_config(self, config) -> Optional[Dict]:
        """Convert InlineAgentsConfiguration to dictionary for caching."""
        if config:
            return {
                "agents_backend": config.agents_backend,
                "configuration": config.configuration,
            }
        return None

    def fetch_pre_generation_data(
        self, project_uuid: str
    ) -> Tuple[Dict, Dict, List[Dict], Dict, Optional[Dict], str]:
        """
        Fetch all pre-generation data using cache-first strategy.

        This method uses CacheService to minimize database queries by:
        1. Checking cache first for each data type
        2. Fetching from database only if cache miss
        3. Caching the result for future requests

        Also tracks performance metrics automatically via observers.

        Args:
            project_uuid: UUID of the project

        Returns:
            Tuple of:
            - project_dict: Project data as dictionary
            - content_base_dict: Content base data as dictionary
            - team: Team/agents data as list of dictionaries
            - guardrails_config: Guardrails configuration as dictionary
            - inline_agent_config: Inline agent configuration (optional)
            - agents_backend: Agents backend string

        Raises:
            Exception: If data cannot be fetched
        """
        import time

        start_time = time.time()
        status = "success"
        error = None

        try:
            # Lazy imports to avoid circular dependencies
            from nexus.inline_agents.team.repository import ORMTeamRepository
            from nexus.usecases.guardrails.guardrails_usecase import GuardrailsUsecase
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data

            # Fetch project and content base data
            # Note: This fetches Django model objects, which we convert to dicts for caching
            # The objects are needed for some operations, but the dicts are cached for future use
            project_obj, content_base_obj, inline_agent_config_obj = get_project_and_content_base_data(project_uuid)

            # Convert to dict and cache using CacheService
            project_dict = self.cache_service.get_project_data(
                project_uuid,
                fetch_func=lambda uuid: self._project_to_dict(project_obj),
            )

            content_base_dict = self.cache_service.get_content_base_data(
                project_uuid,
                fetch_func=lambda uuid: self._content_base_to_dict(content_base_obj),
            )

            # Get agents_backend from project
            agents_backend = project_dict.get("agents_backend") or project_obj.agents_backend

            # Fetch team data using cache
            team = self.cache_service.get_team_data(
                project_uuid,
                agents_backend,
                fetch_func=lambda uuid, backend: ORMTeamRepository(
                    agents_backend=backend, project=project_obj
                ).get_team(uuid),
            )

            # Fetch guardrails config using cache
            guardrails_config = self.cache_service.get_guardrails_config(
                project_uuid,
                fetch_func=lambda uuid: GuardrailsUsecase.get_guardrail_as_dict(uuid),
            )

            # Fetch inline agent config using cache (if available)
            inline_agent_config = None
            if inline_agent_config_obj:
                inline_agent_config = self.cache_service.get_inline_agent_config(
                    project_uuid,
                    fetch_func=lambda uuid: self._get_inline_agent_config(inline_agent_config_obj),
                )

            logger.debug(
                f"Pre-generation data fetched for project {project_uuid}",
                extra={
                    "project_uuid": project_uuid,
                    "agents_backend": agents_backend,
                    "has_team": bool(team),
                    "has_guardrails": bool(guardrails_config),
                    "has_inline_config": bool(inline_agent_config),
                },
            )

            return (
                project_dict,
                content_base_dict,
                team,
                guardrails_config,
                inline_agent_config,
                agents_backend,
            )

        except Exception as e:
            status = "failed"
            error = str(e)
            raise
        finally:
            # Track performance with Sentry (actual stage duration)
            duration = time.time() - start_time
            try:
                import sentry_sdk

                # Create Sentry transaction for the actual pre-generation stage
                with sentry_sdk.start_transaction(
                    name="pre_generation.fetch_data",
                    op="pre_generation",
                    sampled=True,  # Always sample stage performance
                ) as transaction:
                    transaction.set_tag("stage", "pre_generation")
                    transaction.set_tag("project_uuid", project_uuid)
                    transaction.set_measurement("duration", duration, unit="second")
                    transaction.set_status("ok" if status == "success" else "internal_error")
                    if error:
                        transaction.set_data("error", error)

                # Log performance metrics
                if status == "success":
                    logger.info(
                        f"Pre-Generation completed: {status} in {duration:.3f}s",
                        extra={
                            "stage": "pre_generation",
                            "project_uuid": project_uuid,
                            "duration_seconds": duration,
                            "status": status,
                        },
                    )
                else:
                    logger.error(
                        f"Pre-Generation failed: {status} in {duration:.3f}s",
                        extra={
                            "stage": "pre_generation",
                            "project_uuid": project_uuid,
                            "duration_seconds": duration,
                            "status": status,
                            "error": error,
                        },
                    )

                # Warn on slow pre-generation
                if duration > 5.0:
                    logger.warning(
                        f"Slow Pre-Generation: {duration:.3f}s for project {project_uuid}",
                        extra={
                            "stage": "pre_generation",
                            "project_uuid": project_uuid,
                            "duration_seconds": duration,
                            "slow": True,
                        },
                    )
            except Exception as tracking_error:
                # Don't let performance tracking break the main flow
                logger.warning(f"Failed to track pre-generation performance: {tracking_error}", exc_info=True)

    def get_project_objects(
        self, project_uuid: str
    ) -> Tuple[object, object, Optional[object]]:
        """
        Get actual Django model objects (for backward compatibility).

        This method fetches the actual objects, which may be needed
        for some parts of the code that haven't been refactored yet.

        Note: This will fetch from database again. In the future, when we refactor
        to use dicts everywhere, this method can be removed.

        Args:
            project_uuid: UUID of the project

        Returns:
            Tuple of (project, content_base, inline_agent_config)
        """
        from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data

        # TODO: When backend.invoke_agents is refactored to accept dicts,
        # we can remove this method and use the cached dicts directly
        return get_project_and_content_base_data(project_uuid)
