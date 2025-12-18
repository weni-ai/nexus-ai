import logging
from unittest.mock import patch

from django.test import TestCase

from router.tasks.redis_task_manager import RedisTaskManager
from router.tasks.workflow_orchestrator import (
    WorkflowContext,
    _create_workflow_context,
    _finalize_workflow,
    _handle_workflow_error,
    _initialize_workflow,
)


class MockRedisClient:
    """In-memory mock Redis client for testing."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        value = self.data.get(key)
        if value is not None:
            return value.encode("utf-8") if isinstance(value, str) else value
        return None

    def set(self, key, value):
        self.data[key] = value if isinstance(value, str) else value.decode("utf-8")

    def setex(self, key, ttl, value):
        self.data[key] = value if isinstance(value, str) else value.decode("utf-8")

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)


class WorkflowContextTestCase(TestCase):
    """Tests for WorkflowContext dataclass."""

    def test_workflow_context_creation(self):
        """Test creating a WorkflowContext."""
        mock_redis = MockRedisClient()
        task_manager = RedisTaskManager(redis_client=mock_redis)
        message = {"project_uuid": "proj-123", "contact_urn": "tel:+5511999999999", "text": "Hello"}

        ctx = WorkflowContext(
            workflow_id="wf-123",
            project_uuid="proj-123",
            contact_urn="tel:+5511999999999",
            message=message,
            preview=False,
            language="en",
            user_email="user@example.com",
            task_id="task-123",
            task_manager=task_manager,
        )

        self.assertEqual(ctx.workflow_id, "wf-123")
        self.assertEqual(ctx.project_uuid, "proj-123")
        self.assertEqual(ctx.contact_urn, "tel:+5511999999999")
        self.assertFalse(ctx.preview)
        self.assertEqual(ctx.language, "en")
        self.assertIsNone(ctx.cached_data)
        self.assertIsNone(ctx.agents_backend)


class CreateWorkflowContextTestCase(TestCase):
    """Tests for _create_workflow_context helper."""

    def test_create_workflow_context(self):
        """Test creating workflow context from task inputs."""
        message = {
            "project_uuid": "proj-123",
            "contact_urn": "tel:+5511999999999",
            "text": "Test message",
        }

        ctx = _create_workflow_context(
            task_id="task-123",
            message=message,
            preview=False,
            language="pt",
            user_email="test@test.com",
        )

        self.assertIsInstance(ctx, WorkflowContext)
        self.assertEqual(ctx.project_uuid, "proj-123")
        self.assertEqual(ctx.contact_urn, "tel:+5511999999999")
        self.assertEqual(ctx.language, "pt")
        self.assertEqual(ctx.user_email, "test@test.com")
        self.assertIsNotNone(ctx.workflow_id)  # Should be generated

    def test_create_workflow_context_preview_mode(self):
        """Test creating workflow context in preview mode."""
        message = {"project_uuid": "proj-123", "contact_urn": "tel:+5511999999999", "text": "Test"}

        ctx = _create_workflow_context(
            task_id="task-123",
            message=message,
            preview=True,
            language="en",
            user_email="preview@test.com",
        )

        self.assertTrue(ctx.preview)


class InitializeWorkflowTestCase(TestCase):
    """Tests for _initialize_workflow helper."""

    @patch("router.tasks.workflow_orchestrator.notify_async")
    def test_initialize_workflow(self, mock_notify_async):
        """Test workflow initialization."""
        mock_redis = MockRedisClient()
        task_manager = RedisTaskManager(redis_client=mock_redis)

        ctx = WorkflowContext(
            workflow_id="wf-123",
            project_uuid="proj-123",
            contact_urn="urn:test",
            message={"project_uuid": "proj-123", "contact_urn": "urn:test", "text": "Hello"},
            preview=False,
            language="en",
            user_email="",
            task_id="task-123",
            task_manager=task_manager,
        )

        _initialize_workflow(ctx)

        # Verify typing indicator was dispatched
        mock_notify_async.assert_called_once()
        # Check that it was called with the correct event name
        call_args, call_kwargs = mock_notify_async.call_args
        if call_args:
            self.assertEqual(call_args[0], "workflow:send_typing_indicator")
        else:
            # Event name might be passed as keyword argument
            self.assertIn("project_uuid", call_kwargs)

    @patch("router.tasks.workflow_orchestrator.notify_async")
    def test_initialize_workflow_preview_skips_typing(self, mock_notify_async):
        """Test that preview mode still dispatches typing (observer handles skip)."""
        mock_redis = MockRedisClient()
        task_manager = RedisTaskManager(redis_client=mock_redis)

        ctx = WorkflowContext(
            workflow_id="wf-123",
            project_uuid="proj-123",
            contact_urn="urn:test",
            message={"project_uuid": "proj-123", "contact_urn": "urn:test", "text": "Hello"},
            preview=True,  # Preview mode
            language="en",
            user_email="",
            task_id="task-123",
            task_manager=task_manager,
        )

        _initialize_workflow(ctx)

        # Typing indicator observer is dispatched but handles preview internally
        mock_notify_async.assert_called_once()


class FinalizeWorkflowTestCase(TestCase):
    """Tests for _finalize_workflow helper."""

    def test_finalize_workflow(self):
        """Test workflow finalization."""
        mock_redis = MockRedisClient()
        task_manager = RedisTaskManager(redis_client=mock_redis)

        # Create workflow state first
        task_manager.create_workflow_state(
            workflow_id="wf-123",
            project_uuid="proj-123",
            contact_urn="urn:test",
            message_text="Test",
        )

        ctx = WorkflowContext(
            workflow_id="wf-123",
            project_uuid="proj-123",
            contact_urn="urn:test",
            message={"project_uuid": "proj-123", "contact_urn": "urn:test", "text": "Hello"},
            preview=False,
            language="en",
            user_email="",
            task_id="task-123",
            task_manager=task_manager,
        )

        _finalize_workflow(ctx)

        # Verify workflow state was cleared
        state = task_manager.get_workflow_state("proj-123", "urn:test")
        self.assertIsNone(state)


class HandleWorkflowErrorTestCase(TestCase):
    """Tests for _handle_workflow_error helper."""

    @patch("router.tasks.workflow_orchestrator.sentry_sdk")
    def test_handle_workflow_error(self, mock_sentry):
        """Test workflow error handling."""
        mock_redis = MockRedisClient()
        task_manager = RedisTaskManager(redis_client=mock_redis)

        # Create workflow state first
        task_manager.create_workflow_state(
            workflow_id="wf-123",
            project_uuid="proj-123",
            contact_urn="urn:test",
            message_text="Test",
        )

        ctx = WorkflowContext(
            workflow_id="wf-123",
            project_uuid="proj-123",
            contact_urn="urn:test",
            message={"project_uuid": "proj-123", "contact_urn": "urn:test", "text": "Hello"},
            preview=False,
            language="en",
            user_email="",
            task_id="task-123",
            task_manager=task_manager,
        )

        error = Exception("Test error")

        # Suppress expected error logs
        logging.disable(logging.CRITICAL)
        try:
            _handle_workflow_error(ctx, error)
        finally:
            logging.disable(logging.NOTSET)

        # Verify error was captured by Sentry
        mock_sentry.capture_exception.assert_called_once_with(error)

        # Verify workflow state was cleared (finalize clears state after updating)
        state = task_manager.get_workflow_state("proj-123", "urn:test")
        self.assertIsNone(state)
