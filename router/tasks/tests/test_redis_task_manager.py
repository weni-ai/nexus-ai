import logging
from unittest.mock import patch

from django.test import TestCase

from router.tasks.redis_task_manager import RedisTaskManager


class MockRedisClient:
    """In-memory mock Redis client for testing."""

    def __init__(self):
        self.data = {}
        self.ttls = {}

    def get(self, key):
        value = self.data.get(key)
        if value is not None:
            return value.encode("utf-8") if isinstance(value, str) else value
        return None

    def set(self, key, value):
        self.data[key] = value if isinstance(value, str) else value.decode("utf-8")

    def setex(self, key, ttl, value):
        self.data[key] = value if isinstance(value, str) else value.decode("utf-8")
        self.ttls[key] = ttl

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
            self.ttls.pop(key, None)

    def clear(self):
        self.data.clear()
        self.ttls.clear()


class WorkflowStateTestCase(TestCase):
    """Tests for workflow state management methods."""

    def setUp(self):
        self.mock_redis = MockRedisClient()
        self.task_manager = RedisTaskManager(redis_client=self.mock_redis)
        self.project_uuid = "test-project-uuid"
        self.contact_urn = "tel:+5511999999999"
        self.workflow_id = "wf-12345"

    def test_create_workflow_state(self):
        """Test creating a new workflow state."""
        message_text = "Hello, world!"

        workflow_state = self.task_manager.create_workflow_state(
            workflow_id=self.workflow_id,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            message_text=message_text,
        )

        # Verify returned state
        self.assertEqual(workflow_state["workflow_id"], self.workflow_id)
        self.assertEqual(workflow_state["project_uuid"], self.project_uuid)
        self.assertEqual(workflow_state["contact_urn"], self.contact_urn)
        self.assertEqual(workflow_state["status"], "created")
        self.assertEqual(workflow_state["final_message_text"], message_text)
        self.assertIn("created_at", workflow_state)
        self.assertIn("updated_at", workflow_state)
        self.assertIsNone(workflow_state["task_ids"]["pre_generation"])
        self.assertIsNone(workflow_state["task_ids"]["generation"])
        self.assertIsNone(workflow_state["task_ids"]["post_generation"])

        # Verify stored in Redis
        workflow_key = f"workflow:{self.project_uuid}:{self.contact_urn}"
        self.assertIn(workflow_key, self.mock_redis.data)

    def test_get_workflow_state_exists(self):
        """Test retrieving an existing workflow state."""
        # Create a workflow state first
        self.task_manager.create_workflow_state(
            workflow_id=self.workflow_id,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            message_text="Test message",
        )

        # Retrieve it
        state = self.task_manager.get_workflow_state(self.project_uuid, self.contact_urn)

        self.assertIsNotNone(state)
        self.assertEqual(state["workflow_id"], self.workflow_id)
        self.assertEqual(state["project_uuid"], self.project_uuid)

    def test_get_workflow_state_not_exists(self):
        """Test retrieving a non-existent workflow state."""
        state = self.task_manager.get_workflow_state(self.project_uuid, self.contact_urn)
        self.assertIsNone(state)

    def test_store_workflow_state(self):
        """Test storing a workflow state directly."""
        workflow_state = {
            "workflow_id": self.workflow_id,
            "project_uuid": self.project_uuid,
            "contact_urn": self.contact_urn,
            "status": "processing",
            "task_ids": {"pre_generation": "task-1", "generation": None, "post_generation": None},
        }

        self.task_manager.store_workflow_state(workflow_state)

        # Verify stored
        workflow_key = f"workflow:{self.project_uuid}:{self.contact_urn}"
        self.assertIn(workflow_key, self.mock_redis.data)

        # Verify TTL was set
        self.assertEqual(self.mock_redis.ttls[workflow_key], RedisTaskManager.WORKFLOW_CACHE_TIMEOUT)

    def test_clear_workflow_state(self):
        """Test clearing a workflow state."""
        # Create a workflow state
        self.task_manager.create_workflow_state(
            workflow_id=self.workflow_id,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            message_text="Test",
        )

        # Clear it
        self.task_manager.clear_workflow_state(self.project_uuid, self.contact_urn)

        # Verify cleared
        state = self.task_manager.get_workflow_state(self.project_uuid, self.contact_urn)
        self.assertIsNone(state)


