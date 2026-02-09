"""Observers for inline_message:received event. Build SQS-shaped events."""

import logging
from typing import Any

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver
from router.services.sqs_producer import get_conversation_events_producer
from router.tasks.sqs_message_events import build_inline_message_sqs_events

logger = logging.getLogger(__name__)


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
        if preview:
            return

        events = build_inline_message_sqs_events(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            contact_name=contact_name,
            message_text=message_text,
            response_text=response_text,
            incoming_created_at=incoming_created_at,
            outgoing_created_at=outgoing_created_at,
        )
        logger.debug("inline_message:received SQS events: %s", events)


@observer("inline_message:received", isolate_errors=True)
class InlineMessageReceivedMetricsObserver(EventObserver):
    """Second observer for inline_message:received (e.g. send to SQS)."""

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
        if preview:
            return

        events = build_inline_message_sqs_events(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            contact_name=contact_name,
            message_text=message_text,
            response_text=response_text,
            incoming_created_at=incoming_created_at,
            outgoing_created_at=outgoing_created_at,
        )
        get_conversation_events_producer().send_events(events)
