from abc import ABC, abstractmethod
from typing import Optional
from redis import Redis
from django.conf import settings


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
    CACHE_TIMEOUT = 300  # 5 minutes in seconds

    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis_client = redis_client or Redis.from_url(settings.REDIS_URL)

    def get_pending_response(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending response for a contact."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        pending_response = self.redis_client.get(pending_response_key)
        return pending_response.decode('utf-8') if pending_response else None

    def get_pending_task_id(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact."""
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        pending_task_id = self.redis_client.get(pending_task_key)
        return pending_task_id.decode('utf-8') if pending_task_id else None

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

    def get_rationale_session_data(self, session_id: str) -> dict:
        """Get or create rationale session data from cache."""
        cache_key = f"rationale_session_{session_id}"
        session_data = self.redis_client.get(cache_key)

        if session_data is None:
            session_data = {
                'rationale_history': [],
                'first_rationale_text': None,
                'is_first_rationale': True
            }
            self.save_rationale_session_data(session_id, session_data)
        else:
            session_data = eval(session_data.decode('utf-8'))

        return session_data

    def save_rationale_session_data(self, session_id: str, session_data: dict) -> None:
        """Save rationale session data to cache."""
        cache_key = f"rationale_session_{session_id}"
        self.redis_client.setex(
            cache_key,
            self.CACHE_TIMEOUT,
            str(session_data)
        )
