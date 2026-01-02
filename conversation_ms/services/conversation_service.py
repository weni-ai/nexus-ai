import logging
from typing import Optional

import sentry_sdk

logger = logging.getLogger(__name__)


class ConversationService:
    def ensure_conversation_exists(
        self, project_uuid: str, contact_urn: str, contact_name: str, channel_uuid: Optional[str] = None
    ) -> Optional[object]:
        if not channel_uuid:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_context(
                "conversation_creation",
                {
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "contact_name": contact_name,
                    "channel_uuid": None,
                    "method": "ensure_conversation_exists",
                    "reason": "channel_uuid is None",
                },
            )
            sentry_sdk.capture_message(
                "Conversation not created: channel_uuid is None (ConversationService)", level="info"
            )
            logger.warning(
                "[ConversationService] Conversation not created: channel_uuid is None",
                extra={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "contact_name": contact_name,
                },
            )
            return None

        try:
            from router.services.conversation_service import ConversationService as MainConversationService

            main_service = MainConversationService()

            conversation = main_service.ensure_conversation_exists(
                project_uuid=project_uuid, contact_urn=contact_urn, contact_name=contact_name, channel_uuid=channel_uuid
            )

            if conversation:
                logger.debug(
                    "[ConversationService] Conversation ensured",
                    extra={
                        "conversation_uuid": str(conversation.uuid),
                        "project_uuid": project_uuid,
                        "contact_urn": contact_urn,
                    },
                )

            return conversation

        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_tag("channel_uuid", channel_uuid)
            sentry_sdk.set_context(
                "conversation_creation",
                {
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "contact_name": contact_name,
                    "channel_uuid": channel_uuid,
                    "method": "ensure_conversation_exists",
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[ConversationService] Error ensuring conversation exists",
                extra={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
