from typing import Optional

import pendulum
from django.conf import settings


class SpecialEventHandler:
    """Handler for special event types that require custom processing."""

    def __init__(self, agent_uuid: str, conversation_field: Optional[str] = None):
        self.agent_uuid = agent_uuid
        self.conversation_field = conversation_field

    def process(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        conversation: Optional[object] = None,
    ) -> None:
        """Process the special event."""
        event_data.setdefault("metadata", {})
        event_data["metadata"]["agent_uuid"] = self.agent_uuid

        if self.conversation_field:
            from nexus.intelligences.models import Conversation
            from nexus.usecases.inline_agents.update import update_conversation_data

            to_update = {self.conversation_field: event_data.get("value")}
            update_conversation_data(
                to_update=to_update, project_uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid
            )

            # Add conversation fields to metadata
            metadata = event_data.get("metadata", {})

            # Use provided conversation object if available, otherwise query for it
            conversation_obj = conversation
            if not conversation_obj and channel_uuid:
                try:
                    conversation_obj = (
                        Conversation.objects.filter(
                            project__uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid
                        )
                        .order_by("-created_at")
                        .first()
                    )
                except Exception as e:
                    # If conversation lookup fails, log to Sentry for debugging
                    import sentry_sdk

                    sentry_sdk.set_tag("project_uuid", project_uuid)
                    sentry_sdk.set_tag("contact_urn", contact_urn)
                    sentry_sdk.set_tag("channel_uuid", channel_uuid)
                    sentry_sdk.set_context(
                        "conversation_lookup",
                        {
                            "project_uuid": project_uuid,
                            "contact_urn": contact_urn,
                            "channel_uuid": channel_uuid,
                            "event_key": event_data.get("key"),
                            "method": "SpecialEventHandler.process",
                        },
                    )
                    sentry_sdk.capture_exception(e)
                    # Continue without conversation fields - they will be handled by _enrich_metadata
                    conversation_obj = None

            if conversation_obj:
                # Add conversation_uuid if missing
                if "conversation_uuid" not in metadata:
                    metadata["conversation_uuid"] = str(conversation_obj.uuid)

                # Add conversation_start_date if missing and start_date exists
                if "conversation_start_date" not in metadata and conversation_obj.start_date:
                    metadata["conversation_start_date"] = pendulum.instance(
                        conversation_obj.start_date
                    ).to_iso8601_string()

                # Add conversation_end_date if missing and end_date exists
                if "conversation_end_date" not in metadata and conversation_obj.end_date:
                    metadata["conversation_end_date"] = pendulum.instance(conversation_obj.end_date).to_iso8601_string()


def get_special_event_handlers() -> dict[str, SpecialEventHandler]:
    """Get registry of special event handlers."""
    return {
        "weni_csat": SpecialEventHandler(agent_uuid=settings.AGENT_UUID_CSAT, conversation_field="csat"),
        "weni_nps": SpecialEventHandler(agent_uuid=settings.AGENT_UUID_NPS, conversation_field="nps"),
    }
