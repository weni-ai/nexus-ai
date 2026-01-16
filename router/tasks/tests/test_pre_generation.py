"""
Tests for pre_generation_task using Dependency Injection.

The PreGenerationExecutor accepts a PreGenerationDependencies object,
making tests clean and scalable - no need to add more @patch decorators
when new dependencies are added.
"""

import logging
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from router.tasks.invocation_context import CachedProjectData
from router.tasks.pre_generation import (
    PreGenerationDependencies,
    PreGenerationExecutor,
    build_invoke_kwargs,
    compute_session_id,
    deserialize_cached_data,
    preprocess_message,
)


class MockDataService:
    """Mock PreGenerationService for testing."""

    def __init__(self, return_data=None, raise_exception=None):
        self.return_data = return_data
        self.raise_exception = raise_exception
        self.called_with = None

    def fetch_pre_generation_data(self, project_uuid):
        self.called_with = project_uuid
        if self.raise_exception:
            raise self.raise_exception
        return self.return_data


class MockTaskManager:
    """Mock RedisTaskManager for testing."""

    def __init__(self):
        self.status_updates = []

    def update_workflow_status(self, **kwargs):
        self.status_updates.append(kwargs)


def create_test_dependencies(
    data_service=None,
    task_manager=None,
    credentials=None,
    conversation_id=None,
    auth_token="test-token",
    save_message_called=None,
):
    """Factory to create test dependencies with sensible defaults."""
    deps = PreGenerationDependencies.__new__(PreGenerationDependencies)
    deps.data_service = data_service or MockDataService()
    deps.task_manager = task_manager or MockTaskManager()
    deps.fetch_credentials = lambda _: credentials or {}
    deps.ensure_conversation = lambda **_: conversation_id
    deps.generate_auth_token = lambda _: auth_token

    if save_message_called is not None:
        deps.save_user_message = lambda **kw: save_message_called.append(kw)
    else:
        deps.save_user_message = lambda **_: None

    return deps


