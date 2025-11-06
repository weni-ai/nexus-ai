from typing import Optional
from django.conf import settings


class SpecialEventHandler:
    """Handler for special event types that require custom processing."""

    def __init__(
        self,
        agent_uuid: str,
        conversation_field: Optional[str] = None
    ):
        self.agent_uuid = agent_uuid
        self.conversation_field = conversation_field

    def process(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str
    ) -> None:
        """Process the special event."""
        event_data["metadata"]["agent_uuid"] = self.agent_uuid

        if self.conversation_field:
            from nexus.usecases.inline_agents.update import update_conversation_data
            to_update = {self.conversation_field: event_data.get("value")}
            update_conversation_data(
                to_update=to_update,
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid
            )


def get_special_event_handlers() -> dict[str, SpecialEventHandler]:
    """Get registry of special event handlers."""
    return {
        "weni_csat": SpecialEventHandler(
            agent_uuid=settings.AGENT_UUID_CSAT,
            conversation_field="csat"
        ),
        "weni_nps": SpecialEventHandler(
            agent_uuid=settings.AGENT_UUID_NPS,
            conversation_field="nps"
        ),
    }
