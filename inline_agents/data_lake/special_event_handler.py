from typing import Optional

from django.conf import settings


class SpecialEventHandler:
    """Handler for special event types that require custom processing."""

    def __init__(self, agent_uuid: str, conversation_field: Optional[str] = None):
        self.agent_uuid = agent_uuid
        self.conversation_field = conversation_field

    def process(self, event_data: dict, project_uuid: str, contact_urn: str, channel_uuid: str) -> None:
        """Process the special event."""
        event_data["metadata"]["agent_uuid"] = self.agent_uuid

        if self.conversation_field:
            from nexus.intelligences.models import Conversation
            from nexus.usecases.inline_agents.update import update_conversation_data

            to_update = {self.conversation_field: event_data.get("value")}
            update_conversation_data(
                to_update=to_update, project_uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid
            )

            # Add conversation_uuid to metadata
            if channel_uuid and "conversation_uuid" not in event_data.get("metadata", {}):
                try:
                    conversation = (
                        Conversation.objects.filter(
                            project__uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid
                        )
                        .order_by("-created_at")
                        .first()
                    )
                    if conversation:
                        event_data["metadata"]["conversation_uuid"] = str(conversation.uuid)
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
                    # Continue without conversation_uuid - it will be handled by _enrich_metadata
                    pass


def get_special_event_handlers() -> dict[str, SpecialEventHandler]:
    """Get registry of special event handlers."""
    return {
        "weni_csat": SpecialEventHandler(agent_uuid=settings.AGENT_UUID_CSAT, conversation_field="csat"),
        "weni_nps": SpecialEventHandler(agent_uuid=settings.AGENT_UUID_NPS, conversation_field="nps"),
    }
