from typing import Optional

import sentry_sdk

from nexus.usecases.intelligences.create import ConversationUseCase


class ConversationService:
    """Service class to handle conversation operations."""

    def __init__(self):
        self.conversation_usecase = ConversationUseCase()

    def create_conversation_if_channel_exists(
        self, project_uuid: str, contact_urn: str, contact_name: str, channel_uuid: str = None
    ) -> Optional[object]:
        """
        Create a conversation only if channel_uuid is not None.
        Returns the conversation object if created, None otherwise.
        """
        if channel_uuid is None:
            # Log to Sentry for debugging (expected but we want to track it)
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_context(
                "conversation_creation",
                {
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "contact_name": contact_name,
                    "channel_uuid": None,
                    "method": "create_conversation_if_channel_exists",
                    "reason": "channel_uuid is None",
                },
            )
            sentry_sdk.capture_message(
                "Conversation not created: channel_uuid is None (create_conversation_if_channel_exists)", level="info"
            )
            return None

        return self.conversation_usecase.create_conversation_base_structure(
            project_uuid=project_uuid, contact_urn=contact_urn, contact_name=contact_name, channel_uuid=channel_uuid
        )

    def ensure_conversation_exists(
        self,
        project_uuid: str,
        contact_urn: str,
        contact_name: str,
        channel_uuid: str = None,
    ) -> Optional[object]:
        """
        Ensure conversation exists only if channel_uuid is not None.
        Returns the conversation object if it exists or was created, None if channel_uuid is None.
        """
        if channel_uuid is None:
            # Log to Sentry for debugging (expected but we want to track it)
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
                "Conversation not created: channel_uuid is None (ensure_conversation_exists)", level="info"
            )
            return None

        try:
            return self.conversation_usecase.conversation_in_progress_exists(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid,
                contact_name=contact_name,
            )
        except Exception as e:
            # Log conversation creation/lookup failures to Sentry
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
            raise