class PreGenerationExecutorTestCase(SimpleTestCase):
    """Tests for PreGenerationExecutor with dependency injection."""

    def setUp(self):
        self.message = {
            "project_uuid": "test-project-uuid",
            "contact_urn": "tel:+5511999999999",
            "text": "Hello, world!",
            "metadata": {},
            "attachments": [],
        }
        self.workflow_id = "wf-test-123"

        # Sample pre-generation data (what the data service returns)
        self.sample_project_dict = {
            "uuid": "test-project-uuid",
            "name": "Test Project",
            "agents_backend": "bedrock",
            "rationale_switch": False,
            "use_components": False,
        }
        self.sample_data = (
            self.sample_project_dict,
            {"uuid": "cb-uuid", "title": "Test Content Base"},  # content_base_dict
            [{"name": "Agent 1", "role": "assistant"}],  # team
            {},  # guardrails_config
            None,  # inline_agent_config
            "bedrock",  # agents_backend
            ["Instruction 1", "Instruction 2"],  # instructions
            {"name": "Test Agent"},  # agent_data
        )

    def test_success(self):
        """Test successful pre-generation execution."""
        save_calls = []
        deps = create_test_dependencies(
            data_service=MockDataService(return_data=self.sample_data),
            credentials={"api_key": "test-key"},
            conversation_id="conv-uuid-123",
            auth_token="test-jwt-token",
            save_message_called=save_calls,
        )

        executor = PreGenerationExecutor(deps=deps)
        result = executor.execute(
            message=self.message,
            preview=False,
            language="en",
            workflow_id=self.workflow_id,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["project_uuid"], "test-project-uuid")
        self.assertEqual(result["agents_backend"], "bedrock")
        self.assertEqual(result["workflow_id"], self.workflow_id)
        self.assertIn("cached_data", result)
        self.assertIn("pre_fetched", result)
        self.assertIn("invoke_kwargs", result)

        # Verify pre-fetched data
        self.assertEqual(result["pre_fetched"]["credentials_count"], 1)
        self.assertTrue(result["pre_fetched"]["auth_token_generated"])
        self.assertEqual(result["pre_fetched"]["conversation_id"], "conv-uuid-123")

        # Verify save_user_message was called
        self.assertEqual(len(save_calls), 1)
        self.assertEqual(save_calls[0]["project_uuid"], "test-project-uuid")

    def test_failure_handling(self):
        """Test pre-generation failure handling."""
        task_manager = MockTaskManager()
        deps = create_test_dependencies(
            data_service=MockDataService(raise_exception=Exception("Database error")),
            task_manager=task_manager,
        )

        executor = PreGenerationExecutor(deps=deps)

        logging.disable(logging.CRITICAL)
        try:
            result = executor.execute(
                message=self.message,
                preview=False,
                language="en",
                workflow_id=self.workflow_id,
            )
        finally:
            logging.disable(logging.NOTSET)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["project_uuid"], "test-project-uuid")
        self.assertIn("error", result)
        self.assertIn("Database error", result["error"])

        # Verify workflow status was updated to failed
        self.assertTrue(any(u["status"] == "failed" for u in task_manager.status_updates))

    def test_without_workflow_id(self):
        """Test pre-generation without workflow ID (standalone mode)."""
        task_manager = MockTaskManager()
        deps = create_test_dependencies(
            data_service=MockDataService(return_data=self.sample_data),
            task_manager=task_manager,
        )

        executor = PreGenerationExecutor(deps=deps)
        result = executor.execute(
            message=self.message,
            preview=False,
            language="en",
            workflow_id=None,
        )

        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["workflow_id"])

        # Verify workflow status was NOT updated (no workflow_id)
        self.assertEqual(len(task_manager.status_updates), 0)

    def test_preview_mode_skips_conversation(self):
        """Test that preview mode skips conversation creation."""
        deps = create_test_dependencies(
            data_service=MockDataService(return_data=self.sample_data),
        )
        # Override ensure_conversation to track calls
        conversation_calls = []
        deps.ensure_conversation = lambda **kw: conversation_calls.append(kw) or None

        executor = PreGenerationExecutor(deps=deps)
        result = executor.execute(
            message=self.message,
            preview=True,
            language="en",
        )

        self.assertEqual(result["status"], "success")
        # ensure_conversation was called but should return None for preview
        self.assertEqual(len(conversation_calls), 1)
        self.assertTrue(conversation_calls[0]["preview"])


class PureFunctionsTestCase(SimpleTestCase):
    """Tests for pure functions (no dependencies needed)."""

    def test_compute_session_id(self):
        """Test session ID computation."""
        session_id = compute_session_id("proj-123", "sanitized-urn")
        self.assertEqual(session_id, "project-proj-123-session-sanitized-urn")

    def test_preprocess_message_basic(self):
        """Test basic message preprocessing."""
        message = {"text": "Hello world", "attachments": [], "metadata": {}}
        processed, turn_off_rationale = preprocess_message(message)

        self.assertEqual(processed["text"], "Hello world")
        self.assertFalse(turn_off_rationale)

    def test_preprocess_message_with_overwrite(self):
        """Test message preprocessing with overwrite appends to text."""
        message = {
            "text": "Original",
            "attachments": [],
            "metadata": {"overwrite_message": "Appended"},
        }
        processed, _ = preprocess_message(message)
        self.assertIn("Appended", processed["text"])