class WorkflowStatusUpdateTestCase(TestCase):
    """Tests for workflow status update method."""

    def setUp(self):
        self.mock_redis = MockRedisClient()
        self.task_manager = RedisTaskManager(redis_client=self.mock_redis)
        self.project_uuid = "test-project-uuid"
        self.contact_urn = "tel:+5511999999999"
        self.workflow_id = "wf-12345"

    def test_update_workflow_status_success(self):
        """Test updating workflow status successfully."""
        # Create workflow state
        self.task_manager.create_workflow_state(
            workflow_id=self.workflow_id,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            message_text="Test",
        )

        # Update status
        result = self.task_manager.update_workflow_status(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            status="pre_generation",
        )

        self.assertTrue(result)

        # Verify updated
        state = self.task_manager.get_workflow_state(self.project_uuid, self.contact_urn)
        self.assertEqual(state["status"], "pre_generation")

    def test_update_workflow_status_with_task_id(self):
        """Test updating workflow status with task phase and ID."""
        # Create workflow state
        self.task_manager.create_workflow_state(
            workflow_id=self.workflow_id,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            message_text="Test",
        )

        # Update with task ID
        task_id = "celery-task-123"
        result = self.task_manager.update_workflow_status(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            status="pre_generation",
            task_phase="pre_generation",
            task_id=task_id,
        )

        self.assertTrue(result)

        # Verify task ID stored
        state = self.task_manager.get_workflow_state(self.project_uuid, self.contact_urn)
        self.assertEqual(state["task_ids"]["pre_generation"], task_id)

    def test_update_workflow_status_not_found(self):
        """Test updating status when workflow doesn't exist."""
        result = self.task_manager.update_workflow_status(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            status="pre_generation",
        )

        self.assertFalse(result)


class WorkflowTaskRevocationTestCase(TestCase):
    """Tests for workflow task revocation method."""

    def setUp(self):
        self.mock_redis = MockRedisClient()
        self.task_manager = RedisTaskManager(redis_client=self.mock_redis)

    @patch("nexus.celery.app")
    def test_revoke_workflow_tasks(self, mock_celery_app):
        """Test revoking all tasks in a workflow."""
        workflow_state = {
            "workflow_id": "wf-123",
            "project_uuid": "test-project",
            "contact_urn": "tel:+5511999999999",
            "task_ids": {
                "pre_generation": "task-1",
                "generation": "task-2",
                "post_generation": None,  # Not started yet
            },
        }

        revoked = self.task_manager.revoke_workflow_tasks(workflow_state)

        # Should have revoked 2 tasks (not None ones)
        self.assertEqual(len(revoked), 2)
        self.assertIn("task-1", revoked)
        self.assertIn("task-2", revoked)

        # Verify Celery control was called
        self.assertEqual(mock_celery_app.control.revoke.call_count, 2)
        mock_celery_app.control.revoke.assert_any_call("task-1", terminate=True)
        mock_celery_app.control.revoke.assert_any_call("task-2", terminate=True)

    @patch("nexus.celery.app")
    def test_revoke_workflow_tasks_empty(self, mock_celery_app):
        """Test revoking tasks when none exist."""
        workflow_state = {
            "workflow_id": "wf-123",
            "task_ids": {
                "pre_generation": None,
                "generation": None,
                "post_generation": None,
            },
        }

        revoked = self.task_manager.revoke_workflow_tasks(workflow_state)

        self.assertEqual(len(revoked), 0)
        mock_celery_app.control.revoke.assert_not_called()

    @patch("nexus.celery.app")
    def test_revoke_workflow_tasks_handles_errors(self, mock_celery_app):
        """Test that revocation continues even if some tasks fail."""
        # First call succeeds, second raises exception
        mock_celery_app.control.revoke.side_effect = [None, Exception("Connection error")]

        workflow_state = {
            "workflow_id": "wf-123",
            "task_ids": {
                "pre_generation": "task-1",
                "generation": "task-2",
                "post_generation": None,
            },
        }

        # Suppress expected error logs
        logging.disable(logging.CRITICAL)
        try:
            revoked = self.task_manager.revoke_workflow_tasks(workflow_state)
        finally:
            logging.disable(logging.NOTSET)

        # Only first one should be in revoked list
        self.assertEqual(len(revoked), 1)
        self.assertIn("task-1", revoked)


