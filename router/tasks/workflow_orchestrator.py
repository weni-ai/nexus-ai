"""
Workflow Orchestrator for Inline Agents

This task orchestrates the three-phase workflow:
1. Pre-Generation (separate task via pre_generation_task)
2. Generation (inline for now, will be extracted later)
3. Post-Generation (inline for now, will be extracted later)

The orchestrator is designed to be simple and clean - it only:
- Initializes workflow context
- Calls the three phases in sequence
- Handles errors and cleanup

All complex logic is delegated to helper functions or the phase tasks themselves.
"""

import logging
import os
import uuid as uuid_lib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import sentry_sdk
from django.conf import settings

from inline_agents.backends import BackendsRegistry
from nexus.celery import app as celery_app
from nexus.events import notify_async
from nexus.projects.websockets.consumers import send_preview_message_to_websocket
from router.dispatcher import dispatch
from router.entities import message_factory
from router.tasks.actions_client import get_action_clients
from router.tasks.invocation_context import CachedProjectData
from router.tasks.invoke import (
    ThrottlingException,
    UnsafeMessageException,
    _invoke_backend,
    _preprocess_message_input,
    dispatch_preview,
)
from router.tasks.pre_generation import deserialize_cached_data, pre_generation_task
from router.tasks.redis_task_manager import RedisTaskManager

logger = logging.getLogger(__name__)


# =============================================================================
# Workflow Context
# =============================================================================


@dataclass
class WorkflowContext:
    """
    Holds all state needed throughout the workflow execution.

    This centralizes all the parameters and state that would otherwise
    be passed around between functions.
    """

    # Immutable inputs
    workflow_id: str
    project_uuid: str
    contact_urn: str
    message: Dict
    preview: bool
    language: str
    user_email: str
    task_id: str
    task_manager: RedisTaskManager

    # State populated during execution
    agents_backend: Optional[str] = None
    broadcast: Optional[Dict] = None
    cached_data: Optional[CachedProjectData] = None
    flows_user_email: str = field(default_factory=lambda: os.environ.get("FLOW_USER_EMAIL", ""))


# =============================================================================
# Workflow Lifecycle Helpers
# =============================================================================


def _initialize_workflow(ctx: WorkflowContext) -> None:
    """
    Initialize the workflow: send typing indicator, handle message
    concatenation, and create workflow state.
    """
    # Set Sentry context
    sentry_sdk.set_tag("workflow_id", ctx.workflow_id)
    sentry_sdk.set_tag("project_uuid", ctx.project_uuid)
    sentry_sdk.set_tag("task_id", ctx.task_id)

    logger.info(
        f"[Workflow] Starting workflow {ctx.workflow_id} for project {ctx.project_uuid}",
        extra={
            "workflow_id": ctx.workflow_id,
            "project_uuid": ctx.project_uuid,
            "contact_urn": ctx.contact_urn,
            "preview": ctx.preview,
        },
    )

    # Send typing indicator (async, non-blocking)
    notify_async(
        event="workflow:send_typing_indicator",
        contact_urn=ctx.contact_urn,
        msg_external_id=ctx.message.get("msg_event", {}).get("msg_external_id", ""),
        project_uuid=ctx.project_uuid,
        preview=ctx.preview,
    )

    # Handle message concatenation and revoke existing workflow
    final_message_text, had_existing = ctx.task_manager.handle_workflow_message_concatenation(
        project_uuid=ctx.project_uuid,
        contact_urn=ctx.contact_urn,
        new_message_text=ctx.message.get("text", ""),
    )

    if had_existing:
        logger.info(
            f"[Workflow] Revoked existing workflow for {ctx.contact_urn}",
            extra={"workflow_id": ctx.workflow_id, "project_uuid": ctx.project_uuid},
        )

    # Update message with concatenated text
    ctx.message["text"] = final_message_text

    # Create workflow state
    ctx.task_manager.create_workflow_state(
        workflow_id=ctx.workflow_id,
        project_uuid=ctx.project_uuid,
        contact_urn=ctx.contact_urn,
        message_text=final_message_text,
    )


