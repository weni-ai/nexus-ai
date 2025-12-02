"""
Cache invalidation observers using the observer pattern.

These observers automatically refresh cache when data is updated, ensuring
the next user gets fresh cached data immediately instead of cache miss.

Uses async observers to avoid blocking update operations.

IMPORT STRATEGY:
----------------
We use lazy imports (inside perform methods) for dependencies that may have
circular import risks with the event system. This includes:
- Services/usecases that might import nexus.events
- Repositories that depend on models/usecases
- Any module in the dependency chain that could import event system

Safe top-level imports (no circular risk):
- nexus.event_domain.* (event system core, no external dependencies)
- Standard library modules

This pattern ensures scalability: as the codebase grows and dependencies
change, we avoid circular import issues without needing to refactor observers.
"""
import logging

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver

logger = logging.getLogger(__name__)


@observer("project_activity", isolate_errors=True, manager="async")
class ProjectCacheInvalidationObserver(EventObserver):
    """Invalidates and refreshes project cache when project is updated."""

    async def perform(self, **kwargs):
        """Refresh project cache when project is updated."""
        project = kwargs.get("project")
        action_type = kwargs.get("action_type")

        if not project or action_type != "U":  # Only on updates
            return

        try:
            # Lazy imports to avoid circular dependencies
            # (usecases/repositories may import nexus.events, which imports this module)
            from nexus.inline_agents.team.repository import ORMTeamRepository
            from nexus.usecases.guardrails.guardrails_usecase import GuardrailsUsecase
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
            from router.services.cache_service import CacheService

            cache_service = CacheService()
            project_uuid = str(project.uuid)

            # Get fresh data and refresh cache
            project_obj, content_base_obj, inline_agent_config = get_project_and_content_base_data(project_uuid)
            agents_backend = project_obj.agents_backend
            team = ORMTeamRepository(agents_backend=agents_backend, project=project_obj).get_team(project_uuid)

            # Helper functions to convert to dict
            def _project_to_dict(proj):
                return {
                    "uuid": str(proj.uuid),
                    "agents_backend": proj.agents_backend,
                    "use_components": proj.use_components,
                    "rationale_switch": proj.rationale_switch,
                    "use_prompt_creation_configurations": proj.use_prompt_creation_configurations,
                    "conversation_turns_to_include": proj.conversation_turns_to_include,
                    "exclude_previous_thinking_steps": proj.exclude_previous_thinking_steps,
                    "default_supervisor_foundation_model": proj.default_supervisor_foundation_model,
                    "human_support": proj.human_support,
                    "human_support_prompt": proj.human_support_prompt,
                }

            def _content_base_to_dict(cb):
                return {
                    "uuid": str(cb.uuid),
                    "title": cb.title,
                    "intelligence_uuid": str(cb.intelligence.uuid),
                }

            def _get_inline_agent_config(config):
                if config:
                    return {
                        "agents_backend": config.agents_backend,
                        "configuration": config.configuration,
                    }
                return None

            # Refresh all caches with fresh data
            cache_service.invalidate_project_cache(
                project_uuid=project_uuid,
                agents_backend=agents_backend,
                fetch_funcs={
                    "project": lambda uuid: _project_to_dict(project_obj),
                    "content_base": lambda uuid: _content_base_to_dict(content_base_obj),
                    "team": lambda uuid, backend: team,
                    "guardrails": lambda uuid: GuardrailsUsecase.get_guardrail_as_dict(uuid),
                    "inline_agent_config": lambda uuid: _get_inline_agent_config(inline_agent_config),
                },
            )

            logger.info(f"Refreshed project cache for {project_uuid}")
        except Exception as e:
            logger.error(f"Failed to refresh project cache for {project_uuid}: {e}", exc_info=True)
            # Error is isolated, won't break the update operation


@observer("contentbase_activity", isolate_errors=True, manager="async")
class ContentBaseCacheInvalidationObserver(EventObserver):
    """Invalidates and refreshes content base cache when content base is updated."""

    async def perform(self, **kwargs):
        """Refresh content base cache when content base is updated."""
        contentbase = kwargs.get("contentbase")
        action_type = kwargs.get("action_type")

        if not contentbase or action_type != "U":  # Only on updates
            return

        try:
            # Lazy imports to avoid circular dependencies
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
            from router.services.cache_service import CacheService

            cache_service = CacheService()

            # Get project_uuid from content base
            try:
                project_uuid = str(contentbase.intelligence.project.uuid)
            except AttributeError:
                # Content base might not have project (org-level)
                logger.debug(f"Content base {contentbase.uuid} has no project, skipping cache invalidation")
                return

            # Get fresh data
            project_obj, content_base_obj, _ = get_project_and_content_base_data(project_uuid)
            agents_backend = project_obj.agents_backend

            def _content_base_to_dict(cb):
                return {
                    "uuid": str(cb.uuid),
                    "title": cb.title,
                    "intelligence_uuid": str(cb.intelligence.uuid),
                }

            # Refresh content base cache
            cache_service.invalidate_content_base_cache(
                project_uuid=project_uuid,
                fetch_func=lambda uuid: _content_base_to_dict(content_base_obj),
                agents_backend=agents_backend,
            )

            logger.info(f"Refreshed content base cache for {project_uuid}")
        except Exception as e:
            logger.error(f"Failed to refresh content base cache: {e}", exc_info=True)


