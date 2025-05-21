from abc import ABC, abstractmethod
from typing import Optional
from redis import Redis
from django.conf import settings


class TaskManager(ABC):
    """Abstract base class for task management."""

    @abstractmethod
    def get_pending_response(self, contact_urn: str) -> Optional[str]:
        """Get the pending response for a contact."""
        pass

    @abstractmethod
    def get_pending_task_id(self, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact."""
        pass

    @abstractmethod
    def store_pending_response(self, contact_urn: str, message_text: str) -> None:
        """Store a pending response for a contact."""
        pass

    @abstractmethod
    def store_pending_task_id(self, contact_urn: str, task_id: str) -> None:
        """Store a pending task ID for a contact."""
        pass

    @abstractmethod
    def clear_pending_tasks(self, contact_urn: str) -> None:
        """Clear all pending tasks for a contact."""
        pass

    @abstractmethod
    def handle_pending_response(self, contact_urn: str, message_text: str) -> str:
        """Handle pending response and return final message text."""
        pass


class RedisTaskManager(TaskManager):
    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis_client = redis_client or Redis.from_url(settings.REDIS_URL)

    def get_pending_response(self, contact_urn: str) -> Optional[str]:
        """Get the pending response for a contact."""
        pending_response_key = f"response:{contact_urn}"
        pending_response = self.redis_client.get(pending_response_key)
        return pending_response.decode('utf-8') if pending_response else None

    def get_pending_task_id(self, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact."""
        pending_task_key = f"task:{contact_urn}"
        pending_task_id = self.redis_client.get(pending_task_key)
        return pending_task_id.decode('utf-8') if pending_task_id else None

    def store_pending_response(self, contact_urn: str, message_text: str) -> None:
        """Store a pending response for a contact."""
        pending_response_key = f"response:{contact_urn}"
        self.redis_client.set(pending_response_key, message_text)

    def store_pending_task_id(self, contact_urn: str, task_id: str) -> None:
        """Store a pending task ID for a contact."""
        pending_task_key = f"task:{contact_urn}"
        self.redis_client.set(pending_task_key, task_id)

    def clear_pending_tasks(self, contact_urn: str) -> None:
        """Clear all pending tasks for a contact."""
        pending_response_key = f"response:{contact_urn}"
        pending_task_key = f"task:{contact_urn}"
        self.redis_client.delete(pending_response_key)
        self.redis_client.delete(pending_task_key)

    def handle_pending_response(self, contact_urn: str, message_text: str) -> str:
        """
        Handle pending response by either concatenating with existing response
        or storing new response.
        Returns the final message text to be processed.
        """
        pending_response = self.get_pending_response(contact_urn)

        if pending_response:
            # Concatenate the previous message with the new one
            final_message = f"{pending_response}\n{message_text}"
            self.clear_pending_tasks(contact_urn)
        else:
            # Store the current message
            final_message = message_text
            self.store_pending_response(contact_urn, message_text)

        return final_message
