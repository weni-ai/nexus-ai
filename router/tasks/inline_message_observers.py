"""Observers for inline_message:received event. Build SQS-shaped events."""

import logging
import uuid
from typing import Any, Optional

import sentry_sdk

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver
from router.services.sqs_producer import get_conversation_events_producer
from router.tasks.redis_task_manager import RedisTaskManager
from router.tasks.sqs_message_events import build_message_sent_event

logger = logging.getLogger(__name__)


def _should_emit_conversation_outgoing_sqs(
    project_uuid: str,
    contact_urn: str,
    celery_task_id: Optional[str],
) -> bool:
    """
    Emit ``message.sent`` only when this run is still the latest Celery task for the contact
    (same superseded rule as ``dispatch`` / ``_should_dispatch_latest``).
    """
    if not celery_task_id or not project_uuid or not contact_urn:
        return True

    latest = RedisTaskManager().get_latest_task_id(project_uuid, contact_urn)
    if latest is None:
        logger.info(
            "latest_task missing in Redis; emitting conversation outgoing SQS anyway "
            "project_uuid=%s contact_urn=%s celery_task_id=%s",
            project_uuid,
            contact_urn,
            celery_task_id,
        )
        return True

    if str(latest) != str(celery_task_id):
        logger.info(
            "Skipping conversation outgoing SQS (superseded): celery_task_id=%s latest=%s",
            celery_task_id,
            latest,
        )
        return False
    return True


def _report_missing_required_sentry(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    reason: str = "message_conversation_log_uuid not provided",
) -> None:
    """Report missing required data to Sentry (event still sent with fallback id)."""
    sentry_sdk.set_tag("project_uuid", project_uuid)
    sentry_sdk.set_tag("contact_urn", contact_urn)
    sentry_sdk.set_tag("channel_uuid", channel_uuid)
    sentry_sdk.set_context("inline_message_observer", {"reason": reason})
    sentry_sdk.capture_message(
        f"[InlineMessageObserver] {reason}, sending with fallback id",
        level="warning",
    )


@observer("inline_message:received", isolate_errors=True)
class InlineMessageReceivedObserver(EventObserver):
    """Runs when inline agent execution has completed."""

    def perform(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        contact_name: str,
        message_text: str,
        response_text: str,
        incoming_created_at: str,
        outgoing_created_at: str,
        preview: bool = False,
        **kwargs: Any,
    ) -> None:
        if preview or kwargs.get("skip_conversation_sqs"):
            return

        message_conversation_log_uuid = kwargs.get("message_conversation_log_uuid")
        if not message_conversation_log_uuid:
            logger.warning("message_conversation_log_uuid not provided, using fallback id so message is not lost")
            _report_missing_required_sentry(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid,
            )

        turn_id = kwargs.get("turn_id")
        message_id = message_conversation_log_uuid or str(uuid.uuid4())
        outgoing_id = f"{turn_id}:outgoing" if turn_id else str(uuid.uuid4())
        sent_event = build_message_sent_event(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            contact_name=contact_name,
            message_text=response_text,
            created_at=outgoing_created_at,
            message_id=message_id,
            correlation_id=outgoing_id,
        )
        logger.debug("inline_message:received SQS event (outgoing): %s", sent_event.to_dict())


@observer("inline_message:received", isolate_errors=True)
class InlineMessageReceivedMetricsObserver(EventObserver):
    """Send outgoing (message.sent) to SQS when inline agent execution has completed."""

    def perform(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        contact_name: str,
        message_text: str,
        response_text: str,
        incoming_created_at: str,
        outgoing_created_at: str,
        preview: bool = False,
        **kwargs: Any,
    ) -> None:
        if preview or kwargs.get("skip_conversation_sqs"):
            return

        if not _should_emit_conversation_outgoing_sqs(
            project_uuid,
            contact_urn,
            kwargs.get("celery_task_id"),
        ):
            return

        message_conversation_log_uuid = kwargs.get("message_conversation_log_uuid")
        # Missing trace ID is reported only by InlineMessageReceivedObserver to avoid duplicate Sentry
        turn_id = kwargs.get("turn_id")
        message_id = message_conversation_log_uuid or str(uuid.uuid4())
        outgoing_id = f"{turn_id}:outgoing" if turn_id else str(uuid.uuid4())
        sent_event = build_message_sent_event(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            contact_name=contact_name,
            message_text=response_text,
            created_at=outgoing_created_at,
            message_id=message_id,
            correlation_id=outgoing_id,
        )
        try:
            get_conversation_events_producer().send_event(sent_event.to_dict())
        except Exception as exc:
            logger.exception(
                "Failed to send message.sent event to SQS",
                extra={"project_uuid": project_uuid, "turn_id": turn_id},
            )
            sentry_sdk.capture_exception(exc)
