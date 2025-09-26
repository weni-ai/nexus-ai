import pendulum

import logging

from typing import Optional

from router.repositories.dynamo.message import MessageRepository
from router.tasks.interfaces import InlineAgentTaskManager

logger = logging.getLogger(__name__)


class DynamoTaskManager(InlineAgentTaskManager):
    """DynamoDB implementation of inline agent task management following ISP principle."""

    def __init__(self, message_repository: Optional[MessageRepository] = None):
        """Initialize DynamoTaskManager with dependency injection."""
        self.message_repository = message_repository or MessageRepository()

    def get_pending_task_id(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """
        Retrieve the most recent pending task ID for a contact from DynamoDB.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name

        Returns:
            Most recent task ID if found, None otherwise
        """
        try:
            latest_message = self.message_repository.get_latest_message_by_source(
                project_uuid, contact_urn, "task_id"
            )
            return latest_message.get("text") if latest_message else None
        except Exception as e:
            print(f"Error getting pending task ID: {e}")
            return None

    def store_pending_task_id(
        self, project_uuid: str, contact_urn: str, task_id: str
    ) -> None:
        """
        Store a pending task ID for a contact in DynamoDB.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name
            task_id: Task identifier to store

        Raises:
            Exception: If storage operation fails
        """
        try:
            message_data = {
                "text": task_id,
                "source": "task_id",
                "created_at": pendulum.now().isoformat(),
            }

            self.message_repository.storage_message(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                message_data=message_data,
            )
        except Exception as e:
            print(f"Error storing pending task ID: {e}")
            raise

    def clear_pending_tasks(self, project_uuid: str, contact_urn: str) -> None:
        """
        Clear all pending tasks for a contact by deleting pending messages and task IDs.

        This method provides immediate cleanup when needed, complementing the TTL strategy.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name
        """
        try:
            self.message_repository.delete_pending_tasks(project_uuid, contact_urn)
        except Exception as e:
            print(f"Error clearing pending tasks: {e}")

    def handle_pending_response(
        self, project_uuid: str, contact_urn: str, message_text: str
    ) -> str:
        """
        Handle pending response by concatenating with existing response or storing new one.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name
            message_text: New message text to process

        Returns:
            Final message text ready for processing
        """
        try:
            pending_response = self._get_pending_response(project_uuid, contact_urn)

            if pending_response:
                final_message = f"{pending_response}\n{message_text}"
                self.clear_pending_tasks(project_uuid, contact_urn)
            else:
                final_message = message_text
                self._store_pending_response(project_uuid, contact_urn, message_text)

            return final_message
        except Exception as e:
            print(f"Error handling pending response: {e}")
            return message_text

    def _get_pending_response(
        self, project_uuid: str, contact_urn: str
    ) -> Optional[str]:
        """
        Get the most recent pending response for a contact from DynamoDB.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name

        Returns:
            Most recent pending message text if found, None otherwise
        """
        try:
            latest_message = self.message_repository.get_latest_message_by_source(
                project_uuid, contact_urn, "pending"
            )
            return latest_message.get("text") if latest_message else None
        except Exception as e:
            print(f"Error getting pending response: {e}")
            return None

    def _store_pending_response(
        self, project_uuid: str, contact_urn: str, message_text: str
    ) -> None:
        """
        Store a pending response for a contact in DynamoDB.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name
            message_text: Message text to store as pending
        """
        try:
            message_data = {
                "text": message_text,
                "source": "pending",
                "created_at": pendulum.now().isoformat(),
            }

            self.message_repository.storage_message(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                message_data=message_data,
            )
        except Exception as e:
            print(f"Error storing pending response: {e}")
            raise
