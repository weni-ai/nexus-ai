from django.test import TestCase
from uuid import uuid4

from .project_factory import ProjectFactory
from ..projects_use_case import ProjectsUseCase
from nexus.projects.models import Project


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
            str(self.project.uuid), 
            "bedrock"
        )
        
        # Check the returned value
        self.assertEqual(result, "BedrockBackend")
        
        # Check that it was saved to the database
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "BedrockBackend")

    def test_set_agents_backend_by_project_openai(self):
        """Test setting agents backend to OpenAIBackend"""
        result = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), 
            "openai"
        )
        
        # Check the returned value
        self.assertEqual(result, "OpenAIBackend")
        
        # Check that it was saved to the database
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "OpenAIBackend")

    def test_set_agents_backend_by_project_case_insensitive(self):
        """Test that backend names are case insensitive"""
        result = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), 
            "BEDROCK"
        )
        
        self.assertEqual(result, "BedrockBackend")
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "BedrockBackend")

    def test_set_agents_backend_by_project_invalid_backend(self):
        """Test setting an invalid backend should raise an exception"""
        with self.assertRaises(Exception) as context:
            self.usecase.set_agents_backend_by_project(
                str(self.project.uuid), 
                "invalid_backend"
            )
        
        self.assertIn("Invalid backend", str(context.exception))

    def test_set_agents_backend_by_project_nonexistent_project(self):
        """Test setting backend for non-existent project should raise an exception"""
        with self.assertRaises(Exception):
            self.usecase.set_agents_backend_by_project(
                str(uuid4()), 
                "bedrock"
            )

    def test_set_agents_backend_by_project_empty_string(self):
        """Test setting empty string as backend should raise an exception"""
        with self.assertRaises(Exception):
            self.usecase.set_agents_backend_by_project(
                str(self.project.uuid), 
                ""
            )

    def test_get_agents_backend_after_set(self):
        """Test getting backend after setting it"""
        # Set the backend
        self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), 
            "openai"
        )
        
        # Get the backend
        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "OpenAIBackend")

    def test_set_agents_backend_multiple_times(self):
        """Test setting backend multiple times"""
        # Set to bedrock first
        result1 = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), 
            "bedrock"
        )
        self.assertEqual(result1, "BedrockBackend")
        
        # Set to openai
        result2 = self.usecase.set_agents_backend_by_project(
            str(self.project.uuid), 
            "openai"
        )
        self.assertEqual(result2, "OpenAIBackend")
        
        # Verify the final state
        self.project.refresh_from_db()
        self.assertEqual(self.project.agents_backend, "OpenAIBackend")
        
        # Get the backend
        backend = self.usecase.get_agents_backend_by_project(str(self.project.uuid))
        self.assertEqual(backend, "OpenAIBackend") 