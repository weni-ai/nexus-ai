import logging

import sentry_sdk

from conversation_ms.repositories.message_repository import MessageRepository
from nexus.intelligences.models import ConversationMessages

logger = logging.getLogger(__name__)


class MessageMigrationService:
    def __init__(self):
        self.message_repository = MessageRepository()

    def migrate_conversation_messages_to_postgres(self, conversation):
        """
        Migrate messages from DynamoDB to PostgreSQL ConversationMessages table.
        This should be called when a conversation is closed.
        """
        try:
            logger.info(
                "[MessageMigrationService] Starting migration for conversation",
                extra={"conversation_uuid": str(conversation.uuid)},
            )

            messages = self.message_repository.get_messages_from_dynamo(
                project_uuid=str(conversation.project.uuid),
                contact_urn=conversation.contact_urn,
                channel_uuid=str(conversation.channel_uuid) if conversation.channel_uuid else None,
            )

            if not messages:
                logger.info(
                    "[MessageMigrationService] No messages to migrate",
                    extra={"conversation_uuid": str(conversation.uuid)},
                )
                return

            formatted_messages = []
            for msg in messages:
                formatted_messages.append(
                    {
                        "text": msg.get("text", ""),
                        "source": msg.get("source", ""),
                        "created_at": msg.get("created_at", ""),
                    }
                )

            conversation_messages, created = ConversationMessages.objects.update_or_create(
                conversation=conversation,
                defaults={"messages": formatted_messages},
            )

            logger.info(
                "[MessageMigrationService] Migration completed",
                extra={
                    "conversation_uuid": str(conversation.uuid),
                    "messages_count": len(formatted_messages),
                    "created": created,
                },
            )

        except Exception as e:
            sentry_sdk.set_tag("conversation_uuid", str(conversation.uuid))
            sentry_sdk.set_context(
                "message_migration",
                {
                    "conversation_uuid": str(conversation.uuid),
                    "project_uuid": str(conversation.project.uuid),
                    "contact_urn": conversation.contact_urn,
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[MessageMigrationService] Error migrating messages",
                extra={
                    "conversation_uuid": str(conversation.uuid),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
