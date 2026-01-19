import logging
from typing import Dict, List, Optional, Tuple

from router.services.cache_service import CacheService

logger = logging.getLogger(__name__)


class PreGenerationService:
    def __init__(self, cache_service: Optional[CacheService] = None):
        self.cache_service = cache_service or CacheService()
        self._project_obj = None
        self._content_base_obj = None
        self._inline_agent_config_obj = None

    def _project_to_dict(self, project) -> Dict:
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
            "default_formatter_foundation_model": project.default_formatter_foundation_model,
            "formatter_instructions": project.formatter_instructions,
            "formatter_reasoning_effort": project.formatter_reasoning_effort,
            "formatter_reasoning_summary": project.formatter_reasoning_summary,
            "formatter_send_only_assistant_message": project.formatter_send_only_assistant_message,
            "formatter_tools_descriptions": project.formatter_tools_descriptions,
            "supervisor_agent_uuid": project.manager_agent.uuid if project.manager_agent else None,
        }

    def _content_base_to_dict(self, content_base) -> Dict:
        return {
            "uuid": str(content_base.uuid),
            "title": content_base.title,
            "intelligence_uuid": str(content_base.intelligence.uuid),
        }

    def _instructions_to_list(self, content_base) -> List[str]:
        try:
            return list(content_base.instructions.all().values_list("instruction", flat=True))
        except Exception:
            return []

    def _agent_to_dict(self, content_base) -> Optional[Dict]:
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
            pass
        return None

    def _get_inline_agent_config(self, config) -> Optional[Dict]:
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
        import time

        start_time = time.time()
        status = "success"
        error = None

        try:
            from nexus.inline_agents.team.repository import ORMTeamRepository
            from nexus.usecases.guardrails.guardrails_usecase import GuardrailsUsecase
            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data

            project_obj, content_base_obj, inline_agent_config_obj = get_project_and_content_base_data(project_uuid)

            try:
                _ = content_base_obj.agent
            except Exception:
                pass

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
