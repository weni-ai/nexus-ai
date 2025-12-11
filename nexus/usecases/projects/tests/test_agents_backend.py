from unittest import skip
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from inline_agents.backends.openai.tests.openai_factory import (
    OpenAISupervisorFactory,
)
from inline_agents.backends.tests.inline_factories import SupervisorFactory
from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from nexus.intelligences.models import ContentBase
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseAgentFactory

from ..projects_use_case import ProjectsUseCase
from .project_factory import ProjectFactory


class MockExternalAgentClient:
    def create_supervisor(
        self, project_uuid, supervisor_name, supervisor_description, supervisor_instructions, is_single_agent
    ):
        return "supervisor_id", "supervisor_alias", "v1"

    def prepare_agent(self, agent_id: str):
        pass

    def wait_agent_status_update(self, external_id):
        pass

    def associate_sub_agents(self, **kwargs):
        pass

    def create_agent_alias(self, **kwargs):
        return "sub_agent_alias_id", "sub_agent_alias_arn", "v1"


class AgentsBackendTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.usecase = ProjectsUseCase(
            event_manager_notify=mock_event_manager_notify,
            external_agent_client=MockExternalAgentClient,
        )

        self.supervisor_openai = OpenAISupervisorFactory()
        self.supervisor_bedrock = SupervisorFactory()

        self.project_ab2 = self.usecase.create_project(
            project_dto=ProjectCreationDTO(
                uuid=str(uuid4()),
                name="Test Project",
                org_uuid=str(self.project.org.uuid),
                is_template=False,
                template_type_uuid=None,
                brain_on=True,
                authorizations=[],
                indexer_database=Project.BEDROCK,
            ),
            user_email=self.project.created_by.email,
        )
        self.project_ab2.inline_agent_switch = True
        self.project_ab2.save()

    def test_get_agents_backend_by_project_default(self):
        """Test getting agents backend when it's not set (should return OpenAIBackend as default)"""
        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "OpenAIBackend")

    def test_get_agents_backend_by_project_with_bedrock(self):
        """Test getting agents backend when it's set to BedrockBackend"""
        # Set the backend directly on the model
        self.project.agents_backend = "BedrockBackend"
        self.project.save()

        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "BedrockBackend")

    def test_get_agents_backend_by_project_with_openai(self):
        """Test getting agents backend when it's set to OpenAIBackend"""
        # Set the backend directly on the model
        self.project.agents_backend = "OpenAIBackend"
        self.project.save()

        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "OpenAIBackend")

    def test_set_agents_backend_by_project_bedrock(self):
        """Test setting agents backend to BedrockBackend"""
        result = self.usecase.set_agents_backend_by_project(str(self.project.uuid), "bedrock")

        # Check the returned value
        self.assertEqual(result, "BedrockBackend")

        # Check that it was saved to the database
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "BedrockBackend")

    def test_set_agents_backend_by_project_openai(self):
        """Test setting agents backend to OpenAIBackend"""
        result = self.usecase.set_agents_backend_by_project(str(self.project.uuid), "openai")

        # Check the returned value
        self.assertEqual(result, "OpenAIBackend")

        # Check that it was saved to the database
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "OpenAIBackend")

    def test_set_agents_backend_by_project_case_insensitive(self):
        """Test that backend names are case insensitive"""
        result = self.usecase.set_agents_backend_by_project(str(self.project.uuid), "BEDROCK")

        self.assertEqual(result, "BedrockBackend")

        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "BedrockBackend")

    def test_set_agents_backend_by_project_invalid_backend(self):
        """Test setting an invalid backend should raise an exception"""
        with self.assertRaises(Exception) as context:
            self.usecase.set_agents_backend_by_project(str(self.project.uuid), "invalid_backend")

        self.assertIn("Invalid backend", str(context.exception))

    def test_set_agents_backend_by_project_nonexistent_project(self):
        """Test setting backend for non-existent project should raise an exception"""
        from nexus.projects.exceptions import ProjectDoesNotExist

        with self.assertRaises(ProjectDoesNotExist):
            self.usecase.set_agents_backend_by_project(str(uuid4()), "bedrock")

    def test_set_agents_backend_by_project_empty_string(self):
        """Test setting empty string as backend should raise an exception"""
        with self.assertRaises(Exception):  # noqa: B017
            self.usecase.set_agents_backend_by_project(str(self.project.uuid), "")

    def test_get_agents_backend_after_set(self):
        """Test getting backend after setting it"""
        # Set the backend
        self.usecase.set_agents_backend_by_project(str(self.project.uuid), "openai")

        # Get the backend
        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "OpenAIBackend")

    def test_set_agents_backend_multiple_times(self):
        """Test setting backend multiple times"""
        # Set to bedrock first
        result1 = self.usecase.set_agents_backend_by_project(str(self.project.uuid), "bedrock")
        self.assertEqual(result1, "BedrockBackend")

        # Set to openai
        result2 = self.usecase.set_agents_backend_by_project(str(self.project.uuid), "openai")
        self.assertEqual(result2, "OpenAIBackend")

        # Verify the final state
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "OpenAIBackend")

        # Get the backend
        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "OpenAIBackend")


@skip("temporarily skipped: backend registry and supervisor repositories under stabilization")
class TestGetAgentBuilderProjectDetails(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.usecase = ProjectsUseCase(
            event_manager_notify=mock_event_manager_notify,
            external_agent_client=MockExternalAgentClient,
        )

        self.supervisor_openai = OpenAISupervisorFactory()
        self.supervisor_bedrock = SupervisorFactory()

        self.project_ab2 = self.usecase.create_project(
            project_dto=ProjectCreationDTO(
                uuid=str(uuid4()),
                name="Test Project",
                org_uuid=str(self.project.org.uuid),
                is_template=False,
                template_type_uuid=None,
                brain_on=True,
                authorizations=[],
                indexer_database=Project.BEDROCK,
            ),
            user_email=self.project.created_by.email,
        )
        self.project_ab2.agent = self.supervisor_bedrock
        self.project_ab2.inline_agent_switch = True
        self.project_ab2.save()

    @patch("nexus.inline_agents.backends.bedrock.repository.BedrockSupervisorRepository.get_supervisor")
    def test_get_agent_builder_project_details(self, mock_get_supervisor):
        mock_get_supervisor.return_value = {
            "foundation_model": "nova-pro",
            "instruction": "You are a helpful assistant.",
        }

        result = self.usecase.get_agent_builder_project_details(str(self.project_ab2.uuid))

        self.assertEqual(result["agents_backend"], "BedrockBackend")
        self.assertEqual(result["manager_foundation_model"], "nova-pro")

    @patch("nexus.inline_agents.backends.openai.repository.OpenAISupervisorRepository.get_supervisor")
    def test_get_agent_builder_project_details_openai(self, mock_get_supervisor):
        mock_get_supervisor.return_value = {
            "foundation_model": "gpt-4-turbo",
            "instruction": "You are an OpenAI assistant.",
        }

        self.project.agent = self.supervisor_openai
        self.project.agents_backend = "OpenAIBackend"
        self.project.inline_agent_switch = True
        self.project.save()

        content_base = get_default_content_base_by_project(str(self.project.uuid))
        try:
            _ = content_base.agent
        except ContentBase.agent.RelatedObjectDoesNotExist:
            ContentBaseAgentFactory(content_base=content_base)

        result = self.usecase.get_agent_builder_project_details(str(self.project.uuid))
        self.assertEqual(result["agents_backend"], "OpenAIBackend")
        self.assertEqual(result["manager_foundation_model"], "gpt-4-turbo")
