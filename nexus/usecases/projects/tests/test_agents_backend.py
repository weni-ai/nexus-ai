from uuid import uuid4

from django.test import TestCase

from inline_agents.backends.openai.tests.openai_factory import (
    OpenAISupervisorFactory,
)
from inline_agents.backends.tests.inline_factories import SupervisorFactory
from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO

from ..projects_use_case import ProjectsUseCase
from .project_factory import ProjectFactory


class AgentsBackendTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.usecase = ProjectsUseCase()

    def test_get_agents_backend_by_project_default(self):
        """Test getting agents backend when it's not set (should return BedrockBackend as default)"""
        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "BedrockBackend")

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
        result = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), "bedrock"
        )

        # Check the returned value
        self.assertEqual(result, "BedrockBackend")

        # Check that it was saved to the database
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "BedrockBackend")

    def test_set_agents_backend_by_project_openai(self):
        """Test setting agents backend to OpenAIBackend"""
        result = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), "openai"
        )

        # Check the returned value
        self.assertEqual(result, "OpenAIBackend")

        # Check that it was saved to the database
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "OpenAIBackend")

    def test_set_agents_backend_by_project_case_insensitive(self):
        """Test that backend names are case insensitive"""
        result = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), "BEDROCK"
        )

        self.assertEqual(result, "BedrockBackend")

        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "BedrockBackend")

    def test_set_agents_backend_by_project_invalid_backend(self):
        """Test setting an invalid backend should raise an exception"""
        with self.assertRaises(Exception) as context:
            self.usecase.set_agents_backend_by_project(
                str(self.project.uuid), "invalid_backend"
            )

        self.assertIn("Invalid backend", str(context.exception))

    def test_set_agents_backend_by_project_nonexistent_project(self):
        """Test setting backend for non-existent project should raise an exception"""
        with self.assertRaises(Exception):
            self.usecase.set_agents_backend_by_project(str(uuid4()), "bedrock")

    def test_set_agents_backend_by_project_empty_string(self):
        """Test setting empty string as backend should raise an exception"""
        with self.assertRaises(Exception):
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
        result1 = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), "bedrock"
        )
        self.assertEqual(result1, "BedrockBackend")

        # Set to openai
        result2 = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), "openai"
        )
        self.assertEqual(result2, "OpenAIBackend")

        # Verify the final state
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "OpenAIBackend")

        # Get the backend
        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "OpenAIBackend")


class TestGetAgentBuilderProjectDetails(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.usecase = ProjectsUseCase(
            event_manager_notify=mock_event_manager_notify,
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

    def test_get_agent_builder_project_details(self):
        """Test getting agent builder project details"""
        result = self.usecase.get_agent_builder_project_details(
            str(self.project_ab2.uuid)
        )

        self.assertEqual(
            result,
            {
                "agents_backend": "BedrockBackend",
                "manager_foundation_model": "nova-pro",
            },
        )

    def test_get_agent_builder_project_details_openai(self):
        """Test getting agent builder project details"""
        self.project_ab2.inline_agent_switch = True
        self.project_ab2.save()
        result = self.usecase.get_agent_builder_project_details(str(self.project.uuid))
        self.assertEqual(
            result,
            {
                "agents_backend": "OpenAIBackend",
                "manager_foundation_model": "gpt-4-turbo",
            },
        )
