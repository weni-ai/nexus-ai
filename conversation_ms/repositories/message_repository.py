import logging

import sentry_sdk

from conversation_ms.models.events import MessageReceivedEvent, MessageSentEvent
from router.repositories.dynamo.message import MessageRepository as DynamoMessageRepository
from router.repositories.entities import ResolutionEntities

logger = logging.getLogger(__name__)


class MessageRepository:
    def __init__(self):
        self.dynamo_repository = DynamoMessageRepository()

    def _is_conversation_in_progress(self, conversation) -> bool:
        return str(conversation.resolution) == "2"

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
                    "in_progress": self._is_conversation_in_progress(conversation),
                },
            )

            if self._is_conversation_in_progress(conversation):
                formatted_message = {
                    "text": message_text,
                    "source": message_data.get("source", "incoming"),
                    "created_at": event.timestamp.isoformat()
                    if hasattr(event.timestamp, "isoformat")
                    else str(event.timestamp),
                }

                self.dynamo_repository.storage_message(
                    project_uuid=event.project_uuid,
                    contact_urn=event.contact_urn,
                    message_data=formatted_message,
                    channel_uuid=event.channel_uuid,
                    resolution_status=ResolutionEntities.IN_PROGRESS,
                    ttl_hours=48,
                )

                logger.debug(
                    "[MessageRepository] Message saved to DynamoDB",
                    extra={"conversation_uuid": str(conversation.uuid)},
                )
            else:
                logger.debug(
                    "[MessageRepository] Conversation not in progress, skipping DynamoDB save",
                    extra={"conversation_uuid": str(conversation.uuid), "resolution": conversation.resolution},
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
                    "in_progress": self._is_conversation_in_progress(conversation),
                },
            )

            if self._is_conversation_in_progress(conversation):
                formatted_message = {
                    "text": message_text,
                    "source": message_data.get("source", "outgoing"),
                    "created_at": event.timestamp.isoformat()
                    if hasattr(event.timestamp, "isoformat")
                    else str(event.timestamp),
                }

                self.dynamo_repository.storage_message(
                    project_uuid=event.project_uuid,
                    contact_urn=event.contact_urn,
                    message_data=formatted_message,
                    channel_uuid=event.channel_uuid,
                    resolution_status=ResolutionEntities.IN_PROGRESS,
                    ttl_hours=48,
                )

                logger.debug(
                    "[MessageRepository] Message saved to DynamoDB",
                    extra={"conversation_uuid": str(conversation.uuid)},
                )
            else:
                logger.debug(
                    "[MessageRepository] Conversation not in progress, skipping DynamoDB save",
                    extra={"conversation_uuid": str(conversation.uuid), "resolution": conversation.resolution},
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

    def get_messages_from_dynamo(self, project_uuid: str, contact_urn: str, channel_uuid: str = None) -> list:
        try:
            response = self.dynamo_repository.get_messages(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid,
                limit=1000,
            )
            return response.get("items", [])
        except Exception as e:
            logger.error(
                "[MessageRepository] Error getting messages from DynamoDB",
                extra={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
