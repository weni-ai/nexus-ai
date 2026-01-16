"""
Workflow Orchestrator for Inline Agents

This task orchestrates the three-phase workflow:
1. Pre-Generation (separate task via pre_generation_task)
2. Generation (separate task via generation_task)
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

from nexus.celery import app as celery_app
from nexus.events import notify_async
from nexus.projects.websockets.consumers import send_preview_message_to_websocket
from router.dispatcher import dispatch
from router.entities import message_factory
from router.tasks.actions_client import get_action_clients
from router.tasks.generation import generation_task
from router.tasks.invoke import (
    ThrottlingException,
    UnsafeMessageException,
    dispatch_preview,
)
from router.tasks.pre_generation import pre_generation_task
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
    use_components: bool = False
    flows_user_email: str = field(default_factory=lambda: os.environ.get("FLOW_USER_EMAIL", ""))
    cached_data: Optional[Dict] = None


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
        f"[Workflow] Starting workflow {ctx.workflow_id}, project {ctx.project_uuid}, contact {ctx.contact_urn}"
    )

    # Send typing indicator (async, non-blocking)
    logger.info(f"[Workflow] Dispatching typing indicator for project {ctx.project_uuid}, contact {ctx.contact_urn}")
    notify_async(
        event="workflow:send_typing_indicator",
        contact_urn=ctx.contact_urn,
        msg_external_id=ctx.message.get("msg_event", {}).get("msg_external_id", ""),
        project_uuid=ctx.project_uuid,
        preview=ctx.preview,
    )

    # Handle message concatenation and revoke existing workflow
    # Pass current_task_id to avoid revoking self on retry
    final_message_text, had_existing = ctx.task_manager.handle_workflow_message_concatenation(
        project_uuid=ctx.project_uuid,
        contact_urn=ctx.contact_urn,
        new_message_text=ctx.message.get("text", ""),
        current_task_id=ctx.task_id,
    )

    if had_existing:
        logger.info(f"[Workflow] Revoked existing workflow for {ctx.project_uuid}, {ctx.contact_urn}")

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

    logger.info(f"[Workflow] {status.capitalize()} for {ctx.project_uuid}, {ctx.contact_urn}")


def _handle_workflow_error(ctx: WorkflowContext, error: Exception) -> None:
    """Handle generic workflow errors: log, report to Sentry, notify preview."""
    logger.error(
        f"[Workflow] Failed workflow {ctx.workflow_id}, project {ctx.project_uuid}, contact {ctx.contact_urn}: {error}",
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
    logger.warning(f"[Workflow] Unsafe message for {ctx.project_uuid}, {ctx.contact_urn}: {error.message}")

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

    Returns the pre-generation result dict with invoke_kwargs and agents_backend.
    """
    logger.info(f"[Workflow] Executing pre-generation for {ctx.project_uuid}, {ctx.contact_urn}")

    # Call directly using .run() to avoid Celery's "never call .get() within a task" error
    result = pre_generation_task.run(
        ctx.message,
        preview=ctx.preview,
        language=ctx.language,
        user_email=ctx.user_email,
        workflow_id=ctx.workflow_id,
    )

    if result["status"] == "failed":
        error_msg = result.get("error", "Unknown error")
        logger.error(f"[Workflow] Pre-generation failed for {ctx.project_uuid}, {ctx.contact_urn}: {error_msg}")
        raise Exception(f"Pre-generation failed: {error_msg}")

    # Populate context with results
    ctx.agents_backend = result["agents_backend"]
    ctx.use_components = result.get("use_components", False)

    # Get action clients (needed for post-generation)
    ctx.broadcast, _ = get_action_clients(
        preview=ctx.preview,
        multi_agents=True,
        project_use_components=ctx.use_components,
    )

    return result


def _run_generation(ctx: WorkflowContext, pre_gen_result: Dict) -> str:
    """
    Execute the generation phase via generation_task.

    Generation is now a PURE model call - all preprocessing is done in pre-generation.

    Returns the LLM response string.
    """
    logger.info(f"[Workflow] Executing generation for {ctx.project_uuid}, {ctx.contact_urn}")

    # Call generation_task directly using .run() to avoid Celery's "never call .get() within a task" error
    # invoke_kwargs is ready-to-use - generation just calls backend.invoke_agents()
    result = generation_task.run(
        invoke_kwargs=pre_gen_result["invoke_kwargs"],
        agents_backend=ctx.agents_backend,
        project_uuid=ctx.project_uuid,
        contact_urn=ctx.contact_urn,
        workflow_id=ctx.workflow_id,
    )

    if result["status"] == "failed":
        error_msg = result.get("error", "Unknown error")
        logger.error(f"[Workflow] Generation failed for {ctx.project_uuid}, {ctx.contact_urn}: {error_msg}")
        raise Exception(f"Generation failed: {error_msg}")

    return result["response"]


def _run_post_generation(ctx: WorkflowContext, response: str, pre_gen_result: Dict) -> Any:
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

    logger.info(f"[Workflow] Executing post-generation for {ctx.project_uuid}, {ctx.contact_urn}")

    # Use processed_message from pre-generation (has preprocessed text)
    processed_message = pre_gen_result.get("processed_message", ctx.message)
    message_obj = _create_message_object(processed_message)

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

    This task replaces start_inline_agents when project is in WORKFLOW_ARCHITECTURE_PROJECTS.
    It orchestrates the workflow through three phases:
    1. Pre-Generation (via pre_generation_task)
    2. Generation (via generation_task)
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

        # Phase 1: Pre-Generation (data fetching + message preprocessing)
        pre_gen_result = _run_pre_generation(ctx)

        # Phase 2: Generation (PURE model call - invoke_kwargs ready to use)
        response = _run_generation(ctx, pre_gen_result)

        # Phase 3: Post-Generation (dispatch response)
        result = _run_post_generation(ctx, response, pre_gen_result)

        # Finalize workflow
        _finalize_workflow(ctx)

        return result

    except UnsafeMessageException as e:
        return _handle_guardrails_block(ctx, e)

    except Exception as e:
        _handle_workflow_error(ctx, e)
        raise
