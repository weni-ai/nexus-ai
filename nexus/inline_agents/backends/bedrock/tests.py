from unittest import skip
from unittest.mock import patch

from django.test import TestCase

from inline_agents.backends.tests.inline_factories import SupervisorFactory
from nexus.inline_agents.backends.bedrock.repository import BedrockSupervisorRepository
from nexus.usecases.projects.tests.project_factory import ProjectFactory


@skip("Bedrock backend is being deprecated")
class TestBedrockSupervisorRepository(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.repository = BedrockSupervisorRepository()
        self.supervisor = SupervisorFactory()

    def test_get_supervisor(self):
        result = BedrockSupervisorRepository.get_supervisor(project=self.project)

        # Assert
        self.assertEqual(result["prompt_override_configuration"], self.supervisor.prompt_override_configuration)
        self.assertEqual(result["instruction"], self.supervisor.instruction)
        self.assertEqual(result["action_groups"], self.supervisor.action_groups)
        self.assertEqual(result["foundation_model"], self.supervisor.foundation_model)
        self.assertEqual(result["knowledge_bases"], self.supervisor.knowledge_bases)

    def test_get_supervisor_with_custom_foundation_model_and_foundation_model_empty(self):
        self.project.default_supervisor_foundation_model = "custom_foundation_model"
        self.project.save()

        result = BedrockSupervisorRepository.get_supervisor(project=self.project)

        # Assert
        self.assertEqual(result["prompt_override_configuration"], self.supervisor.prompt_override_configuration)
        self.assertEqual(result["instruction"], self.supervisor.instruction)
        self.assertEqual(result["action_groups"], self.supervisor.action_groups)
        self.assertEqual(result["foundation_model"], "custom_foundation_model")
        self.assertEqual(result["knowledge_bases"], self.supervisor.knowledge_bases)

    def test_get_supervisor_with_foundation_model(self):
        result = BedrockSupervisorRepository.get_supervisor(project=self.project, foundation_model="foundation_model")

        # Assert
        self.assertEqual(result["prompt_override_configuration"], self.supervisor.prompt_override_configuration)
        self.assertEqual(result["instruction"], self.supervisor.instruction)
        self.assertEqual(result["action_groups"], self.supervisor.action_groups)
        self.assertEqual(result["foundation_model"], "foundation_model")
        self.assertEqual(result["knowledge_bases"], self.supervisor.knowledge_bases)

    def test_get_supervisor_with_custom_foundation_model_and_foundation_model_not_empty(self):
        self.project.default_supervisor_foundation_model = "custom_foundation_model"
        self.project.save()

        result = BedrockSupervisorRepository.get_supervisor(project=self.project, foundation_model="foundation_model")

        # Assert
        self.assertEqual(result["prompt_override_configuration"], self.supervisor.prompt_override_configuration)
        self.assertEqual(result["instruction"], self.supervisor.instruction)
        self.assertEqual(result["action_groups"], self.supervisor.action_groups)
        self.assertEqual(result["foundation_model"], "custom_foundation_model")
        self.assertEqual(result["knowledge_bases"], self.supervisor.knowledge_bases)

    # Specific tests for the get_foundation_model method
    def test_get_foundation_model_default_behavior(self):
        """Tests default behavior when there is no customization"""
        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        self.assertEqual(result, self.supervisor.foundation_model)

    def test_get_foundation_model_with_project_custom_model(self):
        """Tests when the project has a custom model defined"""
        self.project.default_supervisor_foundation_model = "project_custom_model"
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        self.assertEqual(result, "project_custom_model")

    def test_get_foundation_model_with_foundation_model_parameter(self):
        """Tests when the foundation_model parameter is passed"""
        result = BedrockSupervisorRepository.get_foundation_model(
            project=self.project, supervisor=self.supervisor, foundation_model="parameter_model"
        )
        self.assertEqual(result, "parameter_model")

    def test_get_foundation_model_with_project_custom_and_parameter(self):
        """Tests when there are both project custom model and foundation_model parameter"""
        self.project.default_supervisor_foundation_model = "project_custom_model"
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(
            project=self.project, supervisor=self.supervisor, foundation_model="parameter_model"
        )
        # The project custom model should have priority
        self.assertEqual(result, "project_custom_model")

    def test_get_foundation_model_with_empty_project_custom(self):
        """Tests when the project has empty default_supervisor_foundation_model"""
        self.project.default_supervisor_foundation_model = ""
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        self.assertEqual(result, self.supervisor.foundation_model)

    def test_get_foundation_model_with_none_project_custom(self):
        """Tests when the project has default_supervisor_foundation_model as None"""
        self.project.default_supervisor_foundation_model = None
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        self.assertEqual(result, self.supervisor.foundation_model)

    def test_get_foundation_model_with_none_foundation_model_parameter(self):
        """Tests when the foundation_model parameter is None"""
        result = BedrockSupervisorRepository.get_foundation_model(
            project=self.project, supervisor=self.supervisor, foundation_model=None
        )
        self.assertEqual(result, self.supervisor.foundation_model)

    def test_get_foundation_model_priority_order(self):
        """Tests priority order: project custom > parameter > supervisor default"""
        # Scenario 1: Only supervisor default
        result1 = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        self.assertEqual(result1, self.supervisor.foundation_model)

        # Scenario 2: Supervisor default + foundation_model parameter
        result2 = BedrockSupervisorRepository.get_foundation_model(
            project=self.project, supervisor=self.supervisor, foundation_model="param_model"
        )
        self.assertEqual(result2, "param_model")

        # Scenario 3: Supervisor default + parameter + project custom
        self.project.default_supervisor_foundation_model = "project_custom"
        self.project.save()

        result3 = BedrockSupervisorRepository.get_foundation_model(
            project=self.project, supervisor=self.supervisor, foundation_model="param_model"
        )
        self.assertEqual(result3, "project_custom")

    @patch("nexus.settings.LOCKED_FOUNDATION_MODELS", ["locked_model_1", "locked_model_2"])
    def test_get_foundation_model_with_locked_supervisor_model(self):
        """Tests when supervisor foundation_model is in LOCKED_FOUNDATION_MODELS"""
        # Set supervisor model to a locked model
        self.supervisor.foundation_model = "locked_model_1"
        self.supervisor.save()

        # Try to override with project custom model
        self.project.default_supervisor_foundation_model = "project_custom_model"
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        # Should return the project model, since the lock only
        # aplies to the foundation model returned by the complexity layer
        self.assertEqual(result, "project_custom_model")

    @patch("nexus.settings.LOCKED_FOUNDATION_MODELS", ["locked_model_1", "locked_model_2"])
    def test_get_foundation_model_with_locked_project_custom_model(self):
        """Tests when project custom model is in LOCKED_FOUNDATION_MODELS"""
        # Set project custom model to a locked model
        self.project.default_supervisor_foundation_model = "locked_model_2"
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        # Should return the locked project custom
        self.assertEqual(result, self.project.default_supervisor_foundation_model)

    @patch("nexus.settings.LOCKED_FOUNDATION_MODELS", ["locked_model_1", "locked_model_2"])
    def test_get_foundation_model_with_locked_parameter_model(self):
        """Tests when foundation_model parameter is in LOCKED_FOUNDATION_MODELS"""
        result = BedrockSupervisorRepository.get_foundation_model(
            project=self.project, supervisor=self.supervisor, foundation_model="locked_model_1"
        )
        # Should return the parameter model, since the lock only
        # aplies to the foundation model returned by the complexity layer
        self.assertEqual(result, "locked_model_1")

    @patch("nexus.settings.LOCKED_FOUNDATION_MODELS", ["locked_model_1", "locked_model_2"])
    def test_get_foundation_model_priority_with_locked_models(self):
        """Tests priority order when locked models are involved"""
        # Set project custom model to a locked model
        self.project.default_supervisor_foundation_model = "locked_model_1"
        self.project.save()

        # Try to override with parameter that is also locked
        result = BedrockSupervisorRepository.get_foundation_model(
            project=self.project, supervisor=self.supervisor, foundation_model="locked_model_2"
        )
        # Should return the project model since both are locked
        self.assertEqual(result, self.project.default_supervisor_foundation_model)

    @patch("nexus.settings.LOCKED_FOUNDATION_MODELS", [])
    def test_get_foundation_model_with_empty_locked_models_list(self):
        """Tests when LOCKED_FOUNDATION_MODELS is empty (no restrictions)"""
        self.project.default_supervisor_foundation_model = "any_model"
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        # Should work normally when no models are locked
        self.assertEqual(result, "any_model")

    @patch("nexus.settings.LOCKED_FOUNDATION_MODELS", ["locked_model"])
    def test_get_foundation_model_with_non_locked_models(self):
        """Tests that non-locked models can be overridden normally"""
        self.project.default_supervisor_foundation_model = "non_locked_model"
        self.project.save()

        result = BedrockSupervisorRepository.get_foundation_model(project=self.project, supervisor=self.supervisor)
        # Should return the project custom model since it's not locked
        self.assertEqual(result, "non_locked_model")