class DeserializeCachedDataTestCase(SimpleTestCase):
    """Tests for deserialize_cached_data function."""

    def test_deserialize_cached_data_full(self):
        """Test deserializing complete cached data."""
        serialized = {
            "project_dict": {"uuid": "proj-123", "name": "Project"},
            "content_base_dict": {"uuid": "cb-123"},
            "team": [{"name": "Agent"}],
            "guardrails_config": {"enabled": True},
            "inline_agent_config_dict": {"timeout": 30},
            "instructions": ["Do this", "Do that"],
            "agent_data": {"name": "Main Agent"},
            "formatter_agent_configurations": {"format": "json"},
        }

        result = deserialize_cached_data(serialized)

        self.assertIsInstance(result, CachedProjectData)
        self.assertEqual(result.project_dict["uuid"], "proj-123")
        self.assertEqual(result.content_base_dict["uuid"], "cb-123")
        self.assertEqual(len(result.team), 1)
        self.assertEqual(result.guardrails_config["enabled"], True)
        self.assertEqual(result.inline_agent_config_dict["timeout"], 30)
        self.assertEqual(len(result.instructions), 2)
        self.assertEqual(result.agent_data["name"], "Main Agent")

    def test_deserialize_cached_data_partial(self):
        """Test deserializing partial cached data (None values)."""
        serialized = {
            "project_dict": {"uuid": "proj-123"},
            "content_base_dict": None,
            "team": [],
            "guardrails_config": None,
            "inline_agent_config_dict": None,
            "instructions": [],
            "agent_data": None,
        }

        result = deserialize_cached_data(serialized)

        self.assertIsInstance(result, CachedProjectData)
        self.assertEqual(result.project_dict["uuid"], "proj-123")
        self.assertIsNone(result.content_base_dict)
        self.assertEqual(result.team, [])

    def test_deserialize_cached_data_empty(self):
        """Test deserializing empty cached data."""
        serialized = {}
        result = deserialize_cached_data(serialized)

        self.assertIsInstance(result, CachedProjectData)
        self.assertIsNone(result.project_dict)
        self.assertIsNone(result.content_base_dict)


class CachedProjectDataTestCase(SimpleTestCase):
    """Tests for CachedProjectData dataclass."""

    def test_from_pre_generation_data(self):
        """Test creating CachedProjectData from pre-generation service output."""
        project_dict = {"uuid": "proj-123", "name": "Test"}
        content_base_dict = {"uuid": "cb-123"}
        team = [{"name": "Agent"}]
        guardrails_config = {}
        inline_agent_config_dict = None
        instructions = ["Instruction"]
        agent_data = {"name": "Agent"}

        result = CachedProjectData.from_pre_generation_data(
            project_dict=project_dict,
            content_base_dict=content_base_dict,
            team=team,
            guardrails_config=guardrails_config,
            inline_agent_config_dict=inline_agent_config_dict,
            instructions=instructions,
            agent_data=agent_data,
        )

        self.assertIsInstance(result, CachedProjectData)
        self.assertEqual(result.project_dict, project_dict)
        self.assertEqual(result.content_base_dict, content_base_dict)
        self.assertEqual(result.team, team)


class BuildInvokeKwargsTestCase(SimpleTestCase):
    """Tests for build_invoke_kwargs function."""

    def test_build_invoke_kwargs_includes_prefetched(self):
        """Test that pre-fetched data is included in invoke_kwargs."""
        cached_data = CachedProjectData.from_pre_generation_data(
            project_dict={"uuid": "proj-123", "use_components": False},
            content_base_dict={"uuid": "cb-123"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
        )
        message = {
            "project_uuid": "proj-123",
            "text": "Hello",
            "contact_urn": "tel:+123",
        }

        result = build_invoke_kwargs(
            cached_data=cached_data,
            message=message,
            preview=False,
            language="en",
            user_email="test@test.com",
            turn_off_rationale=False,
            credentials={"key": "value"},
            auth_token="token-123",
            session_id="session-123",
            conversation_id="conv-123",
        )

        self.assertEqual(result["_pre_fetched_credentials"], {"key": "value"})
        self.assertEqual(result["_pre_fetched_auth_token"], "token-123")
        self.assertEqual(result["_pre_fetched_session_id"], "session-123")
        self.assertEqual(result["_pre_fetched_conversation_id"], "conv-123")