class WorkflowMessageConcatenationTestCase(TestCase):
    """Tests for workflow message concatenation."""

    def setUp(self):
        self.mock_redis = MockRedisClient()
        self.task_manager = RedisTaskManager(redis_client=self.mock_redis)
        self.project_uuid = "test-project-uuid"
        self.contact_urn = "tel:+5511999999999"

    @patch("nexus.celery.app")
    def test_concatenation_with_existing_workflow(self, mock_celery_app):
        """Test message concatenation when workflow exists."""
        # Create existing workflow with a message
        self.task_manager.create_workflow_state(
            workflow_id="wf-old",
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            message_text="First message",
        )

        # Update with a task ID to test revocation
        self.task_manager.update_workflow_status(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            status="generation",
            task_phase="generation",
            task_id="old-task-id",
        )

        # Handle new message
        final_message, had_existing = self.task_manager.handle_workflow_message_concatenation(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            new_message_text="Second message",
        )

        # Verify concatenation
        self.assertTrue(had_existing)
        self.assertEqual(final_message, "First message\nSecond message")

        # Verify old workflow was cleared
        state = self.task_manager.get_workflow_state(self.project_uuid, self.contact_urn)
        self.assertIsNone(state)

        # Verify task was revoked
        mock_celery_app.control.revoke.assert_called()

    @patch("nexus.celery.app")
    def test_concatenation_no_existing_workflow(self, mock_celery_app):
        """Test message concatenation when no workflow exists."""
        final_message, had_existing = self.task_manager.handle_workflow_message_concatenation(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            new_message_text="New message",
        )

        self.assertFalse(had_existing)
        self.assertEqual(final_message, "New message")

        # No revocation should happen
        mock_celery_app.control.revoke.assert_not_called()

    @patch("nexus.celery.app")
    def test_concatenation_same_message(self, mock_celery_app):
        """Test that same message doesn't get duplicated."""
        message = "Same message"

        # Create workflow with message
        self.task_manager.create_workflow_state(
            workflow_id="wf-123",
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            message_text=message,
        )

        # Handle same message again
        final_message, had_existing = self.task_manager.handle_workflow_message_concatenation(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            new_message_text=message,
        )

        # Should not duplicate
        self.assertTrue(had_existing)
        self.assertEqual(final_message, message)

    @patch("nexus.celery.app")
    def test_concatenation_backwards_compatibility_legacy_format(self, mock_celery_app):
        """Test concatenation with legacy single-task format."""
        # Store using legacy format
        self.task_manager.store_pending_response(self.project_uuid, self.contact_urn, "Legacy message")
        self.task_manager.store_pending_task_id(self.project_uuid, self.contact_urn, "legacy-task-id")

        # Handle new message
        final_message, had_existing = self.task_manager.handle_workflow_message_concatenation(
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            new_message_text="New message",
        )

        # Should concatenate with legacy message
        self.assertTrue(had_existing)
        self.assertEqual(final_message, "Legacy message\nNew message")

        # Legacy task should be revoked
        mock_celery_app.control.revoke.assert_called_with("legacy-task-id", terminate=True)


class LegacyPendingTasksTestCase(TestCase):
    """Tests for backwards-compatible legacy pending task methods."""

    def setUp(self):
        self.mock_redis = MockRedisClient()
        self.task_manager = RedisTaskManager(redis_client=self.mock_redis)
        self.project_uuid = "test-project"
        self.contact_urn = "tel:+5511999999999"

    def test_store_and_get_pending_response(self):
        """Test storing and retrieving pending response."""
        message = "Test pending message"

        self.task_manager.store_pending_response(self.project_uuid, self.contact_urn, message)
        result = self.task_manager.get_pending_response(self.project_uuid, self.contact_urn)

        self.assertEqual(result, message)

    def test_store_and_get_pending_task_id(self):
        """Test storing and retrieving pending task ID."""
        task_id = "celery-task-abc123"

        self.task_manager.store_pending_task_id(self.project_uuid, self.contact_urn, task_id)
        result = self.task_manager.get_pending_task_id(self.project_uuid, self.contact_urn)

        self.assertEqual(result, task_id)

    def test_get_pending_response_not_exists(self):
        """Test getting pending response when none exists."""
        result = self.task_manager.get_pending_response(self.project_uuid, self.contact_urn)
        self.assertIsNone(result)

    def test_clear_pending_tasks(self):
        """Test clearing pending tasks."""
        self.task_manager.store_pending_response(self.project_uuid, self.contact_urn, "Message")
        self.task_manager.store_pending_task_id(self.project_uuid, self.contact_urn, "task-123")

        self.task_manager.clear_pending_tasks(self.project_uuid, self.contact_urn)

        self.assertIsNone(self.task_manager.get_pending_response(self.project_uuid, self.contact_urn))
        self.assertIsNone(self.task_manager.get_pending_task_id(self.project_uuid, self.contact_urn))

    def test_handle_pending_response_no_existing(self):
        """Test handle_pending_response when no existing message."""
        message = "New message"

        result = self.task_manager.handle_pending_response(self.project_uuid, self.contact_urn, message)

        self.assertEqual(result, message)
        # Should store the message
        stored = self.task_manager.get_pending_response(self.project_uuid, self.contact_urn)
        self.assertEqual(stored, message)

    def test_handle_pending_response_with_existing(self):
        """Test handle_pending_response concatenates with existing."""
        self.task_manager.store_pending_response(self.project_uuid, self.contact_urn, "First")

        result = self.task_manager.handle_pending_response(self.project_uuid, self.contact_urn, "Second")

        self.assertEqual(result, "First\nSecond")
        # Should have cleared the pending response
        stored = self.task_manager.get_pending_response(self.project_uuid, self.contact_urn)
        self.assertIsNone(stored)