def _finalize_workflow(ctx: WorkflowContext, status: str = "completed") -> None:
    """Finalize workflow: update status and clear state."""
    ctx.task_manager.update_workflow_status(
        project_uuid=ctx.project_uuid,
        contact_urn=ctx.contact_urn,
        status=status,
    )
    ctx.task_manager.clear_workflow_state(ctx.project_uuid, ctx.contact_urn)

    logger.info(
        f"[Workflow] {status.capitalize()} workflow {ctx.workflow_id}",
        extra={
            "workflow_id": ctx.workflow_id,
            "project_uuid": ctx.project_uuid,
            "status": status,
        },
    )


def _handle_workflow_error(ctx: WorkflowContext, error: Exception) -> None:
    """Handle generic workflow errors: log, report to Sentry, notify preview."""
    logger.error(
        f"[Workflow] Failed workflow {ctx.workflow_id}: {error}",
        extra={
            "workflow_id": ctx.workflow_id,
            "project_uuid": ctx.project_uuid,
            "error": str(error),
        },
        exc_info=True,
    )
    sentry_sdk.capture_exception(error)

    _finalize_workflow(ctx, status="failed")

    # Send error to preview if applicable
    if ctx.user_email:
        send_preview_message_to_websocket(
            user_email=ctx.user_email,
            project_uuid=str(ctx.project_uuid),
            message_data={"type": "error", "content": str(error)},
        )


def _handle_guardrails_block(ctx: WorkflowContext, error: UnsafeMessageException) -> Any:
    """Handle guardrails block: dispatch the blocked message response."""
    logger.warning(
        f"[Workflow] Unsafe message in workflow {ctx.workflow_id}: {error.message}",
        extra={"workflow_id": ctx.workflow_id, "project_uuid": ctx.project_uuid},
    )

    message_obj = _create_message_object(ctx.message)
    _finalize_workflow(ctx, status="blocked")

    if ctx.preview and ctx.broadcast:
        return dispatch_preview(
            error.message,
            message_obj,
            ctx.broadcast,
            ctx.user_email,
            ctx.agents_backend or "unknown",
            ctx.flows_user_email,
        )
    return dispatch(
        llm_response=error.message,
        message=message_obj,
        direct_message=ctx.broadcast or {},
        user_email=ctx.flows_user_email,
        full_chunks=[],
        backend=ctx.agents_backend or "unknown",
    )


# =============================================================================
# Phase Execution Helpers
# =============================================================================


def _run_pre_generation(ctx: WorkflowContext) -> Dict:
    """
    Execute the pre-generation phase.

    Returns the pre-generation result dict with cached_data and agents_backend.
    """
    logger.info(f"[Workflow] Executing pre-generation for {ctx.workflow_id}")

    result = pre_generation_task.apply(
        args=[ctx.message],
        kwargs={
            "preview": ctx.preview,
            "language": ctx.language,
            "workflow_id": ctx.workflow_id,
        },
    ).get()

    if result["status"] == "failed":
        error_msg = result.get("error", "Unknown error")
        logger.error(f"[Workflow] Pre-generation failed: {error_msg}")
        raise Exception(f"Pre-generation failed: {error_msg}")

    # Populate context with results
    ctx.cached_data = deserialize_cached_data(result["cached_data"])
    ctx.agents_backend = result["agents_backend"]

    # Get action clients (needed for post-generation)
    ctx.broadcast, _ = get_action_clients(
        preview=ctx.preview,
        multi_agents=True,
        project_use_components=ctx.cached_data.project_dict.get("use_components", False),
    )

    return result


def _run_generation(ctx: WorkflowContext) -> str:
    """
    Execute the generation phase.

    This is currently inline but will be replaced by generation_task.
    Returns the LLM response string.
    """
    ctx.task_manager.update_workflow_status(
        project_uuid=ctx.project_uuid,
        contact_urn=ctx.contact_urn,
        status="generation",
        task_phase="generation",
        task_id=ctx.task_id,
    )

    logger.info(f"[Workflow] Executing generation for {ctx.workflow_id}")

    # Preprocess message
    processed_message, foundation_model, turn_off_rationale = _preprocess_message_input(ctx.message, ctx.agents_backend)

    # Create message object
    message_obj = _create_message_object(processed_message)

    # Get backend and invoke
    backend = BackendsRegistry.get_backend(ctx.agents_backend)

    response = _invoke_backend(
        backend=backend,
        cached_data=ctx.cached_data,
        message_obj=message_obj,
        processed_message=processed_message,
        preview=ctx.preview,
        language=ctx.language,
        user_email=ctx.user_email,
        foundation_model=foundation_model,
        turn_off_rationale=turn_off_rationale,
    )

    return response


