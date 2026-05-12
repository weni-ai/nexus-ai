import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import pendulum
from redis import Redis

from router.repositories.redis.message import MessageRepository as RedisMessageRepository

logger = logging.getLogger(__name__)


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
    WORKFLOW_CACHE_TIMEOUT = 600  # 10 minutes for workflow state

    def __init__(self, redis_client: Optional[Redis] = None):
        if redis_client:
            self._read_client = redis_client
            self._write_client = redis_client
        else:
            from router.utils.redis_clients import get_redis_read_client, get_redis_write_client

            self._read_client = get_redis_read_client()
            self._write_client = get_redis_write_client()
        self.redis_client = self._write_client
        self.message_repository = RedisMessageRepository(self.redis_client)
        self._conversation_service = None

    # ==================== Workflow State Management ====================

    def get_workflow_state(self, project_uuid: str, contact_urn: str) -> Optional[Dict]:
        """
        Get current workflow state for a contact - uses read replica if available.

        Args:
            project_uuid: Project UUID
            contact_urn: Contact URN

        Returns:
            Workflow state dict or None if not found
        """
        workflow_key = f"workflow:{project_uuid}:{contact_urn}"
        state = self._read_client.get(workflow_key)
        if state:
            return json.loads(state.decode("utf-8"))
        return None

    def store_workflow_state(self, workflow_state: Dict) -> None:
        """
        Store workflow state in Redis.

        Args:
            workflow_state: Workflow state dict containing project_uuid, contact_urn, etc.
        """
        workflow_key = f"workflow:{workflow_state['project_uuid']}:{workflow_state['contact_urn']}"
        self._write_client.setex(workflow_key, self.WORKFLOW_CACHE_TIMEOUT, json.dumps(workflow_state, default=str))

    def update_workflow_status(
        self, project_uuid: str, contact_urn: str, status: str, task_phase: str = None, task_id: str = None
    ) -> bool:
        """
        Update workflow status and optionally task ID.

        Args:
            project_uuid: Project UUID
            contact_urn: Contact URN
            status: New status (e.g., "pre_generation", "generation", "completed", "failed")
            task_phase: Task phase to update (e.g., "pre_generation", "generation")
            task_id: Task ID to store for the phase

        Returns:
            True if updated, False if workflow not found
        """
        workflow_state = self.get_workflow_state(project_uuid, contact_urn)
        if workflow_state:
            workflow_state["status"] = status
            workflow_state["updated_at"] = pendulum.now().to_iso8601_string()
            if task_phase and task_id:
                workflow_state["task_ids"][task_phase] = task_id
            self.store_workflow_state(workflow_state)
            return True
        return False

    def revoke_workflow_tasks(self, workflow_state: Dict, exclude_task_id: Optional[str] = None) -> List[str]:
        """
        Revoke all tasks in a workflow.

        Args:
            workflow_state: Workflow state dict
            exclude_task_id: Task ID to exclude from revocation (e.g., current task on retry)

        Returns:
            List of revoked task IDs
        """
        from nexus.celery import app as celery_app

        revoked = []
        task_ids = workflow_state.get("task_ids", {})

        for phase, task_id in task_ids.items():
            if task_id and task_id != exclude_task_id:
                try:
                    celery_app.control.revoke(task_id, terminate=True)
                    revoked.append(task_id)
                    logger.info(f"[Workflow] Revoked task {task_id} (phase: {phase})")
                except Exception as e:
                    logger.warning(f"[Workflow] Failed to revoke task {task_id}: {e}")

        return revoked

    def clear_workflow_state(self, project_uuid: str, contact_urn: str) -> None:
        """
        Clear workflow state for a contact.

        Also clears old single-task keys for backwards compatibility.

        Args:
            project_uuid: Project UUID
            contact_urn: Contact URN
        """
        workflow_key = f"workflow:{project_uuid}:{contact_urn}"
        self._write_client.delete(workflow_key)
        # Also clear old single-task keys for backwards compatibility
        self.clear_pending_tasks(project_uuid, contact_urn)

    def create_workflow_state(
        self,
        workflow_id: str,
        project_uuid: str,
        contact_urn: str,
        message_text: str,
    ) -> Dict:
        """
        Create a new workflow state.

        Args:
            workflow_id: Unique workflow ID
            project_uuid: Project UUID
            contact_urn: Contact URN
            message_text: Final message text (after concatenation)

        Returns:
            Created workflow state dict
        """
        workflow_state = {
            "workflow_id": workflow_id,
            "project_uuid": project_uuid,
            "contact_urn": contact_urn,
            "status": "created",
            "task_ids": {
                "pre_generation": None,
                "generation": None,
                "post_generation": None,
            },
            "created_at": pendulum.now().to_iso8601_string(),
            "updated_at": pendulum.now().to_iso8601_string(),
            "final_message_text": message_text,
        }
        self.store_workflow_state(workflow_state)
        logger.info(f"[Workflow] Created workflow {workflow_id} for project {project_uuid}")
        return workflow_state

    def handle_workflow_message_concatenation(
        self, project_uuid: str, contact_urn: str, new_message_text: str, current_task_id: Optional[str] = None
    ) -> Tuple[str, bool]:
        """
        Handle message concatenation for workflows.

        If an existing workflow exists:
        - Revoke all its tasks (except the current one, to support retries)
        - Concatenate pending message with new message
        - Clear old workflow state

        Also handles backwards compatibility with old single-task format.

        Args:
            project_uuid: Project UUID
            contact_urn: Contact URN
            new_message_text: New message text
            current_task_id: Current task ID (to avoid revoking self on retry)

        Returns:
            Tuple of (final_message_text, had_existing_workflow)
        """
        from nexus.celery import app as celery_app

        workflow_state = self.get_workflow_state(project_uuid, contact_urn)

        if workflow_state:
            # Revoke existing workflow tasks, excluding current task (for retry support)
            revoked = self.revoke_workflow_tasks(workflow_state, exclude_task_id=current_task_id)
            if revoked:
                logger.info(f"[Workflow] Revoked {len(revoked)} tasks for {contact_urn}")

            # Get pending message from workflow state
            pending_text = workflow_state.get("final_message_text", "")
            if pending_text and pending_text != new_message_text:
                final_message = f"{pending_text}\n{new_message_text}"
            else:
                final_message = new_message_text

            # Clear old workflow state
            self.clear_workflow_state(project_uuid, contact_urn)
            return final_message, True
        else:
            # Check old single-task format for backwards compatibility
            pending_response = self.get_pending_response(project_uuid, contact_urn)
            pending_task_id = self.get_pending_task_id(project_uuid, contact_urn)

            # Only revoke if it's a different task (not a retry of the same task)
            if pending_task_id and pending_task_id != current_task_id:
                try:
                    celery_app.control.revoke(pending_task_id, terminate=True)
                    logger.info(f"[Workflow] Revoked legacy task {pending_task_id}")
                except Exception as e:
                    logger.warning(f"[Workflow] Failed to revoke legacy task: {e}")

            if pending_response:
                final_message = f"{pending_response}\n{new_message_text}"
                self.clear_pending_tasks(project_uuid, contact_urn)
                return final_message, True
            else:
                return new_message_text, False

    # ==================== Legacy Pending Task Methods ====================

    def get_pending_response(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending response for a contact - uses read replica if available."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        pending_response = self._read_client.get(pending_response_key)
        return pending_response.decode("utf-8") if pending_response else None

    def get_pending_task_id(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact - uses read replica if available."""
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        pending_task_id = self._read_client.get(pending_task_key)
        return pending_task_id.decode("utf-8") if pending_task_id else None

    def store_pending_response(self, project_uuid: str, contact_urn: str, message_text: str) -> None:
        """Store a pending response for a contact - uses primary."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        self._write_client.set(pending_response_key, message_text)

    def store_pending_task_id(self, project_uuid: str, contact_urn: str, task_id: str) -> None:
        """Store a pending task ID for a contact - uses primary."""
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        self._write_client.set(pending_task_key, task_id)

    def clear_pending_tasks(self, project_uuid: str, contact_urn: str) -> None:
        """Clear all pending tasks for a contact - uses primary."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        self._write_client.delete(pending_response_key)
        self._write_client.delete(pending_task_key)

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
        """Get or create rationale session data from cache - uses read replica if available."""
        cache_key = f"rationale_session_{session_id}"
        session_data = self._read_client.get(cache_key)

        if session_data is None:
            session_data = {"rationale_history": [], "first_rationale_text": None, "is_first_rationale": True}
            self.save_rationale_session_data(session_id, session_data)
        else:
            session_data = json.loads(session_data.decode("utf-8"))

        return session_data

    def save_rationale_session_data(self, session_id: str, session_data: dict) -> None:
        """Save rationale session data to cache - uses primary."""
        cache_key = f"rationale_session_{session_id}"
        self._write_client.setex(cache_key, self.CACHE_TIMEOUT, json.dumps(session_data))

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
            logger.info("Skipping message cache: channel_uuid is None", extra={"contact_urn": contact_urn})
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
