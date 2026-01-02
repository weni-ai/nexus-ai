import logging

import sentry_sdk

from conversation_ms.models.events import MessageReceivedEvent, MessageSentEvent

logger = logging.getLogger(__name__)


class MessageRepository:
    def save_received_message(self, conversation, event: MessageReceivedEvent):
        try:
            message_data = event.message
            message_id = message_data.get("message_id") or message_data.get("id")
            message_text = message_data.get("text", "")

            logger.info(
                "[MessageRepository] Saving received message",
                extra={
                    "conversation_uuid": str(conversation.uuid),
                    "message_id": message_id,
                    "correlation_id": event.correlation_id,
                    "text_preview": message_text[:100] if message_text else None,
                },
            )

        except Exception as e:
            sentry_sdk.set_tag("project_uuid", event.project_uuid)
            sentry_sdk.set_tag("contact_urn", event.contact_urn)
            sentry_sdk.set_context(
                "message_repository",
                {
                    "event": event,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                    "message_id": message_data.get("message_id") if message_data else None,
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[MessageRepository] Error saving received message",
                extra={
                    "event": event,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    def save_sent_message(self, conversation, event: MessageSentEvent):
        try:
            message_data = event.message
            message_id = message_data.get("message_id") or message_data.get("id")
            message_text = message_data.get("text", "")

            logger.info(
                "[MessageRepository] Saving sent message",
                extra={
                    "conversation_uuid": str(conversation.uuid),
                    "message_id": message_id,
                    "correlation_id": event.correlation_id,
                    "text_preview": message_text[:100] if message_text else None,
                },
            )

        except Exception as e:
            sentry_sdk.set_tag("project_uuid", event.project_uuid)
            sentry_sdk.set_tag("contact_urn", event.contact_urn)
            sentry_sdk.set_context(
                "message_repository",
                {
                    "event": event,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                    "message_id": message_data.get("message_id") if message_data else None,
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[MessageRepository] Error saving sent message",
                extra={
                    "event": event,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
