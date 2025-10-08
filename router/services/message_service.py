import pendulum

from django.conf import settings
from router.repositories import Repository
from router.services.conversation_service import ConversationService


class MessageService:
    """Message service implementation that works with any message repository."""

    def __init__(self, message_repository: Repository = None):
        if message_repository is None:
            from router.repositories.dynamo.message import MessageRepository as DynamoMessageRepository
            message_repository = DynamoMessageRepository()

        self.message_repository = message_repository
        self.conversation_service = ConversationService()

    def handle_message_cache(
        self,
        contact_urn: str,
        contact_name: str,
        project_uuid: str,
        msg_text: str,
        source: str,
        channel_uuid: str,
        preview: bool = False
    ) -> None:
        """Handle message cache logic - matches original RedisTaskManager.handle_message_cache."""
        if project_uuid not in settings.CUSTOM_LAMBDA_CONVERSATION_PROJECTS:
            return

        if preview:
            return

        current_conversation_response = self.message_repository.get_messages(project_uuid, contact_urn, channel_uuid, limit=1)
        current_conversation = current_conversation_response.get('items', [])
        if current_conversation:
            self.add_message_to_cache(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                msg_text=msg_text,
                source=source,
                channel_uuid=channel_uuid,
                contact_name=contact_name
            )
        else:
            self.create_message_to_cache(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                contact_name=contact_name,
                msg_text=msg_text,
                source=source,
                channel_uuid=channel_uuid
            )

    def create_message_to_cache(
        self,
        msg_text: str,
        contact_urn: str,
        contact_name: str,
        project_uuid: str,
        source: str,
        channel_uuid: str = None,
        ttl_hours: int = 48
    ) -> None:
        """Create a new message and store it with TTL - matches original create_message_to_cache logic."""
        message_data = {
            "text": msg_text,
            "source": source,
            "created_at": self._get_current_timestamp()
        }
        self.message_repository.storage_message(project_uuid, contact_urn, message_data, channel_uuid, ttl_hours)

        # Create conversation only if channel_uuid is not None
        self.conversation_service.create_conversation_if_channel_exists(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid
        )

    def add_message_to_cache(
        self,
        project_uuid: str,
        contact_urn: str,
        msg_text: str,
        source: str,
        channel_uuid: str = None,
        contact_name: str = None
    ) -> None:
        """Add a message to existing conversation - matches original add_message_to_cache logic."""
        message = {
            "text": msg_text,
            "source": source,
            "created_at": self._get_current_timestamp()
        }
        self.message_repository.add_message(project_uuid, contact_urn, message, channel_uuid)

        # Ensure conversation exists only if channel_uuid is not None
        self.conversation_service.ensure_conversation_exists(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid
        )

    def get_cache_messages(self, project_uuid: str, contact_urn: str, channel_uuid: str, limit: int = 50, cursor: str = None) -> dict:
        """Get messages from cache with pagination - optimized for large datasets."""
        return self.message_repository.get_messages(project_uuid, contact_urn, channel_uuid, limit, cursor)

    def clear_message_cache(self, project_uuid: str, contact_urn: str, channel_uuid: str = None) -> None:
        """Clear message cache - matches original clear_message_cache logic."""
        self.message_repository.delete_messages(project_uuid, contact_urn, channel_uuid)

    def rabbitmq_msg_batch_to_cache(
        self,
        project_uuid: str,
        contact_urn: str,
        messages: list,
        key: str,
        channel_uuid: str = None
    ) -> None:
        """Store a batch of messages in cache - matches original rabbitmq_msg_batch_to_cache logic."""
        self.message_repository.store_batch_messages(project_uuid, contact_urn, messages, key, channel_uuid)

    def get_messages_for_conversation(
        self, project_uuid: str, contact_urn: str, channel_uuid: str,
        start_date: str = None, end_date: str = None, resolution_status: int = None
    ) -> list:
        """Get messages for a specific conversation, optionally filtered by time range and resolution."""
        return self.message_repository.get_messages_for_conversation(
            project_uuid, contact_urn, channel_uuid, start_date, end_date, resolution_status
        )

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return pendulum.now().to_iso8601_string()
