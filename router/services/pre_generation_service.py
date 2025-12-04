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
        # Store Django objects to avoid duplicate queries
        self._project_obj = None
        self._content_base_obj = None
        self._inline_agent_config_obj = None

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
            # Formatter agent configurations (used by OpenAI backend)
            "default_formatter_foundation_model": project.default_formatter_foundation_model,
            "formatter_instructions": project.formatter_instructions,
            "formatter_reasoning_effort": project.formatter_reasoning_effort,
            "formatter_reasoning_summary": project.formatter_reasoning_summary,
            "formatter_send_only_assistant_message": project.formatter_send_only_assistant_message,
            "formatter_tools_descriptions": project.formatter_tools_descriptions,
        }

    def _content_base_to_dict(self, content_base) -> Dict:
        """Convert ContentBase model to dictionary for caching."""
        return {
            "uuid": str(content_base.uuid),
            "title": content_base.title,
            "intelligence_uuid": str(content_base.intelligence.uuid),
        }

    def _instructions_to_list(self, content_base) -> List[str]:
        """Extract instructions as list of instruction texts (used by backend)."""
        try:
            return list(content_base.instructions.all().values_list("instruction", flat=True))
        except Exception:
            return []  # If instructions don't exist or error, use empty list

    def _agent_to_dict(self, content_base) -> Optional[Dict]:
        """Extract agent data as dictionary (used by backend)."""
        try:
            agent = content_base.agent
            if agent:
                return {
                    "name": agent.name,
                    "role": agent.role,
                    "personality": agent.personality,
                    "goal": agent.goal,
                }
        except Exception:
            pass  # If agent doesn't exist or error, return None
        return None

    def _get_inline_agent_config(self, config) -> Optional[Dict]:
        """Convert InlineAgentsConfiguration to dictionary for caching."""
        if config:
            return {
                "agents_backend": config.agents_backend,
                "configuration": config.configuration,
                "default_instructions_for_collaborators": config.default_instructions_for_collaborators,
            }
        return None

    def fetch_pre_generation_data(
        self, project_uuid: str
    ) -> Tuple[Dict, Dict, List[Dict], Dict, Optional[Dict], str, List[str], Optional[Dict]]:
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
        transaction = None

        # Try to start Sentry transaction (non-blocking if Sentry is unavailable)
        try:
            import sentry_sdk

            transaction = sentry_sdk.start_transaction(
                name="pre_generation.fetch_data",
                op="pre_generation",
                sampled=True,  # Override global traces_sample_rate=0.0
            )
            if transaction:
                transaction.set_tag("stage", "pre_generation")
                transaction.set_tag("project_uuid", project_uuid)
        except Exception:
            logger.warning("Sentry not available, continuing without transaction tracking", exc_info=True)
            pass

        try:
            # Lazy imports to avoid circular dependencies
            from nexus.inline_agents.team.repository import ORMTeamRepository
            from nexus.usecases.guardrails.guardrails_usecase import GuardrailsUsecase
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data

            project_obj, content_base_obj, inline_agent_config_obj = get_project_and_content_base_data(project_uuid)

            try:
                _ = content_base_obj.agent
            except Exception:
                pass  # Agent might not exist, that's okay

            self._project_obj = project_obj
            self._content_base_obj = content_base_obj
            self._inline_agent_config_obj = inline_agent_config_obj

            project_dict = self.cache_service.get_project_data(
                project_uuid,
                fetch_func=lambda uuid: self._project_to_dict(project_obj),
            )

            content_base_dict = self.cache_service.get_content_base_data(
                project_uuid,
                fetch_func=lambda uuid: self._content_base_to_dict(content_base_obj),
            )

            instructions_list = self.cache_service.get_instructions_data(
                project_uuid,
                fetch_func=lambda uuid: self._instructions_to_list(content_base_obj),
            )

            agent_dict = self.cache_service.get_agent_data(
                project_uuid,
                fetch_func=lambda uuid: self._agent_to_dict(content_base_obj),
            )

            agents_backend = project_dict.get("agents_backend") or project_obj.agents_backend

            team = self.cache_service.get_team_data(
                project_uuid,
                agents_backend,
                fetch_func=lambda uuid, backend: ORMTeamRepository(
                    agents_backend=backend, project=project_obj
                ).get_team(uuid),
            )

            guardrails_config = self.cache_service.get_guardrails_config(
                project_uuid,
                fetch_func=lambda uuid: GuardrailsUsecase.get_guardrail_as_dict(uuid),
            )

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
                    "has_instructions": bool(instructions_list),
                    "has_agent": bool(agent_dict),
                },
            )

            return (
                project_dict,
                content_base_dict,
                team,
                guardrails_config,
                inline_agent_config,
                agents_backend,
                instructions_list,
                agent_dict,
            )

        except Exception as e:
            status = "failed"
            error = str(e)
            raise
        finally:
            duration = time.time() - start_time
            if transaction:
                try:
                    transaction.set_measurement("duration", duration, unit="second")
                    transaction.set_status("ok" if status == "success" else "internal_error")
                    if error:
                        transaction.set_data("error", error)
                    transaction.finish()
                except Exception as tracking_error:
                    logger.warning(f"Failed to finish Sentry transaction: {tracking_error}", exc_info=True)

            try:
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
            except Exception as logging_error:
                logger.warning(f"Failed to log pre-generation performance: {logging_error}", exc_info=True)

    def get_project_objects(
        self, project_uuid: str
    ) -> Tuple[object, object, Optional[object]]:
        """
        Get actual Django model objects (for backward compatibility).

        This method returns the objects that were already fetched in fetch_pre_generation_data(),
        avoiding duplicate database queries.

        Note: In the future, when backend.invoke_agents is refactored to accept dicts,
        this method can be removed.

        Args:
            project_uuid: UUID of the project (for validation, not used if objects already cached)

        Returns:
            Tuple of (project, content_base, inline_agent_config)
        """
        # Return cached objects from fetch_pre_generation_data() to avoid duplicate queries
        if self._project_obj and self._content_base_obj:
            return self._project_obj, self._content_base_obj, self._inline_agent_config_obj

        # Fallback: fetch if objects weren't cached (shouldn't happen in normal flow)
        from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
        project_obj, content_base_obj, inline_agent_config_obj = get_project_and_content_base_data(project_uuid)
        self._project_obj = project_obj
        self._content_base_obj = content_base_obj
        self._inline_agent_config_obj = inline_agent_config_obj
        return project_obj, content_base_obj, inline_agent_config_obj
