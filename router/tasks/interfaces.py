from enum import Enum

from abc import ABC, abstractmethod

from typing import Optional


class TaskManagerBackend(Enum):
    REDIS = "redis"
    DYNAMO = "dynamo"


class InlineAgentTaskManager(ABC):
    """Interface for inline agent task management operations following ISP."""

    @abstractmethod
    def get_pending_task_id(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact."""
        pass

    @abstractmethod
    def store_pending_task_id(
        self, project_uuid: str, contact_urn: str, task_id: str
    ) -> None:
        """Store a pending task ID for a contact."""
        pass

    @abstractmethod
    def clear_pending_tasks(self, project_uuid: str, contact_urn: str) -> None:
        """Clear all pending tasks for a contact."""
        pass

    @abstractmethod
    def handle_pending_response(
        self, project_uuid: str, contact_urn: str, message_text: str
    ) -> str:
        """Handle pending response and return final message text."""
        pass
