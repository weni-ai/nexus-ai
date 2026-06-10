import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from nexus.eda.registry import WENI_MIGRATED_QUEUES
from nexus.projects.consumers.project_consumer import ProjectConsumer
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO


class ProjectConsumerTestCase(SimpleTestCase):
    def setUp(self) -> None:
        self.consumer = ProjectConsumer()

    def _message(self, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.body = json.dumps(payload).encode()
        msg.delivery_tag = 42
        ch = MagicMock()
        msg.channel = ch
        return msg

    def test_migrated_queue_in_registry(self) -> None:
        self.assertIn("nexus-ai.projects", WENI_MIGRATED_QUEUES)

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_handle_success_acks_and_creates_project(self, mock_usecase_cls) -> None:
        project_uuid = str(uuid4())
        org_uuid = str(uuid4())
        payload = {
            "uuid": project_uuid,
            "name": "New project",
            "is_template": False,
            "template_type_uuid": None,
            "organization_uuid": org_uuid,
            "brain_on": True,
            "authorizations": [{"role": "admin"}],
            "indexer_database": Project.BEDROCK,
            "inline_agent_switch": False,
            "user_email": "creator@example.com",
        }
        msg = self._message(payload)

        self.consumer.handle(msg)

        mock_usecase_cls.return_value.create_project.assert_called_once()
        call_kwargs = mock_usecase_cls.return_value.create_project.call_args.kwargs
        project_dto = call_kwargs["project_dto"]
        self.assertIsInstance(project_dto, ProjectCreationDTO)
        self.assertEqual(project_dto.uuid, project_uuid)
        self.assertEqual(project_dto.name, "New project")
        self.assertEqual(project_dto.org_uuid, org_uuid)
        self.assertTrue(project_dto.brain_on)
        self.assertFalse(project_dto.inline_agent_switch)
        self.assertEqual(call_kwargs["user_email"], "creator@example.com")
        msg.channel.basic_ack.assert_called_once_with(42)
        msg.channel.basic_reject.assert_not_called()

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_handle_defaults_indexer_database_to_bedrock(self, mock_usecase_cls) -> None:
        payload = {
            "uuid": str(uuid4()),
            "name": "P",
            "is_template": False,
            "template_type_uuid": None,
            "organization_uuid": str(uuid4()),
            "user_email": "u@example.com",
        }
        msg = self._message(payload)

        self.consumer.handle(msg)

        project_dto = mock_usecase_cls.return_value.create_project.call_args.kwargs["project_dto"]
        self.assertEqual(project_dto.indexer_database, Project.BEDROCK)
        self.assertTrue(project_dto.inline_agent_switch)

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_handle_failure_rejects_and_reports_sentry(self, mock_usecase_cls) -> None:
        mock_usecase_cls.return_value.create_project.side_effect = RuntimeError("create failed")
        payload = {
            "uuid": str(uuid4()),
            "name": "P",
            "is_template": False,
            "template_type_uuid": None,
            "organization_uuid": str(uuid4()),
            "user_email": "u@example.com",
        }
        msg = self._message(payload)

        with patch("nexus.eda.consumers.base.capture_exception") as capture_exception:
            self.consumer.handle(msg)
            capture_exception.assert_called_once()

        msg.channel.basic_reject.assert_called_once_with(42, requeue=False)
        msg.channel.basic_ack.assert_not_called()

    def test_handle_invalid_json_rejects(self) -> None:
        msg = MagicMock()
        msg.body = b"not-json"
        msg.delivery_tag = 7
        msg.channel = MagicMock()

        with patch("nexus.eda.consumers.base.capture_exception") as capture_exception:
            self.consumer.handle(msg)
            capture_exception.assert_called_once()

        msg.channel.basic_reject.assert_called_once_with(7, requeue=False)