@observer("contentbase_agent_activity", isolate_errors=True, manager="async")
class ContentBaseAgentCacheInvalidationObserver(EventObserver):
    """Invalidates and refreshes content base cache when agent is updated."""

    async def perform(self, **kwargs):
        """Refresh content base cache when agent is updated."""
        content_base_agent = kwargs.get("content_base_agent")

        if not content_base_agent:
            return

        try:
            # Lazy imports to avoid circular dependencies
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
            from router.services.cache_service import CacheService

            cache_service = CacheService()

            # Get project_uuid from content base
            content_base = content_base_agent.content_base
            try:
                project_uuid = str(content_base.intelligence.project.uuid)
            except AttributeError:
                logger.debug(f"Content base {content_base.uuid} has no project, skipping cache invalidation")
                return

            # Get fresh data
            project_obj, content_base_obj, _ = get_project_and_content_base_data(project_uuid)
            agents_backend = project_obj.agents_backend

            def _content_base_to_dict(cb):
                return {
                    "uuid": str(cb.uuid),
                    "title": cb.title,
                    "intelligence_uuid": str(cb.intelligence.uuid),
                }

            # Refresh content base cache (agent is part of content base)
            cache_service.invalidate_content_base_cache(
                project_uuid=project_uuid,
                fetch_func=lambda uuid: _content_base_to_dict(content_base_obj),
                agents_backend=agents_backend,
            )

            logger.info(f"Refreshed content base cache (agent update) for {project_uuid}")
        except Exception as e:
            logger.error(f"Failed to refresh content base cache (agent update): {e}", exc_info=True)


@observer("contentbase_instruction_activity", isolate_errors=True, manager="async")
class ContentBaseInstructionCacheInvalidationObserver(EventObserver):
    """Invalidates and refreshes content base cache when instructions are updated."""

    async def perform(self, **kwargs):
        """Refresh content base cache when instructions are updated."""
        content_base_instruction = kwargs.get("content_base_instruction")

        if not content_base_instruction:
            return

        try:
            # Lazy imports to avoid circular dependencies
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
            from router.services.cache_service import CacheService

            cache_service = CacheService()

            # Get project_uuid from content base
            content_base = content_base_instruction.content_base
            try:
                project_uuid = str(content_base.intelligence.project.uuid)
            except AttributeError:
                logger.debug(f"Content base {content_base.uuid} has no project, skipping cache invalidation")
                return

            # Get fresh data
            project_obj, content_base_obj, _ = get_project_and_content_base_data(project_uuid)
            agents_backend = project_obj.agents_backend

            def _content_base_to_dict(cb):
                return {
                    "uuid": str(cb.uuid),
                    "title": cb.title,
                    "intelligence_uuid": str(cb.intelligence.uuid),
                }

            # Refresh content base cache (instructions are part of content base)
            cache_service.invalidate_content_base_cache(
                project_uuid=project_uuid,
                fetch_func=lambda uuid: _content_base_to_dict(content_base_obj),
                agents_backend=agents_backend,
            )

            logger.info(f"Refreshed content base cache (instruction update) for {project_uuid}")
        except Exception as e:
            logger.error(f"Failed to refresh content base cache (instruction update): {e}", exc_info=True)


@observer("contentbase_activity", isolate_errors=True, manager="async")
class TeamCacheInvalidationObserver(EventObserver):
    """
    Invalidates and refreshes team cache when content base is updated.

    Note: This handles team updates that happen through ContentBasePersonalizationSerializer.
    For direct team updates via PushAgents API, we need to either:
    1. Fire an event from PushAgents, OR
    2. Add cache invalidation directly in PushAgents.post()
    """

    async def perform(self, **kwargs):
        """Refresh team cache when content base (which includes team) is updated."""
        contentbase = kwargs.get("contentbase")
        action_type = kwargs.get("action_type")

        if not contentbase or action_type != "U":  # Only on updates
            return

        try:
            # Lazy imports to avoid circular dependencies
            from nexus.inline_agents.team.repository import ORMTeamRepository
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
            from router.services.cache_service import CacheService

            cache_service = CacheService()

            # Get project_uuid from content base
            try:
                project_uuid = str(contentbase.intelligence.project.uuid)
            except AttributeError:
                logger.debug(f"Content base {contentbase.uuid} has no project, skipping team cache invalidation")
                return

            # Get fresh data
            project_obj, content_base_obj, _ = get_project_and_content_base_data(project_uuid)
            agents_backend = project_obj.agents_backend
            team = ORMTeamRepository(agents_backend=agents_backend, project=project_obj).get_team(project_uuid)

            # Refresh team cache
            cache_service.invalidate_team_cache(
                project_uuid=project_uuid,
                agents_backend=agents_backend,
                fetch_func=lambda uuid, backend: team,
            )

            logger.info(f"Refreshed team cache for {project_uuid}")
        except Exception as e:
            logger.error(f"Failed to refresh team cache: {e}", exc_info=True)


# Note: For direct team updates via PushAgents API (nexus/inline_agents/api/views.py),
# we need to add cache invalidation directly in PushAgents.post() method since
# it doesn't currently fire an event. Alternatively, we could add an event there.
#
# For guardrails updates, we would need to:
# 1. Fire an event when guardrails are updated, OR
# 2. Add cache invalidation directly in the guardrails update handler
