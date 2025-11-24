import json
from abc import ABC, abstractmethod
from typing import Optional

import pendulum
from django.conf import settings
from redis import Redis

from router.repositories.redis.message import MessageRepository as RedisMessageRepository


class TaskManager(ABC):
    """Abstract base class for task management."""

    @abstractmethod
    def get_pending_response(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending response for a contact."""
        pass

    @abstractmethod
    def get_pending_task_id(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact."""
        pass

    @abstractmethod
    def store_pending_response(self, project_uuid: str, contact_urn: str, message_text: str) -> None:
        """Store a pending response for a contact."""
        pass

    @abstractmethod
    def store_pending_task_id(self, project_uuid: str, contact_urn: str, task_id: str) -> None:
        """Store a pending task ID for a contact."""
        pass

    @abstractmethod
    def clear_pending_tasks(self, project_uuid: str, contact_urn: str) -> None:
        """Clear all pending tasks for a contact."""
        pass

    @abstractmethod
    def handle_pending_response(self, project_uuid: str, contact_urn: str, message_text: str) -> str:
        """Handle pending response and return final message text."""
        pass


class RedisTaskManager(TaskManager):
    """Redis-specific task manager with repository-agnostic message cache methods."""

    CACHE_TIMEOUT = 300  # 5 minutes in seconds

    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis_client = redis_client or Redis.from_url(settings.REDIS_URL)
        self.message_repository = RedisMessageRepository(self.redis_client)
        self._conversation_service = None

    def get_pending_response(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending response for a contact."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        pending_response = self.redis_client.get(pending_response_key)
        return pending_response.decode("utf-8") if pending_response else None

    def get_pending_task_id(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact."""
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        pending_task_id = self.redis_client.get(pending_task_key)
        return pending_task_id.decode("utf-8") if pending_task_id else None

    def store_pending_response(self, project_uuid: str, contact_urn: str, message_text: str) -> None:
        """Store a pending response for a contact."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        self.redis_client.set(pending_response_key, message_text)

    def store_pending_task_id(self, project_uuid: str, contact_urn: str, task_id: str) -> None:
        """Store a pending task ID for a contact."""
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        self.redis_client.set(pending_task_key, task_id)

    def clear_pending_tasks(self, project_uuid: str, contact_urn: str) -> None:
        """Clear all pending tasks for a contact."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        self.redis_client.delete(pending_response_key)
        self.redis_client.delete(pending_task_key)

    def handle_pending_response(self, project_uuid: str, contact_urn: str, message_text: str) -> str:
        """
        Handle pending response by either concatenating with existing response
        or storing new response.
        Returns the final message text to be processed.
        """
        pending_response = self.get_pending_response(project_uuid, contact_urn)

        if pending_response:
            # Concatenate the previous message with the new one
            final_message = f"{pending_response}\n{message_text}"
            self.clear_pending_tasks(project_uuid, contact_urn)
        else:
            # Store the current message
            final_message = message_text
            self.store_pending_response(project_uuid, contact_urn, message_text)

        return final_message

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return pendulum.now().to_iso8601_string()

    def get_rationale_session_data(self, session_id: str) -> dict:
        """Get or create rationale session data from cache."""
        cache_key = f"rationale_session_{session_id}"
        session_data = self.redis_client.get(cache_key)

        if session_data is None:
            session_data = {"rationale_history": [], "first_rationale_text": None, "is_first_rationale": True}
            self.save_rationale_session_data(session_id, session_data)
        else:
            session_data = json.loads(session_data.decode("utf-8"))

        return session_data

    def save_rationale_session_data(self, session_id: str, session_data: dict) -> None:
        """Save rationale session data to cache."""
        cache_key = f"rationale_session_{session_id}"
        self.redis_client.setex(cache_key, self.CACHE_TIMEOUT, json.dumps(session_data))

    def create_message_to_cache(
        self,
        msg_text: str,
        contact_urn: str,
        contact_name: str,
        project_uuid: str,
        source: str,
        channel_uuid: str = None,
    ) -> None:
        # Store the message using the repository
        message_data = {"text": msg_text, "source": source, "created_at": self._get_current_timestamp()}
        self.message_repository.storage_message(project_uuid, contact_urn, message_data)

        # Create conversation only if channel_uuid is not None
        self._get_conversation_service().create_conversation_if_channel_exists(
            project_uuid=project_uuid, contact_urn=contact_urn, contact_name=contact_name, channel_uuid=channel_uuid
        )

    def get_cache_messages(self, project_uuid: str, contact_urn: str) -> list:
        """Get messages from cache"""
        return self.message_repository.get_messages(project_uuid, contact_urn)

    def add_message_to_cache(
        self,
        project_uuid: str,
        contact_urn: str,
        msg_text: str,
        source: str,
        channel_uuid: str = None,
        contact_name: str = None,
    ) -> None:
        # Add the message using the repository (matches original add_message_to_cache logic)
        message = {"text": msg_text, "source": source, "created_at": self._get_current_timestamp()}
        self.message_repository.add_message(project_uuid, contact_urn, message)

        # Ensure conversation exists only if channel_uuid is not None
        self._get_conversation_service().ensure_conversation_exists(
            project_uuid=project_uuid, contact_urn=contact_urn, contact_name=contact_name, channel_uuid=channel_uuid
        )

    def handle_message_cache(
        self,
        contact_urn: str,
        contact_name: str,
        project_uuid: str,
        msg_text: str,
        source: str,
        channel_uuid: str = None,
        preview: bool = False,
    ) -> None:
        """Handle message cache logic - stores message in cache."""
        if preview:
            return

        if channel_uuid is None:
            import logging

            logging.getLogger(__name__).info(
                "Skipping message cache: channel_uuid is None", extra={"contact_urn": contact_urn}
            )
            return

        # Check if there are existing cached messages to decide storage method
        cached_messages = self.get_cache_messages(project_uuid, contact_urn)
        if cached_messages:
            self.add_message_to_cache(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                msg_text=msg_text,
                source=source,
                channel_uuid=channel_uuid,
                contact_name=contact_name,
            )
        else:
            self.create_message_to_cache(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                contact_name=contact_name,
                msg_text=msg_text,
                source=source,
                channel_uuid=channel_uuid,
            )

    def clear_message_cache(self, project_uuid: str, contact_urn: str) -> None:
        """Clear message cache"""
        self.message_repository.delete_messages(project_uuid, contact_urn)

    def rabbitmq_msg_batch_to_cache(self, project_uuid: str, contact_urn: str, messages: list, key: str) -> None:
        """
        Store a batch of messages in cache.
        """
        self.message_repository.store_batch_messages(project_uuid, contact_urn, messages, key)

    def _get_conversation_service(self):
        """Get conversation service instance, creating it if it doesn't exist."""
        if self._conversation_service is None:
            from router.services.conversation_service import ConversationService

            self._conversation_service = ConversationService()
        return self._conversation_service