def _run_post_generation(ctx: WorkflowContext, response: str) -> Any:
    """
    Execute the post-generation phase.

    This is currently inline but will be replaced by post_generation_task.
    Returns the dispatch result.
    """
    ctx.task_manager.update_workflow_status(
        project_uuid=ctx.project_uuid,
        contact_urn=ctx.contact_urn,
        status="post_generation",
    )

    logger.info(f"[Workflow] Executing post-generation for {ctx.workflow_id}")

    message_obj = _create_message_object(ctx.message)

    # Clear pending tasks (legacy compatibility)
    ctx.task_manager.clear_pending_tasks(message_obj.project_uuid, message_obj.contact_urn)

    # Dispatch response
    if ctx.preview:
        return dispatch_preview(
            response,
            message_obj,
            ctx.broadcast,
            ctx.user_email,
            ctx.agents_backend,
            ctx.flows_user_email,
        )
    else:
        return dispatch(
            llm_response=response,
            message=message_obj,
            direct_message=ctx.broadcast,
            user_email=ctx.flows_user_email,
            full_chunks=[],
            backend=ctx.agents_backend,
        )


# =============================================================================
# Utility Helpers
# =============================================================================


def _create_message_object(message: Dict):
    """Create a message object from a message dict."""
    return message_factory(
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


def _create_workflow_context(
    task_id: str,
    message: Dict,
    preview: bool,
    language: str,
    user_email: str,
) -> WorkflowContext:
    """Create a workflow context from task parameters."""
    return WorkflowContext(
        workflow_id=f"workflow-{uuid_lib.uuid4()}",
        project_uuid=message.get("project_uuid"),
        contact_urn=message.get("contact_urn"),
        message=message,
        preview=preview,
        language=language,
        user_email=user_email,
        task_id=task_id,
        task_manager=RedisTaskManager(),
    )


# =============================================================================
# Main Orchestrator Task
# =============================================================================


@celery_app.task(
    bind=True,
    name="router.tasks.workflow_orchestrator.inline_agent_workflow",
    soft_time_limit=300,
    time_limit=360,
    acks_late=getattr(settings, "START_INLINE_AGENTS_ACK_LATE", True),
    autoretry_for=(ThrottlingException,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def inline_agent_workflow(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
) -> Any:
    """
    Main workflow orchestrator for inline agents.

    This task replaces start_inline_agents when USE_WORKFLOW_ARCHITECTURE is enabled.
    It orchestrates the workflow through three phases:
    1. Pre-Generation (via pre_generation_task)
    2. Generation (inline for now, will be generation_task)
    3. Post-Generation (inline for now, will be post_generation_task)

    The orchestrator is intentionally simple - all complex logic is delegated
    to the phase tasks and helper functions.
    """
    ctx = _create_workflow_context(
        task_id=self.request.id,
        message=message,
        preview=preview,
        language=language,
        user_email=user_email,
    )

    try:
        # Initialize workflow (typing indicator, message concat, state creation)
        _initialize_workflow(ctx)

        # Phase 1: Pre-Generation
        _run_pre_generation(ctx)

        # Phase 2: Generation (will be generation_task.apply() later)
        response = _run_generation(ctx)

        # Phase 3: Post-Generation (will be post_generation_task.apply() later)
        result = _run_post_generation(ctx, response)

        # Finalize workflow
        _finalize_workflow(ctx)

        return result

    except UnsafeMessageException as e:
        return _handle_guardrails_block(ctx, e)

    except Exception as e:
        _handle_workflow_error(ctx, e)
        raise
