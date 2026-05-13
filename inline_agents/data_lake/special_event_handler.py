from typing import Optional

import pendulum
import sentry_sdk
from django.conf import settings

from router.services.sqs_producer import get_conversation_events_producer
from router.tasks.sqs_message_events import build_csat_event, build_custom_event, build_nps_event


class SpecialEventHandler:
    """Handler for special event types that require custom processing."""

    def __init__(self, agent_uuid: str, conversation_field: Optional[str] = None):
        self.agent_uuid = agent_uuid
        self.conversation_field = conversation_field

    def _send_to_sqs(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        sqs_correlation_id: Optional[str] = None,
    ) -> None:
        """Send the special event to SQS for conversation-ms."""
        key = event_data.get("key")
        value = event_data.get("value")

        if not key or value is None:
            return

        try:
            event = None
            if key == "weni_csat":
                event = build_csat_event(
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    channel_uuid=channel_uuid,
                    value=str(value),
                    correlation_id=sqs_correlation_id,
                )
            elif key == "weni_nps":
                event = build_nps_event(
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    channel_uuid=channel_uuid,
                    value=str(value),
                    correlation_id=sqs_correlation_id,
                )
            else:
                event = build_custom_event(
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    channel_uuid=channel_uuid,
                    key=key,
                    value=str(value),
                    correlation_id=sqs_correlation_id,
                )

            if event:
                get_conversation_events_producer().send_event(event.to_dict())

        except Exception as e:
            sentry_sdk.capture_exception(e)

    def process(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        conversation: Optional[object] = None,
        *,
        skip_conversation_sqs: bool = False,
        sqs_correlation_id: Optional[str] = None,
    ) -> None:
        """Process the special event."""
        if not skip_conversation_sqs:
            self._send_to_sqs(
                event_data, project_uuid, contact_urn, channel_uuid, sqs_correlation_id=sqs_correlation_id
            )

        event_data.setdefault("metadata", {})
        event_data["metadata"]["agent_uuid"] = self.agent_uuid

        if self.conversation_field:
            from nexus.usecases.inline_agents.update import update_conversation_data

            # Persist CSAT/NPS on Django Conversation only when an ORM row is explicitly passed (legacy).
            # AB 2.x inline path does not create local Conversation rows; SQS remains the handoff.
            if conversation is not None:
                to_update = {self.conversation_field: event_data.get("value")}
                update_conversation_data(
                    to_update=to_update, project_uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid
                )

            metadata = event_data.get("metadata", {})

            if conversation is not None:
                if "conversation_uuid" not in metadata:
                    metadata["conversation_uuid"] = str(conversation.uuid)

                if "conversation_start_date" not in metadata and conversation.start_date:
                    metadata["conversation_start_date"] = pendulum.instance(conversation.start_date).to_iso8601_string()

                if "conversation_end_date" not in metadata and conversation.end_date:
                    metadata["conversation_end_date"] = pendulum.instance(conversation.end_date).to_iso8601_string()


def get_special_event_handlers() -> dict[str, SpecialEventHandler]:
    """Get registry of special event handlers."""
    return {
        "weni_csat": SpecialEventHandler(agent_uuid=settings.AGENT_UUID_CSAT, conversation_field="csat"),
        "weni_nps": SpecialEventHandler(agent_uuid=settings.AGENT_UUID_NPS, conversation_field="nps"),
    }
