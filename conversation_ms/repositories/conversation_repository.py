import logging
from typing import Optional

import sentry_sdk

logger = logging.getLogger(__name__)


class ConversationRepository:
    def get_conversation(
        self, project_uuid: str, contact_urn: str, channel_uuid: Optional[str] = None
    ) -> Optional[object]:
        try:
            from nexus.intelligences.models import Conversation

            filters = {
                "project__uuid": project_uuid,
                "contact_urn": contact_urn,
            }

            if channel_uuid:
                filters["channel_uuid"] = channel_uuid

            conversation = Conversation.objects.filter(**filters).order_by("-created_at").first()

            return conversation
        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_tag("channel_uuid", channel_uuid)
            sentry_sdk.set_context(
                "conversation_repository",
                {
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[ConversationRepository] Error getting conversation",
                extra={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
