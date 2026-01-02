import logging

import sentry_sdk

from conversation_ms.models.events import MessageReceivedEvent, MessageSentEvent
from conversation_ms.repositories.message_repository import MessageRepository
from conversation_ms.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


class MessageService:
    def __init__(self):
        self.conversation_service = ConversationService()
        self.message_repository = MessageRepository()

    def process_message_received(self, event_data: dict):
        try:
            event = MessageReceivedEvent.from_sqs_event(event_data)

            logger.info(
                "[MessageService] Processing message.received",
                extra={
                    "correlation_id": event.correlation_id,
                    "project_uuid": event.project_uuid,
                    "contact_urn": event.contact_urn,
                },
            )

            contact_name = event.message.get("contact_name", "")
            conversation = self.conversation_service.ensure_conversation_exists(
                project_uuid=event.project_uuid,
                contact_urn=event.contact_urn,
                contact_name=contact_name,
                channel_uuid=event.channel_uuid,
            )

            if not conversation:
                logger.warning(
                    "[MessageService] Conversation not created (channel_uuid missing), skipping message",
                    extra={
                        "correlation_id": event.correlation_id,
                        "project_uuid": event.project_uuid,
                        "contact_urn": event.contact_urn,
                    },
                )
                return

            self.message_repository.save_received_message(conversation=conversation, event=event)

            logger.info(
                "[MessageService] Message.received processed successfully",
                extra={
                    "correlation_id": event.correlation_id,
                    "conversation_uuid": str(conversation.uuid),
                },
            )

        except Exception as e:
            sentry_sdk.set_tag("project_uuid", event_data.get("data", {}).get("project_uuid", "unknown"))
            sentry_sdk.set_tag("contact_urn", event_data.get("data", {}).get("contact_urn", "unknown"))
            sentry_sdk.set_context(
                "message_processing",
                {
                    "event_type": "message.received",
                    "event_data": event_data,
                    "correlation_id": event_data.get("correlation_id"),
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[MessageService] Error processing message.received",
                extra={"event_data": event_data, "error": str(e)},
                exc_info=True,
            )
            raise

    def process_message_sent(self, event_data: dict):
        try:
            event = MessageSentEvent.from_sqs_event(event_data)

            logger.info(
                "[MessageService] Processing message.sent",
                extra={
                    "correlation_id": event.correlation_id,
                    "project_uuid": event.project_uuid,
                    "contact_urn": event.contact_urn,
                },
            )

            contact_name = event.message.get("contact_name", "")
            conversation = self.conversation_service.ensure_conversation_exists(
                project_uuid=event.project_uuid,
                contact_urn=event.contact_urn,
                contact_name=contact_name,
                channel_uuid=event.channel_uuid,
            )

            if not conversation:
                logger.warning(
                    "[MessageService] Conversation not created (channel_uuid missing), skipping message",
                    extra={
                        "correlation_id": event.correlation_id,
                        "project_uuid": event.project_uuid,
                        "contact_urn": event.contact_urn,
                    },
                )
                return

            self.message_repository.save_sent_message(conversation=conversation, event=event)

            logger.info(
                "[MessageService] Message.sent processed successfully",
                extra={
                    "correlation_id": event.correlation_id,
                    "conversation_uuid": str(conversation.uuid),
                },
            )

        except Exception as e:
            sentry_sdk.set_tag("project_uuid", event_data.get("data", {}).get("project_uuid", "unknown"))
            sentry_sdk.set_tag("contact_urn", event_data.get("data", {}).get("contact_urn", "unknown"))
            sentry_sdk.set_context(
                "message_processing",
                {
                    "event_type": "message.sent",
                    "event_data": event_data,
                    "correlation_id": event_data.get("correlation_id"),
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[MessageService] Error processing message.sent",
                extra={"event_data": event_data, "error": str(e)},
                exc_info=True,
            )
            raise
