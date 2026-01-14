"""
Pre-Generation Celery Task

This task handles all pre-generation work:
- Fetching and caching project data via PreGenerationService
- Preparing CachedProjectData for generation phase

The task wraps PreGenerationService and returns serialized CachedProjectData.
"""

import logging
from typing import Dict, Optional

import sentry_sdk

from nexus.celery import app as celery_app
from router.services.pre_generation_service import PreGenerationService
from router.tasks.invocation_context import CachedProjectData
from router.tasks.redis_task_manager import RedisTaskManager

logger = logging.getLogger(__name__)


def get_task_manager() -> RedisTaskManager:
    """Get the default task manager instance."""
    return RedisTaskManager()


@celery_app.task(
    bind=True,
    name="router.tasks.pre_generation.pre_generation_task",
    soft_time_limit=60,
    time_limit=90,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=30,
)
def pre_generation_task(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    workflow_id: Optional[str] = None,
) -> Dict:
    """
    Pre-Generation Task - Fetches and prepares all data needed for generation.

    This task wraps the PreGenerationService and returns serialized data
    that can be passed to the generation phase.

    Args:
        message: The incoming message dict containing project_uuid, contact_urn, etc.
        preview: Whether this is a preview request
        language: Language code
        workflow_id: ID of the parent workflow (optional)

    Returns:
        Dict containing:
        - status: "success" | "failed"
        - cached_data: Serialized CachedProjectData (if success)
        - project_uuid: Project UUID
        - agents_backend: Backend type
        - workflow_id: Workflow ID (if provided)
        - error: Error message (if failed)
    """
    task_manager = get_task_manager()
    project_uuid = message.get("project_uuid")
    contact_urn = message.get("contact_urn")

    # Update workflow state if workflow_id provided
    if workflow_id and contact_urn:
        task_manager.update_workflow_status(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            status="pre_generation",
            task_phase="pre_generation",
            task_id=self.request.id,
        )

    try:
        # Set Sentry context
        sentry_sdk.set_tag("task_phase", "pre_generation")
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("workflow_id", workflow_id or "standalone")
        sentry_sdk.set_tag("task_id", self.request.id)

        logger.info(
            f"[PreGeneration] Starting for project {project_uuid}",
            extra={
                "project_uuid": project_uuid,
                "workflow_id": workflow_id,
                "task_id": self.request.id,
            },
        )

        # Fetch pre-generation data using service
        pre_gen_service = PreGenerationService()
        (
            project_dict,
            content_base_dict,
            team,
            guardrails_config,
            inline_agent_config,
            agents_backend,
            instructions,
            agent_data,
        ) = pre_gen_service.fetch_pre_generation_data(project_uuid)

        # Create CachedProjectData
        cached_data = CachedProjectData.from_pre_generation_data(
            project_dict=project_dict,
            content_base_dict=content_base_dict,
            team=team,
            guardrails_config=guardrails_config,
            inline_agent_config_dict=inline_agent_config,
            instructions=instructions,
            agent_data=agent_data,
        )

        # Serialize CachedProjectData for task result
        serialized_data = {
            "project_dict": cached_data.project_dict,
            "content_base_dict": cached_data.content_base_dict,
            "team": cached_data.team,
            "guardrails_config": cached_data.guardrails_config,
            "inline_agent_config_dict": cached_data.inline_agent_config_dict,
            "instructions": cached_data.instructions,
            "agent_data": cached_data.agent_data,
        }

        logger.info(
            f"[PreGeneration] Success for project {project_uuid}",
            extra={
                "project_uuid": project_uuid,
                "agents_backend": agents_backend,
                "workflow_id": workflow_id,
                "task_id": self.request.id,
                "has_team": bool(team),
                "has_guardrails": bool(guardrails_config),
            },
        )

        return {
            "status": "success",
            "cached_data": serialized_data,
            "project_uuid": project_uuid,
            "agents_backend": agents_backend,
            "workflow_id": workflow_id,
        }

    except Exception as e:
        logger.error(
            f"[PreGeneration] Failed for project {project_uuid}: {e}",
            extra={
                "project_uuid": project_uuid,
                "workflow_id": workflow_id,
                "task_id": self.request.id,
                "error": str(e),
            },
            exc_info=True,
        )
        sentry_sdk.capture_exception(e)

        # Update workflow state on failure if workflow_id provided
        if workflow_id and contact_urn:
            task_manager.update_workflow_status(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                status="failed",
            )

        return {
            "status": "failed",
            "error": str(e),
            "project_uuid": project_uuid,
            "workflow_id": workflow_id,
        }


def deserialize_cached_data(serialized_data: Dict) -> CachedProjectData:
    """
    Deserialize CachedProjectData from task result.

    Args:
        serialized_data: Serialized data dict from pre_generation_task result

    Returns:
        CachedProjectData instance
    """
    return CachedProjectData(
        project_dict=serialized_data.get("project_dict"),
        content_base_dict=serialized_data.get("content_base_dict"),
        team=serialized_data.get("team"),
        guardrails_config=serialized_data.get("guardrails_config"),
        inline_agent_config_dict=serialized_data.get("inline_agent_config_dict"),
        instructions=serialized_data.get("instructions"),
        agent_data=serialized_data.get("agent_data"),
    )
