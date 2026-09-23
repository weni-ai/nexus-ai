import logging
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.tasks.redis_task_manager import RedisTaskManager
from router.tasks.workflow_orchestrator import (
    WorkflowContext,
    _create_workflow_context,
    _finalize_workflow,
    _handle_workflow_error,
    _initialize_workflow,
    _run_generation,
    _run_pre_generation,
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


class WorkflowContextTestCase(SimpleTestCase):
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
            preview_websocket=False,
            simulation_channel=False,
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


class CreateWorkflowContextTestCase(SimpleTestCase):
    """Tests for _create_workflow_context helper."""

    @patch("router.tasks.workflow_orchestrator.RedisTaskManager", return_value=MagicMock())
    def test_create_workflow_context(self, _mock_rtm):
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
            simulation_channel=False,
            language="pt",
            user_email="test@test.com",
        )

        self.assertIsInstance(ctx, WorkflowContext)
        self.assertEqual(ctx.project_uuid, "proj-123")
        self.assertEqual(ctx.contact_urn, "tel:+5511999999999")
        self.assertEqual(ctx.language, "pt")
        self.assertEqual(ctx.user_email, "test@test.com")
        self.assertIsNotNone(ctx.workflow_id)  # Should be generated

    @patch("router.tasks.workflow_orchestrator.RedisTaskManager", return_value=MagicMock())
    def test_create_workflow_context_preview_mode(self, _mock_rtm):
        """Test creating workflow context in preview mode."""
        message = {"project_uuid": "proj-123", "contact_urn": "tel:+5511999999999", "text": "Test"}

        ctx = _create_workflow_context(
            task_id="task-123",
            message=message,
            preview=True,
            simulation_channel=False,
            language="en",
            user_email="preview@test.com",
        )

        self.assertTrue(ctx.preview)


class InitializeWorkflowTestCase(SimpleTestCase):
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
            preview_websocket=False,
            simulation_channel=False,
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
            preview_websocket=False,
            simulation_channel=False,
            language="en",
            user_email="",
            task_id="task-123",
            task_manager=task_manager,
        )

        _initialize_workflow(ctx)

        # Typing indicator observer is dispatched but handles preview internally
        mock_notify_async.assert_called_once()


class InstagramCommentWorkflowRoutingTestCase(SimpleTestCase):
    def _context(self):
        return WorkflowContext(
            workflow_id="wf-ig-comment",
            project_uuid="project-uuid",
            contact_urn="instagram:5467890213",
            message={
                "project_uuid": "project-uuid",
                "contact_urn": "instagram:5467890213",
                "text": "Legal!",
                "metadata": {
                    "overwrite_message": {
                        "ig_comment": {"id": "30065221"},
                        "ig_response_type": "dm_comment",
                    }
                },
                "stream_support": True,
            },
            preview=False,
            preview_websocket=False,
            simulation_channel=False,
            language="pt-br",
            user_email="user@example.com",
            task_id="task-123",
            task_manager=MagicMock(),
            flows_user_email="flows@example.com",
        )

    @patch("router.tasks.workflow_orchestrator.get_action_clients")
    @patch("router.tasks.workflow_orchestrator.deserialize_cached_data")
    @patch("router.tasks.workflow_orchestrator.pre_generation_task")
    def test_pre_generation_forces_broadcast_and_disables_streaming(
        self,
        mock_pre_generation_task,
        mock_deserialize_cached_data,
        mock_get_action_clients,
    ):
        ctx = self._context()
        cached_data = MagicMock()
        cached_data.project_dict = {"use_components": False}
        mock_deserialize_cached_data.return_value = cached_data
        mock_pre_generation_task.run.return_value = {
            "status": "success",
            "cached_data": {},
            "agents_backend": "OpenAIBackend",
        }
        mock_get_action_clients.return_value = (MagicMock(), MagicMock())

        _run_pre_generation(ctx)

        mock_get_action_clients.assert_called_once_with(
            preview=False,
            multi_agents=True,
            project_use_components=False,
            project_uuid="project-uuid",
            stream_support=False,
            force_instagram_comment_broadcast=True,
        )

    @patch("router.tasks.workflow_orchestrator._invoke_backend")
    @patch("router.tasks.workflow_orchestrator.BackendsRegistry.get_backend")
    @patch("router.tasks.workflow_orchestrator.should_skip_conversation_sqs", return_value=True)
    @patch("router.tasks.workflow_orchestrator._extract_and_apply_message_context")
    @patch("router.tasks.workflow_orchestrator._create_message_object")
    @patch("router.tasks.workflow_orchestrator.apply_simulation_foundation_model_override")
    @patch("router.tasks.workflow_orchestrator._preprocess_message_input")
    def test_generation_disables_grpc_streaming_for_comment(
        self,
        mock_preprocess,
        mock_apply_model_override,
        mock_create_message,
        _mock_extract_context,
        _mock_skip_sqs,
        _mock_get_backend,
        mock_invoke_backend,
    ):
        ctx = self._context()
        ctx.cached_data = MagicMock(guardrails_config={})
        ctx.agents_backend = "OpenAIBackend"
        mock_preprocess.return_value = (ctx.message, None, False)
        mock_apply_model_override.return_value = None
        mock_create_message.return_value = MagicMock(
            text="Legal!",
            channel_uuid="channel-uuid",
            contact_name="",
        )
        mock_invoke_backend.return_value = ("Obrigado!", False)

        self.assertEqual(_run_generation(ctx), ("Obrigado!", False))
        self.assertFalse(mock_invoke_backend.call_args.kwargs["stream_support"])


class FinalizeWorkflowTestCase(SimpleTestCase):
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
            preview_websocket=False,
            simulation_channel=False,
            language="en",
            user_email="",
            task_id="task-123",
            task_manager=task_manager,
        )

        _finalize_workflow(ctx)

        # Verify workflow state was cleared
        state = task_manager.get_workflow_state("proj-123", "urn:test")
        self.assertIsNone(state)


class HandleWorkflowErrorTestCase(SimpleTestCase):
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
            preview_websocket=False,
            simulation_channel=False,
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
