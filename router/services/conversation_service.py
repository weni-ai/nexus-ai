from typing import Optional
from nexus.usecases.intelligences.create import ConversationUseCase
from nexus.intelligences.models import Conversation
from router.repositories.entities import ResolutionEntities


class ConversationService:
    """Service class to handle conversation operations."""

    def __init__(self):
        self.conversation_usecase = ConversationUseCase()

    def create_conversation_if_channel_exists(
        self,
        project_uuid: str,
        contact_urn: str,
        contact_name: str,
        channel_uuid: str = None
    ) -> Optional[object]:
        """
        Create a conversation only if channel_uuid is not None.
        Returns the conversation object if created, None otherwise.
        """
        if channel_uuid is None:
            # Temp fix for conversations from flows.
            return None

        return self.conversation_usecase.create_conversation_base_structure(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid
        )

    def ensure_conversation_exists(
        self,
        project_uuid: str,
        contact_urn: str,
        contact_name: str,
        channel_uuid: str = None
    ) -> bool:
        """
        Ensure conversation exists only if channel_uuid is not None.
        Returns True if conversation exists or was created, False if channel_uuid is None.
        """
        if channel_uuid is None:
            # Temp fix for conversations from flows.
            return False

        return self.conversation_usecase.conversation_in_progress_exists(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            contact_name=contact_name
        )

    def get_or_create_conversation(self, project_uuid, contact_urn, external_id, channel_uuid=None, contact_name=None):
        if not external_id:
            # Or handle this error more gracefully, but we need the ID
            raise ValueError("external_id is required to get or create a conversation")

        obj, created = Conversation.objects.get_or_create(
            project_id=project_uuid,
            external_id=external_id,
            defaults={
                'contact_urn': contact_urn,
                'contact_name': contact_name,
                'channel_uuid': channel_uuid,
                'resolution': ResolutionEntities.IN_PROGRESS  # Set default resolution
            }
        )
        
        return obj