"""
Pre-Generation Celery Task

This task handles all pre-generation work:
- Fetching and caching project data via PreGenerationService
- Message preprocessing (attachments, products, overwrite)
- Building invoke_kwargs ready for backend.invoke_agents()

The task returns everything needed for generation to be a pure model call.
"""

import logging
from typing import Dict, Optional, Tuple

import sentry_sdk

from nexus.celery import app as celery_app
from router.entities import message_factory
from router.services.pre_generation_service import PreGenerationService
from router.tasks.invocation_context import CachedProjectData
from router.tasks.invoke import (
    EmptyTextException,
    handle_attachments,
    handle_overwrite_message,
    handle_product_items,
)
from router.tasks.redis_task_manager import RedisTaskManager

logger = logging.getLogger(__name__)


def get_task_manager() -> RedisTaskManager:
    """Get the default task manager instance."""
    return RedisTaskManager()


def _preprocess_message(message: Dict) -> Tuple[Dict, bool]:
    """
    Preprocess message: handle attachments, products, and overwrite.

    Returns:
        Tuple of (processed_message, turn_off_rationale)
    """
    text = message.get("text", "")
    attachments = message.get("attachments", [])
    product_items = message.get("metadata", {}).get("order", {}).get("product_items", [])
    overwrite_message = message.get("metadata", {}).get("overwrite_message")

    text, turn_off_rationale = handle_attachments(text=text, attachments=attachments)

    if len(product_items) > 0:
        text = handle_product_items(text, product_items)

    if overwrite_message:
        text = handle_overwrite_message(text, overwrite_message)

    if not text.strip():
        raise EmptyTextException(
            f"Text is empty after processing. Original text: '{message.get('text', '')}', "
            f"attachments: {attachments}, product_items: {product_items}"
        )

    processed_message = message.copy()
    processed_message["text"] = text
    return processed_message, turn_off_rationale


def _build_invoke_kwargs(
    cached_data: CachedProjectData,
    message: Dict,
    preview: bool,
    language: str,
    user_email: str,
    turn_off_rationale: bool,
) -> Dict:
    """
    Build all kwargs needed for backend.invoke_agents().

    This prepares everything so generation can be a pure model call.
    """
    # Get base kwargs from cached data
    invoke_kwargs = cached_data.get_invoke_kwargs(team=cached_data.team)

    # Create message object for extracting fields
    message_obj = message_factory(
        project_uuid=message.get("project_uuid"),
        text=message.get("text"),
        contact_urn=message.get("contact_urn"),
        metadata=message.get("metadata"),
        attachments=message.get("attachments", []),
        msg_event=message.get("msg_event"),
        contact_fields=message.get("contact_fields", {}),
        contact_name=message.get("contact_name", ""),
        channel_uuid=message.get("channel_uuid", ""),
    )

    # Add message-specific parameters
    invoke_kwargs.update(
        {
            "input_text": message_obj.text,
            "contact_urn": message_obj.contact_urn,
            "project_uuid": message_obj.project_uuid,
            "sanitized_urn": message_obj.sanitized_urn,
            "contact_fields": message_obj.contact_fields_as_json,
            "contact_name": message_obj.contact_name,
            "channel_uuid": message_obj.channel_uuid,
            "msg_external_id": message.get("msg_event", {}).get("msg_external_id", ""),
            "preview": preview,
            "language": language,
            "user_email": user_email,
            "foundation_model": None,  # Only used by Bedrock, which we're not using
            "turn_off_rationale": turn_off_rationale,
            "channel_type": message.get("channel_type", ""),
        }
    )

    return invoke_kwargs


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
    user_email: str = "",
    workflow_id: Optional[str] = None,
) -> Dict:
    """
    Pre-Generation Task - Fetches data and prepares invoke_kwargs for generation.

    Makes generation a PURE model call with zero preprocessing.
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

        # Preprocess message (attachments, products, overwrite)
        processed_message, turn_off_rationale = _preprocess_message(message)

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

        # Build invoke_kwargs (ready for backend.invoke_agents())
        invoke_kwargs = _build_invoke_kwargs(
            cached_data=cached_data,
            message=processed_message,
            preview=preview,
            language=language,
            user_email=user_email,
            turn_off_rationale=turn_off_rationale,
        )

        logger.info(f"[PreGeneration] Success for project {project_uuid}, contact {contact_urn}")

        return {
            "status": "success",
            "invoke_kwargs": invoke_kwargs,
            "agents_backend": agents_backend,
            "processed_message": processed_message,
            "project_uuid": project_uuid,
            "workflow_id": workflow_id,
            "use_components": project_dict.get("use_components", False),
        }

    except Exception as e:
        logger.error(f"[PreGeneration] Failed for project {project_uuid}, contact {contact_urn}: {e}", exc_info=True)
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
        formatter_agent_configurations=serialized_data.get("formatter_agent_configurations"),
    )
