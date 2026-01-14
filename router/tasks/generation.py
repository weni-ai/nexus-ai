import logging
from typing import Dict, Optional

import sentry_sdk

from inline_agents.backends import BackendsRegistry
from inline_agents.backends.openai.redis_pool import get_redis_client
from nexus.celery import app as celery_app
from router.tasks.invoke import ThrottlingException
from router.tasks.redis_task_manager import RedisTaskManager

logger = logging.getLogger(__name__)

WORKFLOW_BACKEND = "OpenAIWorkflowBackend"


def get_task_manager() -> RedisTaskManager:
    return RedisTaskManager(redis_client=get_redis_client())


@celery_app.task(
    bind=True,
    name="router.tasks.generation.generation_task",
    soft_time_limit=240,
    time_limit=300,
    max_retries=2,
    autoretry_for=(ThrottlingException,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def generation_task(
    self,
    invoke_kwargs: Dict,
    agents_backend: str,
    project_uuid: str,
    contact_urn: str,
    workflow_id: Optional[str] = None,
) -> Dict:
    task_manager = get_task_manager()

    if workflow_id and contact_urn:
        task_manager.update_workflow_status(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            status="generation",
            task_phase="generation",
            task_id=self.request.id,
        )

    try:
        backend = BackendsRegistry.get_backend(WORKFLOW_BACKEND)
        response = backend.invoke_agents(**invoke_kwargs)

        logger.info(f"[Generation] Success for project {project_uuid}, contact {contact_urn}")

        return {
            "status": "success",
            "response": response,
            "workflow_id": workflow_id,
            "project_uuid": project_uuid,
        }

    except Exception as e:
        logger.error(f"[Generation] Failed for project {project_uuid}, contact {contact_urn}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)

        return {
            "status": "failed",
            "error": str(e),
            "project_uuid": project_uuid,
            "workflow_id": workflow_id,
        }
