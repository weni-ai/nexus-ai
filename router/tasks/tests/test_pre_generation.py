"""
Tests for pre_generation_task Celery task.

Tests cover:
- Successful pre-generation data fetching
- Error handling and failure states
- Workflow state updates
- CachedProjectData serialization/deserialization
"""

import logging
from unittest.mock import MagicMock, patch

from django.test import TestCase

from router.tasks.invocation_context import CachedProjectData
from router.tasks.pre_generation import deserialize_cached_data, pre_generation_task


class PreGenerationTaskTestCase(TestCase):
    """Tests for pre_generation_task."""

    def setUp(self):
        self.message = {
            "project_uuid": "test-project-uuid",
            "contact_urn": "tel:+5511999999999",
            "text": "Hello, world!",
            "metadata": {},
            "attachments": [],
        }
        self.workflow_id = "wf-test-123"

        # Sample pre-generation data
        self.sample_project_dict = {
            "uuid": "test-project-uuid",
            "name": "Test Project",
            "agents_backend": "bedrock",
            "rationale_switch": False,
            "use_components": False,
        }
        self.sample_content_base_dict = {
            "uuid": "cb-uuid",
            "title": "Test Content Base",
        }
        self.sample_team = [
            {"name": "Agent 1", "role": "assistant"},
        ]
        self.sample_guardrails_config = {}
        self.sample_inline_agent_config = None
        self.sample_instructions = ["Instruction 1", "Instruction 2"]
        self.sample_agent_data = {"name": "Test Agent"}

    @patch("router.tasks.pre_generation.get_task_manager")
    @patch("router.tasks.pre_generation.PreGenerationService")
    @patch("router.tasks.pre_generation.sentry_sdk")
    def test_pre_generation_task_success(self, mock_sentry, mock_service_class, mock_get_tm):
        """Test successful pre-generation task execution."""
        # Setup mocks
        mock_task_manager = MagicMock()
        mock_get_tm.return_value = mock_task_manager

        mock_service = MagicMock()
        mock_service.fetch_pre_generation_data.return_value = (
            self.sample_project_dict,
            self.sample_content_base_dict,
            self.sample_team,
            self.sample_guardrails_config,
            self.sample_inline_agent_config,
            "bedrock",
            self.sample_instructions,
            self.sample_agent_data,
        )
        mock_service_class.return_value = mock_service

        # Create a mock task with request
        mock_self = MagicMock()
        mock_self.request.id = "celery-task-id-123"

        # Call the task function directly (bypassing Celery decorator)
        # For bind=True tasks, use .run() method or call __wrapped__ with self first
        result = pre_generation_task.run(
            message=self.message,
            preview=False,
            language="en",
            workflow_id=self.workflow_id,
        )

        # Verify result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["project_uuid"], "test-project-uuid")
        self.assertEqual(result["agents_backend"], "bedrock")
        self.assertEqual(result["workflow_id"], self.workflow_id)
        self.assertIn("cached_data", result)

        # Verify service was called
        mock_service.fetch_pre_generation_data.assert_called_once_with("test-project-uuid")

    @patch("router.tasks.pre_generation.get_task_manager")
    @patch("router.tasks.pre_generation.PreGenerationService")
    @patch("router.tasks.pre_generation.sentry_sdk")
    def test_pre_generation_task_failure(self, mock_sentry, mock_service_class, mock_get_tm):
        """Test pre-generation task failure handling."""
        # Setup mocks
        mock_task_manager = MagicMock()
        mock_get_tm.return_value = mock_task_manager

        mock_service = MagicMock()
        mock_service.fetch_pre_generation_data.side_effect = Exception("Database error")
        mock_service_class.return_value = mock_service

        # Suppress expected error logs
        logging.disable(logging.CRITICAL)
        try:
            # Call the task
            result = pre_generation_task.run(
                message=self.message,
                preview=False,
                language="en",
                workflow_id=self.workflow_id,
            )
        finally:
            logging.disable(logging.NOTSET)

        # Verify failure result
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["project_uuid"], "test-project-uuid")
        self.assertIn("error", result)
        self.assertIn("Database error", result["error"])

        # Verify Sentry captured the exception
        mock_sentry.capture_exception.assert_called_once()

    @patch("router.tasks.pre_generation.get_task_manager")
    @patch("router.tasks.pre_generation.PreGenerationService")
    @patch("router.tasks.pre_generation.sentry_sdk")
    def test_pre_generation_task_without_workflow_id(self, mock_sentry, mock_service_class, mock_get_tm):
        """Test pre-generation task without workflow ID (standalone mode)."""
        # Setup mocks
        mock_task_manager = MagicMock()
        mock_get_tm.return_value = mock_task_manager

        mock_service = MagicMock()
        mock_service.fetch_pre_generation_data.return_value = (
            self.sample_project_dict,
            self.sample_content_base_dict,
            self.sample_team,
            self.sample_guardrails_config,
            self.sample_inline_agent_config,
            "bedrock",
            self.sample_instructions,
            self.sample_agent_data,
        )
        mock_service_class.return_value = mock_service

        # Call without workflow_id
        result = pre_generation_task.run(
            message=self.message,
            preview=False,
            language="en",
            workflow_id=None,
        )

        # Verify success
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["workflow_id"])

        # Verify workflow status was NOT updated (no workflow_id)
        mock_task_manager.update_workflow_status.assert_not_called()


class DeserializeCachedDataTestCase(TestCase):
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


class CachedProjectDataTestCase(TestCase):
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
